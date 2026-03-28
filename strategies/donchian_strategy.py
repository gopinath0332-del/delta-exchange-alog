import logging
import datetime
from typing import Dict, Optional, Tuple, Any, List
import pandas as pd
import ta
import numpy as np
from core.config import get_config
from core.candle_utils import get_closed_candle_index
from core.persistence import save_strategy_state, load_strategy_state, clear_strategy_state

logger = logging.getLogger(__name__)

def format_time(ts_ms): 
    return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')

class DonchianChannelStrategy:
    """
    Donchian Channel Strategy (Gold Both directions)
    
    Strategy Logic:
    - Long Entry: Close breaks above upper Donchian channel.
    - Long Exit: Close breaks below lower Donchian channel OR trailing stop hit.
    - Short Entry: Close breaks below lower Donchian channel (if allowed and duration met).
    - Short Exit: Close breaks above upper Donchian channel OR trailing stop hit.
    - Partial TP: 50% exit at Entry +/- (ATR * Multiplier) [if enabled].
    - Trailing Stop: Dynamically updated ATR based stop.
    """
    
    def __init__(self, symbol: str = "ARCUSD"):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("donchian_channel", {})

        # Parameters
        self.symbol = symbol  # Passed from runner/config
        self.trade_mode = cfg.get("trade_mode", "Both") # "Long", "Short", "Both"
        self.enter_period = cfg.get("enter_period", 20)
        self.exit_period = cfg.get("exit_period", 10)
        self.atr_period = cfg.get("atr_period", 16)
        self.atr_mult_tp = cfg.get("atr_mult_tp", 4.0)
        self.atr_mult_trail = cfg.get("atr_mult_trail", 2.0)
        self.enable_partial_tp = cfg.get("enable_partial_tp", True)  # Changed default to True
        self.partial_pct = cfg.get("partial_pct", 0.5)
        self.stop_loss_pct = cfg.get("stop_loss_pct", None)  # Fixed stop loss % (e.g. 0.50 for 50%)

        # Profit Milestone Exits (works alongside ATR partial TP)
        self.enable_profit_milestones = cfg.get("enable_profit_milestones", False)
        self.profit_milestones = cfg.get("profit_milestones", [])
        
        # Determine bars_per_day dynamically based on timeframe
        # timeframe format e.g. "1h", "2h", "4h", "6h", "1d", "180m"
        self.timeframe = "1h" # Default, will be set by runner
        
        # Use provided bars_per_day as fallback, otherwise calculate
        default_bars = cfg.get("bars_per_day", 24)
        self.bars_per_day = default_bars
        self.min_long_days = cfg.get("min_long_days", 0)  # Changed default to 0
        self.min_long_bars = self.bars_per_day * self.min_long_days
        # NEW: EMA Filter
        self.ema_length = cfg.get("ema_length", 100)
        self.ema_source = cfg.get("ema_source", "close")  # close, open, high, low
        # Mode Flags
        self.allow_long = self.trade_mode in ["Long", "Both"]
        self.allow_short = self.trade_mode in ["Short", "Both"]
        
        self.indicator_label = "Donchian"
        
        # Leverage (set by runner from trade_config; used to convert price PnL% to margin PnL%)
        self.leverage: int = 1

        # State
        self.current_position = 0  # 1 for Long, -1 for Short, 0 for Flat
        self.last_entry_price = 0.0
        self.entry_price = None
        self.entry_bar_index = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.partial_exit_done = False
        self.milestones_hit = [False] * len(self.profit_milestones)
        self.initial_sl_price = None  # Initial hard stop loss price

        # Duration State
        self.last_long_duration_bars = 0
        self.long_entry_bar = None
        
        # Indicator Cache (for dashboard)
        self.last_upper_channel = 0.0
        self.last_lower_channel = 0.0
        self.last_atr = 0.0
        self.last_ema = 0.0  # NEW: EMA Cache
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
        # Action Tracking (One action per candle rule)
        self.last_action_candle_ts = None
        
    def _update_bars_per_day(self, timeframe: str):
        """Update bars_per_day and min_long_bars based on timeframe."""
        self.timeframe = timeframe
        if timeframe == "1h":
            self.bars_per_day = 24
        elif timeframe == "2h":
            self.bars_per_day = 12
        elif timeframe == "3h" or timeframe == "180m":
            self.bars_per_day = 8
        elif timeframe == "4h":
            self.bars_per_day = 6
        elif timeframe == "6h":
            self.bars_per_day = 4
        elif timeframe == "12h":
            self.bars_per_day = 2
        elif timeframe == "1d":
            self.bars_per_day = 1
        
        self.min_long_bars = self.bars_per_day * self.min_long_days
        logger.info(f"Updated Donchian strategy: timeframe={timeframe}, bars_per_day={self.bars_per_day}, min_long_bars={self.min_long_bars}")
        
        # Closed Candle Cache
        self.last_closed_time_str = "-"
        self.last_closed_upper = 0.0
        self.last_closed_lower = 0.0
        
    def calculate_indicators(self, df: pd.DataFrame, current_time: Optional[float] = None) -> Tuple[float, float, float, float]:
        """
        Calculate Donchian Channels and ATR.
        """
        try:
            if len(df) < max(self.enter_period, self.exit_period, self.atr_period, self.ema_length) + 1:
                return 0.0, 0.0, 0.0, 0.0
                
            if current_time is None:
                import time
                current_time = time.time()
                
            # Donchian Channels
            upper_channel = df['high'].rolling(window=self.enter_period).max()
            lower_channel = df['low'].rolling(window=self.exit_period).min()
            
            # ATR (EMA based)
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr_series = true_range.ewm(span=self.atr_period, adjust=False).mean()
            
            # NEW: EMA Calculation
            ema_src = df[self.ema_source] if self.ema_source in df.columns else df['close']
            ema_series = ema_src.ewm(span=self.ema_length, adjust=False).mean()
            
            current_upper = upper_channel.iloc[-1]
            current_lower = lower_channel.iloc[-1]
            current_atr = atr_series.iloc[-1]
            current_ema = ema_series.iloc[-1]
            
            # Cache for dashboard
            self.last_upper_channel = current_upper
            self.last_lower_channel = current_lower
            self.last_atr = current_atr
            self.last_ema = current_ema
            
            # Closed Candle Logic
            closed_idx = get_closed_candle_index(df, current_time * 1000, self.timeframe)
            
            if len(df) >= abs(closed_idx):
                import datetime
                ts = df['time'].iloc[closed_idx]
                if ts > 1e11: ts /= 1000
                self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M')
                self.last_closed_upper = upper_channel.iloc[closed_idx]
                self.last_closed_lower = lower_channel.iloc[closed_idx]
            else:
                self.last_closed_time_str = "-"
                self.last_closed_upper = 0.0
                self.last_closed_lower = 0.0
            
            return current_upper, current_lower, current_atr, current_ema
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return 0.0, 0.0, 0.0, 0.0

    def check_signals(
        self,
        df: pd.DataFrame,
        current_time_ms: float,
        live_pos_data: Optional[Dict] = None
    ) -> Tuple[Optional[str], str]:
        """
        Check for trading signals using closed candle logic.

        Args:
            df: OHLCV DataFrame (sorted ascending by time).
            current_time_ms: Current epoch time in milliseconds.
        """
        if df.empty or len(df) < max(self.enter_period, self.exit_period, self.atr_period, self.ema_length) + 2:
            return None, ""

        current_time_s = current_time_ms / 1000.0
        upper, lower, atr, ema = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine Closed Candle Index
        closed_idx = get_closed_candle_index(df, current_time_ms, self.timeframe)
        
        # One Action Per Candle Rule:
        # If we already acted on this closed candle, skip further actions until a new candle closes.
        closed_candle_ts = df['time'].iloc[closed_idx]
        if self.last_action_candle_ts is not None and closed_candle_ts <= self.last_action_candle_ts:
            return None, f"One action per candle rule: Already acted on candle {closed_candle_ts}"
        
        # Data at Closed Index
        close_closed = df['close'].iloc[closed_idx]
        
        # Previous Index for Channel Logic (Channel[1])
        prev_idx = closed_idx - 1
        
        upper_channel_series = df['high'].rolling(window=self.enter_period).max()
        lower_channel_series = df['low'].rolling(window=self.exit_period).min()
        upper_prev = upper_channel_series.iloc[prev_idx]
        lower_prev = lower_channel_series.iloc[prev_idx]
        
        # Calculate ATR at closed index for setting levels
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr_series = true_range.ewm(span=self.atr_period, adjust=False).mean()
        atr_closed = atr_series.iloc[closed_idx]
        
        # Calculate EMA at closed index
        ema_src = df[self.ema_source] if self.ema_source in df.columns else df['close']
        ema_series = ema_src.ewm(span=self.ema_length, adjust=False).mean()
        ema_closed = ema_series.iloc[closed_idx]
        
        # Current Price for Trailing Stop Updates (responsive)
        current_price = df['close'].iloc[-1]
        
        action = None
        reason = ""

        # --- LOGIC ---

        # Update Duration State (if Long) — tracks approximate bar index of entry
        # for the min_long_days short-entry gate.
        if self.current_position == 1:
            if self.long_entry_bar is None:
                self.long_entry_bar = len(df) + closed_idx  # Approximate bar index

        # 1. Trailing Stop Update (evaluate on candle close, NOT live intra-bar wicks)
        if self.trailing_stop_level is not None:
            if self.current_position == 1:
                # Long: Stop moves UP only (ratchets based on closed candle)
                new_stop = close_closed - (atr_closed * self.atr_mult_trail)
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
            elif self.current_position == -1:
                # Short: Stop moves DOWN only (ratchets based on closed candle)
                new_stop = close_closed + (atr_closed * self.atr_mult_trail)
                if new_stop < self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
                    
        # 2. Check Trailing Stop Hit (CLOSED CANDLE LOGIC - prevents false signals on wicks)
        if self.trailing_stop_level is not None:
            if self.current_position == 1 and close_closed <= self.trailing_stop_level:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_LONG", f"Trailing SL Hit: {close_closed:.4f} <= {self.trailing_stop_level:.4f}"
            elif self.current_position == -1 and close_closed >= self.trailing_stop_level:
                self.last_action_candle_ts = closed_candle_ts
                return "EXIT_SHORT", f"Trailing SL Hit: {close_closed:.4f} >= {self.trailing_stop_level:.4f}"
                
        # 3. Check Partial TP (LIVE PRICE LOGIC - fires immediately when price crosses ATR TP level)
        # Uses current_price (latest tick) instead of close_closed so the TP executes as soon as
        # the market touches the target, without waiting for the candle to close.
        if self.enable_partial_tp and not self.partial_exit_done and self.tp_level is not None:
            if self.current_position == 1 and current_price >= self.tp_level:
                return "PARTIAL_EXIT", f"Partial TP Hit: {current_price:.4f} >= {self.tp_level:.4f}"
            elif self.current_position == -1 and current_price <= self.tp_level:
                return "PARTIAL_EXIT", f"Partial TP Hit: {current_price:.4f} <= {self.tp_level:.4f}"

        # 3b. Profit Milestone Exits (live price, independent of ATR partial TP)
        if self.enable_profit_milestones and self.current_position != 0:
            pnl_pct = 0.0
            pnl_source = "Manual"
            
            # Use Exchange Unrealized Margin PnL if available (User Priority)
            if live_pos_data:
                unrealized_pnl = float(live_pos_data.get('unrealized_pnl', 0.0))
                margin = float(live_pos_data.get('margin', 0.0))
                if margin > 0:
                    pnl_pct = (unrealized_pnl / margin) * 100.0
                    pnl_source = "Exchange"
                    # No need for manual calculation or leverage adjustment as margin PnL is absolute
                else:
                    # Fallback to manual if margin is zero (unexpected)
                    if self.entry_price:
                        if self.current_position == 1:
                            pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
                        else:
                            pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage
            elif self.entry_price:
                # Manual Fallback (Backtesting or API failure)
                if self.current_position == 1:
                    pnl_pct = ((current_price - self.entry_price) / self.entry_price) * 100 * self.leverage
                else:
                    pnl_pct = ((self.entry_price - current_price) / self.entry_price) * 100 * self.leverage

            for idx, milestone in enumerate(self.profit_milestones):
                if self.milestones_hit[idx]:
                    continue
                pnl_threshold = milestone["pnl_pct"]
                exit_pct = milestone["exit_pct"]
                if pnl_pct >= pnl_threshold:
                    return "MILESTONE_EXIT", (
                        f"Milestone {idx + 1}: {pnl_source} PnL {pnl_pct:.1f}% >= {pnl_threshold}%"
                        f" | exit_pct={exit_pct}"
                    )

        # 4. Entry/Exit Logic (Closed Candle)
        
        # LONG Logic
        if self.allow_long:
            # Entry Long: Breakout AND close > EMA
            if self.current_position == 0:
                if close_closed >= upper_prev and close_closed > ema_closed:
                    action = "ENTRY_LONG"
                    reason = f"Breakout: Close {close_closed:.4f} >= Upper[prev] {upper_prev:.4f} AND above EMA {ema_closed:.4f}"
                    # Set Levels
                    self.entry_price = close_closed
                    self.tp_level = close_closed + (atr_closed * self.atr_mult_tp)
                    self.trailing_stop_level = close_closed - (atr_closed * self.atr_mult_trail)
                    
                    # Pre-calculate Initial Stop Loss Price for runner (important for bracket SL)
                    if self.stop_loss_pct is not None:
                        # Formula: Price * (1 - SL% / Leverage)
                        self.initial_sl_price = close_closed * (1 - self.stop_loss_pct / self.leverage)
                        logger.debug(f"Pre-calculated initial SL for LONG: {self.initial_sl_price:.4f} ({self.stop_loss_pct*100}% of margin)")
                    
                    self.partial_exit_done = False
                    self.long_entry_bar = len(df) + closed_idx # Mark entry index
                    self.last_action_candle_ts = closed_candle_ts
                    return action, reason
                    
            # Exit Long (Channel Breakdown)
            elif self.current_position == 1:
                if close_closed <= lower_prev:
                    action = "EXIT_LONG"
                    reason = f"Breakdown: Close {close_closed:.4f} <= Lower[prev] {lower_prev:.4f}"
                    self.last_action_candle_ts = closed_candle_ts
                    return action, reason

        # SHORT Logic
        if self.allow_short:
            # Entry Short: Breakdown AND close < EMA AND duration met
            if self.current_position == 0:
                # Check Duration Condition (Must have held long enough previously)
                duration_ok = True
                if self.min_long_days > 0:
                     if self.last_long_duration_bars < self.min_long_bars:
                         duration_ok = False
                
                # If min_long_days is 0, duration_ok is True (screenshot case)
                
                if duration_ok and close_closed <= lower_prev and close_closed < ema_closed:
                    action = "ENTRY_SHORT"
                    reason = f"Breakdown: Close {close_closed:.4f} <= Lower[prev] {lower_prev:.4f} AND below EMA {ema_closed:.4f}"
                    # Set Levels
                    self.entry_price = close_closed
                    self.tp_level = close_closed - (atr_closed * self.atr_mult_tp)
                    self.trailing_stop_level = close_closed + (atr_closed * self.atr_mult_trail)
                    
                    # Pre-calculate Initial Stop Loss Price for runner (important for bracket SL)
                    if self.stop_loss_pct is not None:
                        # Formula: Price * (1 + SL% / Leverage)
                        self.initial_sl_price = close_closed * (1 + self.stop_loss_pct / self.leverage)
                        logger.debug(f"Pre-calculated initial SL for SHORT: {self.initial_sl_price:.4f} ({self.stop_loss_pct*100}% of margin)")
                    
                    self.partial_exit_done = False
                    self.last_action_candle_ts = closed_candle_ts
                    return action, reason
                    
            # Exit Short (Channel Breakout)
            elif self.current_position == -1:
                if close_closed >= upper_prev:
                    action = "EXIT_SHORT"
                    reason = f"Breakout: Close {close_closed:.4f} >= Upper[prev] {upper_prev:.4f}"
                    self.last_action_candle_ts = closed_candle_ts
                    return action, reason
                    
        return None, ""

    def update_position_state(self, action: str, current_time_ms: float, indicators: Any = None, price: float = 0.0, reason: str = ""):
        """Update internal state."""
        import datetime
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
            
        upper = indicators.get('upper', 0.0) if isinstance(indicators, dict) else 0.0
        lower = indicators.get('lower', 0.0) if isinstance(indicators, dict) else 0.0
        
        # Record the bar timestamp for the "one action per candle" rule.
        # This prevents multiple entries/exits on the same candle close during 10-min cycles.
        # We handle this by setting last_action_candle_ts which is checked in check_signals.
        # The timestamp used here should match the closed_candle_ts from check_signals.
        # For simplicity, we can pass it or derive it, but here we'll assume the strategy 
        # state is updated ONLY when an action is confirmed.
        
        if action in ["ENTRY_LONG", "ENTRY_SHORT", "EXIT_LONG", "EXIT_SHORT"]:
             # Note: We need to know which candle triggered this. 
             # In live runner, this is the current closed candle.
             # We'll set it here to the 'current' closed candle TS if possible, 
             # or handle it inside check_signals by marking it there.
             pass
        
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_entry_price = price
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "status": "OPEN",
                "logs": []
            }
            # Calculate Initial Stop Loss Price (if pct configured)
            if self.stop_loss_pct is not None:
                # Formula: Price * (1 - SL% / Leverage)
                # E.g. Price=50, SL=0.50 (50%), Leverage=5 -> 50 * (1 - 0.1) = 45
                self.initial_sl_price = price * (1 - self.stop_loss_pct / self.leverage)
                logger.debug(f"Calculated initial SL for LONG: {self.initial_sl_price:.4f} ({self.stop_loss_pct*100}% of margin)")
            else:
                self.initial_sl_price = None
            
        elif action == "ENTRY_SHORT":
            self.current_position = -1
            self.last_entry_price = price
            self.last_long_duration_bars = 0 # Reset duration counter? Pine logic says: lastLongBars updated when Long -> Flat
            self.active_trade = {
                "type": "SHORT",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "status": "OPEN",
                "logs": []
            }
            # Calculate Initial Stop Loss Price (if pct configured)
            if self.stop_loss_pct is not None:
                # Formula: Price * (1 + SL% / Leverage)
                # E.g. Price=50, SL=0.50 (50%), Leverage=5 -> 50 * (1 + 0.1) = 55
                self.initial_sl_price = price * (1 + self.stop_loss_pct / self.leverage)
                logger.debug(f"Calculated initial SL for SHORT: {self.initial_sl_price:.4f} ({self.stop_loss_pct*100}% of margin)")
            else:
                self.initial_sl_price = None

        elif action == "PARTIAL_EXIT":
            if self.active_trade:
                partial_trade = self.active_trade.copy()
                partial_trade["exit_time"] = format_time(current_time_ms)
                partial_trade["exit_price"] = price
                partial_trade["status"] = "PARTIAL"
                partial_trade["exit_pct"] = self.partial_pct  # Track exit percentage
                entry = float(self.active_trade['entry_price'])
                partial_trade["points"] = price - entry if self.current_position == 1 else entry - price
                self.trades.append(partial_trade)
                self.partial_exit_done = True
                self.active_trade["partial_exit"] = True

        elif action == "MILESTONE_EXIT":
            # Parse milestone index from reason string
            milestone_idx = 0
            exit_pct = 0.0
            if reason:
                import re
                match = re.search(r"Milestone (\d+):", reason)
                if match:
                    milestone_idx = int(match.group(1)) - 1
            
            if 0 <= milestone_idx < len(self.profit_milestones):
                self.milestones_hit[milestone_idx] = True
                exit_pct = self.profit_milestones[milestone_idx].get("exit_pct", 0.0)
                
            if self.active_trade:
                milestone_trade = self.active_trade.copy()
                milestone_trade["exit_time"] = format_time(current_time_ms)
                milestone_trade["exit_price"] = price
                milestone_trade["status"] = f"MILESTONE_{milestone_idx + 1}"
                milestone_trade["exit_pct"] = exit_pct  # Track exit percentage
                entry = float(self.active_trade['entry_price'])
                milestone_trade["points"] = price - entry if self.current_position == 1 else entry - price
                self.trades.append(milestone_trade)
                self.active_trade["milestone_exit"] = True

        elif action == "EXIT_LONG":
            self.current_position = 0
            # Calculate Duration
            if self.long_entry_bar:
                # Approximate duration in bars since entry
                # We don't have perfect bar index here in live, but backtest propagates it
                # In live, we might need time-based? 
                # For now assume backtest logic holds mostly.
                pass 
                
            # For Pine logic matching: lastLongBars := bar_index - longEntryBar
            # In live check_signals, we update long_entry_bar.
            # Here we just mark we exited.
            
            # Simple Duration Hack for Live:
            # If we rely on bars, we need persistent counter. 
            # For simplicity, if min_long_days=0, it doesn't matter.
            self.last_long_duration_bars = 9999 # Allow next short if days=0
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                # Update status label based on the exit reason
                if "Trailing" in reason: self.active_trade["status"] = "TRAIL STOP"
                elif "Breakdown" in reason: self.active_trade["status"] = "CHANNEL EXIT"

                self.active_trade["points"] = price - self.active_trade["entry_price"]
                self.trades.append(self.active_trade)
                self.active_trade = None
            
            self.entry_price = None
            self.tp_level = None
            self.trailing_stop_level = None
            self.partial_exit_done = False
            self.milestones_hit = [False] * len(self.profit_milestones)
            self.long_entry_bar = None
            self.initial_sl_price = None

        elif action == "EXIT_SHORT":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                if "Trailing" in reason: self.active_trade["status"] = "TRAIL STOP"
                elif "Breakout" in reason: self.active_trade["status"] = "CHANNEL EXIT"

                self.active_trade["points"] = self.active_trade["entry_price"] - price
                self.trades.append(self.active_trade)
                self.active_trade = None

            self.entry_price = None
            self.tp_level = None
            self.trailing_stop_level = None
            self.partial_exit_done = False
            self.milestones_hit = [False] * len(self.profit_milestones)
            self.initial_sl_price = None
        
        # PERSIST TO DISK
        # Save after any position state update to ensure restarts pick up latest flags.
        self._save_to_disk()

    def set_position(self, position: int):
        self.current_position = position

    def _save_to_disk(self):
        """Save current trade flags to disk for persistence across restarts."""
        try:
            state = {
                "partial_exit_done": self.partial_exit_done,
                "milestones_hit": self.milestones_hit,
                "entry_price": self.entry_price,
                "tp_level": self.tp_level,
                "trailing_stop_level": self.trailing_stop_level,
                "initial_sl_price": self.initial_sl_price,
                "current_position": self.current_position
            }
            save_strategy_state(self.symbol, "donchian_channel", state)
        except Exception as e:
            logger.error(f"Error saving strategy state for {self.symbol}: {e}")

    def _load_from_disk(self) -> bool:
        """
        Attempt to restore trade flags from disk.
        Returns True if state was successfully restored.
        """
        try:
            state = load_strategy_state(self.symbol, "donchian_channel")
            if not state:
                return False
            
            self.partial_exit_done = state.get("partial_exit_done", False)
            self.milestones_hit = state.get("milestones_hit", [False] * len(self.profit_milestones))
            
            # Restore levels if they aren't already set
            if getattr(self, 'tp_level', None) is None: self.tp_level = state.get("tp_level")
            if getattr(self, 'trailing_stop_level', None) is None: self.trailing_stop_level = state.get("trailing_stop_level")
            if getattr(self, 'initial_sl_price', None) is None: self.initial_sl_price = state.get("initial_sl_price")
            
            logger.info(f"Successfully restored trade state from disk for {self.symbol}: Partial={self.partial_exit_done}, Milestones={self.milestones_hit}")
            return True
        except Exception as e:
            logger.warning(f"Error loading strategy state for {self.symbol}: {e}")
            return False

    def reconcile_position(self, size: float, entry_price: float, current_price: float = None, live_pos_data: Optional[Dict] = None):
        """Reconcile internal strategy state with Live Exchange position."""
        import time, datetime
        def format_time(ts_ms): return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
        
        expected_pos = 0
        if size > 0: expected_pos = 1
        elif size < 0: expected_pos = -1
        
        # Determine if we need to reset state (Entry price changed or new position found)
        # We use a small epsilon for price comparison to avoid floating point noise
        price_changed = self.entry_price is not None and abs(self.entry_price - entry_price) > 0.0001
        new_pos_found = self.current_position == 0 and expected_pos != 0

        # Sync state if needed
        if self.current_position != expected_pos or price_changed:
            if self.current_position != expected_pos:
                logger.warning(f"Reconciling Position: Internal {self.current_position} -> Exchange {expected_pos} (Size: {size})")
            
            if price_changed:
                logger.warning(f"Reconciling Entry Price: Internal {self.entry_price} -> Exchange {entry_price}")

            # Genuinely new if direction changed (e.g. LONG -> SHORT or SHORT -> LONG).
            # Moving from 0 (init) to 1 (active) is a "Cold Start".
            # Moving from 0 (was flat) to 1 (active) on a LIVE cycle is a "New Entry".
            # We use persistence to distinguish them.
            if self.current_position == 0 and expected_pos != 0:
                # Cold Start / Re-syncing existing position
                # Try to load previous state to avoid duplicate signals.
                found = self._load_from_disk()
                if found:
                    logger.info("Cold Start: Re-synced with existing position using persistent state.")
                else:
                    logger.info("Cold Start: Re-synced with existing position. No persistent state found.")
                
            truly_new_position = (self.current_position != 0 and self.current_position != expected_pos)

            self.current_position = expected_pos
            self.entry_price = entry_price
            
            if truly_new_position:
                # Genuinely flipped direction -> reset all flags
                self.milestones_hit = [False] * len(self.profit_milestones)
                self.partial_exit_done = False
                clear_strategy_state(self.symbol, "donchian_channel") # Clean slate
            
            if expected_pos != 0 and not self.active_trade:
                side = "LONG" if expected_pos == 1 else "SHORT"
                self.active_trade = {
                    "type": side,
                    "entry_time": format_time(time.time()*1000) + " (Rec)",
                    "entry_price": entry_price,
                    "status": "OPEN"
                }
                logger.info(f"Created reconciled active trade for {side} at {entry_price}")

            elif expected_pos == 0:
                if self.active_trade:
                    self.active_trade["exit_time"] = format_time(time.time()*1000) + " (Rec)"
                    self.active_trade["status"] = "CLOSED (SYNC)"
                    self.trades.append(self.active_trade)
                    self.active_trade = None
                    logger.info("Closed active trade during reconciliation (Flat on exchange)")
                
                # IMPORTANT: Clear stale state to prevent reuse in next trade
                self.entry_price = None
                self.tp_level = None
                self.trailing_stop_level = None
                self.initial_sl_price = None
                self.partial_exit_done = False
                self.milestones_hit = [False] * len(self.profit_milestones)
                clear_strategy_state(self.symbol, "donchian_channel")

        # CATCH-UP LOGIC: We used to mark milestones as ALREADY HIT here if PnL exceeded threshold.
        # This was too aggressive and caused missed exits if the bot was offline when the target was hit.
        # Now, we let check_signals() handle it. If we are pass a milestone but it's not marked hit,
        # it will fire a signal normally during the next cycle.
        # We rely on the truly_new_position guard above to keep flags set across simple restarts.
        pass

    def run_backtest(self, df: pd.DataFrame):
        """Run backtest."""
        logger.info("Starting Donchian Channel backtest...")
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        self.entry_price = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.last_long_duration_bars = 0
        self.long_entry_bar = None
        self.milestones_hit = [False] * len(self.profit_milestones)

        if df.empty: return
        
        # Pre-calculate
        upper_channel = df['high'].rolling(window=self.enter_period).max()
        lower_channel = df['low'].rolling(window=self.exit_period).min()
        
        #  ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr_series = true_range.ewm(span=self.atr_period, adjust=False).mean()
        
        # NEW: EMA Calculation for Backtest
        ema_src = df[self.ema_source] if self.ema_source in df.columns else df['close']
        ema_series = ema_src.ewm(span=self.ema_length, adjust=False).mean()
        
        for i in range(len(df)):
            if i < max(self.enter_period, self.exit_period, self.atr_period, self.ema_length) + 1: continue
            
            current_time_ms = df['time'].iloc[i] * 1000
            close = df['close'].iloc[i]
            high = df['high'].iloc[i]
            low = df['low'].iloc[i]
            upper = upper_channel.iloc[i]
            lower = lower_channel.iloc[i]
            atr = atr_series.iloc[i]
            ema = ema_series.iloc[i]  # NEW: Get EMA value
            
            if pd.isna(upper) or pd.isna(lower): continue
            
            indicators = {'upper': upper, 'lower': lower, 'atr': atr}
            
            # 1. Update Trailing Stop
            if self.trailing_stop_level is not None:
                if self.current_position == 1:
                    new_stop = close - (atr * self.atr_mult_trail)
                    if new_stop > self.trailing_stop_level: self.trailing_stop_level = new_stop
                elif self.current_position == -1:
                    new_stop = close + (atr * self.atr_mult_trail)
                    if new_stop < self.trailing_stop_level: self.trailing_stop_level = new_stop
            
            # 2. Check Signals manually (Backtest Loop)
            # Trailing Stop Hit
            if self.trailing_stop_level is not None:
                if self.current_position == 1 and close <= self.trailing_stop_level:
                    self.update_position_state("EXIT_LONG", current_time_ms, indicators, close, "Trailing SL Hit")
                    # Update Duration Tracking
                    if self.long_entry_bar is not None:
                         self.last_long_duration_bars = i - self.long_entry_bar
                    continue
                elif self.current_position == -1 and close >= self.trailing_stop_level:
                    self.update_position_state("EXIT_SHORT", current_time_ms, indicators, close, "Trailing SL Hit")
                    continue
            
            # Partial TP Check (if enabled and not already done)
            if self.enable_partial_tp and not self.partial_exit_done and self.tp_level is not None:
                if self.current_position == 1 and high >= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", current_time_ms, indicators, self.tp_level, f"Partial TP Hit: {self.tp_level:.4f}")
                elif self.current_position == -1 and low <= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", current_time_ms, indicators, self.tp_level, f"Partial TP Hit: {self.tp_level:.4f}")

            # Profit Milestone Check (works alongside ATR partial TP)
            if self.enable_profit_milestones and self.entry_price and self.current_position != 0:
                for idx, milestone in enumerate(self.profit_milestones):
                    if self.milestones_hit[idx]:
                        continue
                    pnl_threshold = milestone["pnl_pct"]
                    exit_pct = milestone["exit_pct"]
                    if self.current_position == 1:
                        milestone_price = self.entry_price * (1 + pnl_threshold / (100 * self.leverage))
                        if high >= milestone_price:
                            reason = f"Milestone {idx + 1}: PnL >= {pnl_threshold}% | exit_pct={exit_pct}"
                            self.update_position_state("MILESTONE_EXIT", current_time_ms, indicators, milestone_price, reason)
                            break  # Only one milestone per bar
                    else:
                        milestone_price = self.entry_price * (1 - pnl_threshold / (100 * self.leverage))
                        if low <= milestone_price:
                            reason = f"Milestone {idx + 1}: PnL >= {pnl_threshold}% | exit_pct={exit_pct}"
                            self.update_position_state("MILESTONE_EXIT", current_time_ms, indicators, milestone_price, reason)
                            break  # Only one milestone per bar

            # Channel Logic: Use Prev Candle
            upper_prev = upper_channel.iloc[i-1]
            lower_prev = lower_channel.iloc[i-1]
            
            # Entries
            if self.current_position == 0:
                # Long: Breakout AND close > EMA
                if self.allow_long and close >= upper_prev and close > ema:
                    self.update_position_state("ENTRY_LONG", current_time_ms, indicators, close, "Breakout + EMA")
                    self.entry_price = close
                    self.tp_level = close + (atr * self.atr_mult_tp)
                    self.trailing_stop_level = close - (atr * self.atr_mult_trail)
                    self.long_entry_bar = i
                    self.partial_exit_done = False
                    self.milestones_hit = [False] * len(self.profit_milestones)

                # Short: Breakdown AND close < EMA
                elif self.allow_short and close <= lower_prev and close < ema:
                    # Check Duration
                    if self.min_long_days == 0 or (self.last_long_duration_bars >= self.min_long_bars):
                        self.update_position_state("ENTRY_SHORT", current_time_ms, indicators, close, "Breakdown + EMA")
                        self.entry_price = close
                        self.tp_level = close - (atr * self.atr_mult_tp)
                        self.trailing_stop_level = close + (atr * self.atr_mult_trail)
                        self.partial_exit_done = False
                        self.milestones_hit = [False] * len(self.profit_milestones)
            
            # Exits (Channel) by Signal
            elif self.current_position == 1:
                if close <= lower_prev:
                    self.update_position_state("EXIT_LONG", current_time_ms, indicators, close, "Breakdown")
                    if self.long_entry_bar is not None:
                         self.last_long_duration_bars = i - self.long_entry_bar
            
            elif self.current_position == -1:
                if close >= upper_prev:
                     self.update_position_state("EXIT_SHORT", current_time_ms, indicators, close, "Breakout")
                     
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")
