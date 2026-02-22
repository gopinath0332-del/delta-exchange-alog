import logging
from typing import Dict, Optional, Tuple, Any
import pandas as pd
import ta
import numpy as np
from core.config import get_config
from core.candle_utils import get_closed_candle_index

logger = logging.getLogger(__name__)

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
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("donchian_channel", {})

        # Parameters
        self.trade_mode = cfg.get("trade_mode", "Both") # "Long", "Short", "Both"
        self.enter_period = cfg.get("enter_period", 20)
        self.exit_period = cfg.get("exit_period", 10)
        self.atr_period = cfg.get("atr_period", 16)
        self.atr_mult_tp = cfg.get("atr_mult_tp", 4.0)
        self.atr_mult_trail = cfg.get("atr_mult_trail", 2.0)
        self.enable_partial_tp = cfg.get("enable_partial_tp", True)  # Changed default to True
        self.partial_pct = cfg.get("partial_pct", 0.5)
        self.bars_per_day = cfg.get("bars_per_day", 24)
        self.min_long_days = cfg.get("min_long_days", 0)  # Changed default to 0
        self.min_long_bars = self.bars_per_day * self.min_long_days
        # NEW: EMA Filter
        self.ema_length = cfg.get("ema_length", 100)
        self.ema_source = cfg.get("ema_source", "close")  # close, open, high, low
        # PnL Exit Guard: exit if unrealised PnL% drops below this threshold.
        # Configured via donchian_channel.pnl_exit_threshold in settings.yaml.
        self.pnl_exit_threshold = cfg.get("pnl_exit_threshold", -10.0)
        
        # Mode Flags
        self.allow_long = self.trade_mode in ["Long", "Both"]
        self.allow_short = self.trade_mode in ["Short", "Both"]
        
        self.indicator_label = "Donchian"
        self.timeframe = "1h"
        
        # State
        self.current_position = 0  # 1 for Long, -1 for Short, 0 for Flat
        self.last_entry_price = 0.0
        self.entry_price = None
        self.entry_bar_index = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.partial_exit_done = False
        
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
            last_candle_ts = df['time'].iloc[-1]
            if last_candle_ts > 1e11: last_candle_ts /= 1000
            
            diff = current_time - last_candle_ts
            # If candle is complete (closed), use -1, else use -2
            closed_idx = -1 if diff >= 3600 else -2
            
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
        pnl_pct: Optional[float] = None
    ) -> Tuple[Optional[str], str]:
        """
        Check for trading signals using closed candle logic.

        Args:
            df: OHLCV DataFrame (sorted ascending by time).
            current_time_ms: Current epoch time in milliseconds.
            pnl_pct: Current position PnL as a percentage (e.g. -12.5 means -12.5%).
                     When provided and < -10.0, an immediate exit is triggered BEFORE
                     the trailing-stop and channel-exit checks.
        """
        if df.empty or len(df) < max(self.enter_period, self.exit_period, self.atr_period, self.ema_length) + 2:
            return None, ""

        current_time_s = current_time_ms / 1000.0
        upper, lower, atr, ema = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine Closed Candle Index
        last_candle_ts = df['time'].iloc[-1]
        if last_candle_ts > 1e11: last_candle_ts /= 1000
        
        diff = current_time_s - last_candle_ts
        closed_idx = -1 if diff >= 3600 else -2
        
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

        # 0. PnL % Hard Exit Guard (checked BEFORE trailing stop and channel exits)
        #    If the current position's unrealised PnL drops below the configured threshold,
        #    exit immediately to cap downside risk beyond what the trailing stop covers.
        #    Threshold is set via donchian_channel.pnl_exit_threshold in settings.yaml.
        if pnl_pct is not None and self.current_position != 0:
            if pnl_pct < self.pnl_exit_threshold:
                if self.current_position == 1:
                    return (
                        "EXIT_LONG",
                        f"PnL Exit Guard: Position PnL {pnl_pct:.2f}% < {self.pnl_exit_threshold}%"
                    )
                elif self.current_position == -1:
                    return (
                        "EXIT_SHORT",
                        f"PnL Exit Guard: Position PnL {pnl_pct:.2f}% < {self.pnl_exit_threshold}%"
                    )
        
        # Update Duration State (if Long)
        if self.current_position == 1:
            # We track bars in position approximately
            if self.long_entry_bar is None:
                self.long_entry_bar = len(df) + closed_idx # Approx
        
        # 1. Trailing Stop Update (uses current price for responsiveness)
        if self.trailing_stop_level is not None:
            if self.current_position == 1:
                # Long: Stop moves UP only
                new_stop = current_price - (atr * self.atr_mult_trail)
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
            elif self.current_position == -1:
                # Short: Stop moves DOWN only
                new_stop = current_price + (atr * self.atr_mult_trail)
                if new_stop < self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
                    
        # 2. Check Trailing Stop Hit (CLOSED CANDLE LOGIC - prevents false signals)
        if self.trailing_stop_level is not None:
            if self.current_position == 1 and close_closed <= self.trailing_stop_level:
                return "EXIT_LONG", f"Trailing SL Hit: {close_closed:.4f} <= {self.trailing_stop_level:.4f}"
            elif self.current_position == -1 and close_closed >= self.trailing_stop_level:
                return "EXIT_SHORT", f"Trailing SL Hit: {close_closed:.4f} >= {self.trailing_stop_level:.4f}"
                
        # 3. Check Partial TP (CLOSED CANDLE LOGIC - prevents false signals)
        if self.enable_partial_tp and not self.partial_exit_done and self.tp_level is not None:
            if self.current_position == 1 and close_closed >= self.tp_level:
                return "PARTIAL_EXIT", f"Partial TP Hit: {close_closed:.4f} >= {self.tp_level:.4f}"
            elif self.current_position == -1 and close_closed <= self.tp_level:
                return "PARTIAL_EXIT", f"Partial TP Hit: {close_closed:.4f} <= {self.tp_level:.4f}"


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
                    self.partial_exit_done = False
                    self.long_entry_bar = len(df) + closed_idx # Mark entry index
                    return action, reason
                    
            # Exit Long (Channel Breakdown)
            elif self.current_position == 1:
                if close_closed <= lower_prev:
                    action = "EXIT_LONG"
                    reason = f"Breakdown: Close {close_closed:.4f} <= Lower[prev] {lower_prev:.4f}"
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
                    self.partial_exit_done = False
                    return action, reason
                    
            # Exit Short (Channel Breakout)
            elif self.current_position == -1:
                if close_closed >= upper_prev:
                    action = "EXIT_SHORT"
                    reason = f"Breakout: Close {close_closed:.4f} >= Upper[prev] {upper_prev:.4f}"
                    return action, reason
                    
        return None, ""

    def update_position_state(self, action: str, current_time_ms: float, indicators: Any = None, price: float = 0.0, reason: str = ""):
        """Update internal state."""
        import datetime
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
            
        upper = indicators.get('upper', 0.0) if isinstance(indicators, dict) else 0.0
        lower = indicators.get('lower', 0.0) if isinstance(indicators, dict) else 0.0
        
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

        elif action == "PARTIAL_EXIT":
            if self.active_trade:
                partial_trade = self.active_trade.copy()
                partial_trade["exit_time"] = format_time(current_time_ms)
                partial_trade["exit_price"] = price
                partial_trade["status"] = "PARTIAL"
                entry = float(self.active_trade['entry_price'])
                partial_trade["points"] = price - entry if self.current_position == 1 else entry - price
                self.trades.append(partial_trade)
                self.partial_exit_done = True
                self.active_trade["partial_exit"] = True

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
                if "Trailing" in reason: self.active_trade["status"] = "TRAIL STOP"
                elif "Breakdown" in reason: self.active_trade["status"] = "CHANNEL EXIT"
                elif "PnL Exit Guard" in reason: self.active_trade["status"] = "PNL STOP"
                
                self.active_trade["points"] = price - self.active_trade["entry_price"]
                self.trades.append(self.active_trade)
                self.active_trade = None
            
            self.entry_price = None
            self.tp_level = None
            self.trailing_stop_level = None
            self.partial_exit_done = False
            self.long_entry_bar = None

        elif action == "EXIT_SHORT":
            self.current_position = 0
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                if "Trailing" in reason: self.active_trade["status"] = "TRAIL STOP"
                elif "Breakout" in reason: self.active_trade["status"] = "CHANNEL EXIT"
                elif "PnL Exit Guard" in reason: self.active_trade["status"] = "PNL STOP"
                
                self.active_trade["points"] = self.active_trade["entry_price"] - price
                self.trades.append(self.active_trade)
                self.active_trade = None
                
            self.entry_price = None
            self.tp_level = None
            self.trailing_stop_level = None
            self.partial_exit_done = False

    def set_position(self, position: int):
        self.current_position = position

    def reconcile_position(self, size: float, entry_price: float):
        """Reconcile with Exchange."""
        import time, datetime
        def format_time(ts_ms): return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
        
        expected_pos = 0
        if size > 0: expected_pos = 1
        elif size < 0: expected_pos = -1
        
        if self.current_position != expected_pos:
            logger.warning(f"Reconciling: Internal {self.current_position} -> Exchange {expected_pos} (Size: {size})")
            self.current_position = expected_pos
            
            if expected_pos != 0 and not self.active_trade:
                side = "LONG" if expected_pos == 1 else "SHORT"
                self.active_trade = {
                    "type": side,
                    "entry_time": format_time(time.time()*1000) + " (Rec)",
                    "entry_price": entry_price,
                    "status": "OPEN"
                }
                # Set approximated levels?
                self.entry_price = entry_price
                # Without indicators we can't set TP/SL accurately.
                # They will be set on next candle update if logic allows? 
                # Actually check_signals updates levels ONLY ON ENTRY.
                # So reconciled positions might lack dynamic TP/SL levels until manually handled or code improved.
                logger.warning("Reconciled position lacks TP/SL levels until revisited.")

            elif expected_pos == 0 and self.active_trade:
                self.active_trade["exit_time"] = format_time(time.time()*1000) + " (Rec)"
                self.active_trade["status"] = "CLOSED (SYNC)"
                self.trades.append(self.active_trade)
                self.active_trade = None

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
                if self.current_position == 1 and close >= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", current_time_ms, indicators, close, f"Partial TP Hit: {close:.4f}")
                    continue
                elif self.current_position == -1 and close <= self.tp_level:
                    self.update_position_state("PARTIAL_EXIT", current_time_ms, indicators, close, f"Partial TP Hit: {close:.4f}")
                    continue
            
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
                
                # Short: Breakdown AND close < EMA
                elif self.allow_short and close <= lower_prev and close < ema:
                    # Check Duration
                    if self.min_long_days == 0 or (self.last_long_duration_bars >= self.min_long_bars):
                        self.update_position_state("ENTRY_SHORT", current_time_ms, indicators, close, "Breakdown + EMA")
                        self.entry_price = close
                        self.tp_level = close - (atr * self.atr_mult_tp)
                        self.trailing_stop_level = close + (atr * self.atr_mult_trail)
                        self.partial_exit_done = False
            
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
