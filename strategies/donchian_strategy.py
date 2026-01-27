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
    Donchian Channel Strategy (Gold Both directions) - Long Only Mode
    
    Strategy Logic:
    - Long Entry: Close breaks above upper Donchian channel (highest high over enter_period)
    - Partial TP: 50% exit at entry + (ATR × atr_mult_tp) [if enabled]
    - Trailing Stop: Dynamically updated at close - (ATR × atr_mult_trail)
    - Long Exit: Close breaks below lower Donchian channel (lowest low over exit_period) OR trailing stop hit
    
    Parameters (from Pine Script):
    - Enter Channel Period: 20
    - Exit Channel Period: 10
    - ATR Period: 16
    - ATR TP Multiplier: 4.0
    - ATR Trailing SL Multiplier: 2.0
    - Enable Partial TP: false (disabled by default per screenshot)
    - Partial Percentage: 0.5 (50%)
    - Bars per Day: 24 (for 1H timeframe)
    - Minimum Long Duration: 2 days
    """
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("donchian_channel", {})

        # Parameters
        self.enter_period = cfg.get("enter_period", 20)
        self.exit_period = cfg.get("exit_period", 10)
        self.atr_period = cfg.get("atr_period", 16)
        self.atr_mult_tp = cfg.get("atr_mult_tp", 4.0)
        self.atr_mult_trail = cfg.get("atr_mult_trail", 2.0)
        self.enable_partial_tp = cfg.get("enable_partial_tp", False)
        self.partial_pct = cfg.get("partial_pct", 0.5)
        self.bars_per_day = cfg.get("bars_per_day", 24)
        self.min_long_days = cfg.get("min_long_days", 2)
        self.min_long_bars = self.bars_per_day * self.min_long_days
        
        self.indicator_label = "Donchian"
        
        # Timeframe (set by runner, defaults to 1h)
        self.timeframe = "1h"
        
        # State
        self.current_position = 0  # 1 for Long, 0 for Flat
        self.last_entry_price = 0.0
        self.entry_price = None  # Entry price for current position
        self.entry_bar_index = None  # Bar index at entry
        self.tp_level = None  # Take profit level
        self.trailing_stop_level = None  # Trailing stop level
        self.partial_exit_done = False  # Flag for partial exit
        
        # Indicator Cache (for dashboard)
        self.last_upper_channel = 0.0
        self.last_lower_channel = 0.0
        self.last_atr = 0.0
        
        # Trade History
        self.trades = []
        self.active_trade = None
        
        # For closed candle tracking
        self.last_closed_time_str = "-"
        self.last_closed_upper = 0.0
        self.last_closed_lower = 0.0
        
    def calculate_indicators(self, df: pd.DataFrame, current_time: Optional[float] = None) -> Tuple[float, float, float]:
        """
        Calculate Donchian Channels (upper, lower) and ATR for the given dataframe.
        Expected columns: 'close', 'high', 'low'
        
        Returns:
            Tuple[float, float, float]: (upper_channel, lower_channel, atr)
        """
        try:
            # Ensure we have enough data
            if len(df) < max(self.enter_period, self.exit_period, self.atr_period) + 1:
                return 0.0, 0.0, 0.0
                
            if current_time is None:
                import time
                current_time = time.time()
                
            # Donchian Channels
            # Upper channel = highest high over enter_period
            upper_channel = df['high'].rolling(window=self.enter_period).max()
            
            # Lower channel = lowest low over exit_period
            lower_channel = df['low'].rolling(window=self.exit_period).min()
            
            # ATR using EMA (ta library uses SMA by default, but Pine Script uses EMA)
            # Calculate True Range manually
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            
            # EMA of true range
            atr_series = true_range.ewm(span=self.atr_period, adjust=False).mean()
            
            current_upper = upper_channel.iloc[-1]
            current_lower = lower_channel.iloc[-1]
            current_atr = atr_series.iloc[-1]
            
            # Cache for dashboard (Live)
            self.last_upper_channel = current_upper
            self.last_lower_channel = current_lower
            self.last_atr = current_atr
            
            # Dynamic Closed Candle Logic (for 1-hour candles)
            last_candle_ts = df['time'].iloc[-1]
            # Handle potential ms timestamp
            if last_candle_ts > 1e11: 
                last_candle_ts /= 1000
            
            diff = current_time - last_candle_ts
            
            # If diff >= 3600 (1h), the last candle IS the closed candle (new one hasn't appeared)
            # If diff < 3600, the last candle is developing, so -2 is the closed one
            closed_idx = -1 if diff >= 3600 else -2
            
            # Cache Last Closed Candle
            if len(df) >= abs(closed_idx):
                import datetime
                ts = df['time'].iloc[closed_idx]
                if ts > 1e11: 
                    ts /= 1000
                self.last_closed_time_str = datetime.datetime.fromtimestamp(ts).strftime('%H:%M')
                self.last_closed_upper = upper_channel.iloc[closed_idx]
                self.last_closed_lower = lower_channel.iloc[closed_idx]
            else:
                self.last_closed_time_str = "-"
                self.last_closed_upper = 0.0
                self.last_closed_lower = 0.0
            
            return current_upper, current_lower, current_atr
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return 0.0, 0.0, 0.0

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[Optional[str], str]:
        """
        Check for entry/exit signals based on CLOSED candle data.
        
        Uses closed candle logic to match backtesting behavior and prevent
        false signals from developing candles. Trailing stops are checked
        against current price.
        
        Args:
            df: DataFrame with OHLC data
            current_time_ms: Current timestamp in milliseconds
            
        Returns:
            Tuple[str, str]: (Action, Reason)
        """
        if df.empty:
            return None, ""
            
        if len(df) < max(self.enter_period, self.exit_period, self.atr_period) + 2:
            return None, ""

        # Get indicators (Pass current time for dynamic logic)
        current_time_s = current_time_ms / 1000.0
        upper, lower, atr = self.calculate_indicators(df, current_time=current_time_s)
        
        # Determine which index to use for SIGNALS
        # Same logic as calculate_indicators
        last_candle_ts = df['time'].iloc[-1]
        if last_candle_ts > 1e11: 
            last_candle_ts /= 1000
        
        diff = current_time_s - last_candle_ts
        closed_idx = -1 if diff >= 3600 else -2
        
        if closed_idx == -1:
            logger.debug(f"Using Index -1 as Closed Candle (Diff: {diff:.0f}s)")
        
        # We need the closed price at the determined index
        close_closed = df['close'].iloc[closed_idx]
        upper_closed = self.last_closed_upper
        lower_closed = self.last_closed_lower
        
        # Get previous candle's upper channel for entry signal
        prev_idx = closed_idx - 1
        
        # Calculate upper channel for previous candle
        upper_channel_series = df['high'].rolling(window=self.enter_period).max()
        lower_channel_series = df['low'].rolling(window=self.exit_period).min()
        upper_prev = upper_channel_series.iloc[prev_idx]
        lower_prev = lower_channel_series.iloc[prev_idx]
        
        # Get current price for stop/tp checks
        current_price = df['close'].iloc[-1]
        
        action = None
        reason = ""
        
        # --- Trading Logic ---
        
        # Update Trailing Stop if in position
        if self.current_position == 1 and self.trailing_stop_level is not None:
            new_stop = current_price - (atr * self.atr_mult_trail)
            if new_stop > self.trailing_stop_level:
                self.trailing_stop_level = new_stop
                logger.debug(f"Updated trailing stop to {new_stop:.4f}")
        
        # Check Trailing Stop Hit (uses current price)
        if self.current_position == 1 and self.trailing_stop_level is not None:
            if current_price <= self.trailing_stop_level:
                action = "EXIT_LONG"
                reason = f"Trailing SL Hit: Price {current_price:.4f} <= Stop {self.trailing_stop_level:.4f}"
                return action, reason
        
        # Check Partial TP (if enabled, uses current price)
        if self.enable_partial_tp and self.current_position == 1 and not self.partial_exit_done and self.tp_level is not None:
            if current_price >= self.tp_level:
                action = "PARTIAL_EXIT"
                reason = f"Partial TP Hit: Price {current_price:.4f} >= TP {self.tp_level:.4f}"
                return action, reason
        
        # Entry Long
        # Condition: Close breaks above upper channel (close >= upper[prev])
        if self.current_position == 0:
            # Breakout: current closed candle >= previous upper channel
            breakout = close_closed >= upper_prev
            
            if breakout:
                action = "ENTRY_LONG"
                reason = f"Breakout: Close {close_closed:.4f} >= Upper[prev] {upper_prev:.4f}"
                
                # Set TP and Trailing Stop levels
                # Calculate ATR at closed index
                high_low = df['high'] - df['low']
                high_close = np.abs(df['high'] - df['close'].shift())
                low_close = np.abs(df['low'] - df['close'].shift())
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr_series = true_range.ewm(span=self.atr_period, adjust=False).mean()
                atr_closed = atr_series.iloc[closed_idx]
                
                self.entry_price = close_closed
                self.tp_level = close_closed + (atr_closed * self.atr_mult_tp)
                self.trailing_stop_level = close_closed - (atr_closed * self.atr_mult_trail)
                self.partial_exit_done = False
                
        # Exit Long
        # Condition: Close breaks below lower channel (close <= lower[prev]) OR trailing stop hit
        elif self.current_position == 1:
            # Breakdown: current closed candle <= previous lower channel
            breakdown = close_closed <= lower_prev
            
            if breakdown:
                action = "EXIT_LONG"
                reason = f"Breakdown: Close {close_closed:.4f} <= Lower[prev] {lower_prev:.4f}"
                
        return action, reason

    def update_position_state(self, action: str, current_time_ms: float, indicators: Any = None, price: float = 0.0, reason: str = ""):
        """
        Update internal state based on executed action.
        
        Args:
            action: Action taken (ENTRY_LONG, PARTIAL_EXIT, EXIT_LONG)
            current_time_ms: Current timestamp in milliseconds
            indicators: Dictionary with indicator values or legacy float
            price: Execution price
            reason: Reason for the action
        """
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
            
        # Handle indicators argument
        upper = 0.0
        lower = 0.0
        atr = 0.0
        if isinstance(indicators, dict):
            upper = indicators.get('upper', 0.0)
            lower = indicators.get('lower', 0.0)
            atr = indicators.get('atr', 0.0)
        
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_entry_price = price
            
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_price": price,
                "entry_upper": upper,
                "entry_lower": lower,
                "exit_time": None,
                "exit_price": None,
                "exit_upper": None,
                "exit_lower": None,
                "status": "OPEN",
                "partial_exit": False,
                "logs": []
            }
            
        elif action == "PARTIAL_EXIT":
            # Record partial exit in trade history
            if self.active_trade:
                # Create a copy for the partial exit record
                partial_trade = self.active_trade.copy()
                partial_trade["exit_time"] = format_time(current_time_ms)
                partial_trade["exit_price"] = price
                partial_trade["exit_upper"] = upper
                partial_trade["exit_lower"] = lower
                partial_trade["status"] = "PARTIAL"
                partial_trade["points"] = price - partial_trade["entry_price"]
                self.trades.append(partial_trade)
                
                # Mark partial exit done
                self.partial_exit_done = True
                self.active_trade["partial_exit"] = True
                
        elif action == "EXIT_LONG":
            self.current_position = 0
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_price"] = price
                self.active_trade["exit_upper"] = upper
                self.active_trade["exit_lower"] = lower
                
                # Determine exit reason for status
                if "Trailing SL" in reason or "Trailing Stop" in reason:
                    self.active_trade["status"] = "TRAIL STOP"
                elif "Breakdown" in reason or "Lower" in reason:
                    self.active_trade["status"] = "CHANNEL EXIT"
                else:
                    self.active_trade["status"] = "CLOSED"
                    
                self.active_trade["points"] = price - self.active_trade["entry_price"]
                self.trades.append(self.active_trade)
                self.active_trade = None
            
            # Reset levels
            self.entry_price = None
            self.entry_bar_index = None
            self.tp_level = None
            self.trailing_stop_level = None
            self.partial_exit_done = False

    def set_position(self, position: int):
        """Manually set position state."""
        self.current_position = position

    def reconcile_position(self, size: float, entry_price: float):
        """
        Reconcile internal state with actual exchange position.
        
        Args:
            size: Position size from exchange
            entry_price: Entry price from exchange
        """
        import time
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')
        
        if size > 0:
            if self.current_position != 1:
                self.current_position = 1
                self.last_entry_price = entry_price
                self.entry_price = entry_price
                logger.info(f"Reconciled state to LONG (Size: {size})")
        elif size == 0:
            if self.current_position != 0:
                self.current_position = 0
                logger.info("Reconciled state to FLAT")
                
            # Ensure active_trade is closed if we are actually FLAT
            if self.active_trade:
                current_timestamp = time.time() * 1000
                formatted_time = format_time(current_timestamp)
                
                logger.info("Closing phantom active_trade via Reconciliation")
                self.active_trade["exit_time"] = f"{formatted_time} (Reconciled)"
                self.active_trade["exit_price"] = 0.0  # Unknown
                self.active_trade["exit_upper"] = 0.0
                self.active_trade["exit_lower"] = 0.0
                self.active_trade["status"] = "CLOSED (SYNC)"
                self.trades.append(self.active_trade)
                self.active_trade = None

    def run_backtest(self, df: pd.DataFrame):
        """
        Run backtest on historical data.
        
        Args:
            df: DataFrame with OHLC data and time column
        """
        logger.info("Starting Donchian Channel backtest...")
        self.trades = []
        self.current_position = 0
        self.active_trade = None
        self.entry_price = None
        self.entry_bar_index = None
        self.tp_level = None
        self.trailing_stop_level = None
        self.partial_exit_done = False
        
        if df.empty: 
            return

        # Pre-calculate indicators for speed
        upper_channel = df['high'].rolling(window=self.enter_period).max()
        lower_channel = df['low'].rolling(window=self.exit_period).min()
        
        # Calculate ATR with EMA
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr_series = true_range.ewm(span=self.atr_period, adjust=False).mean()
        
        for i in range(len(df)):
            if i < max(self.enter_period, self.exit_period, self.atr_period) + 1: 
                continue
            
            current_time_s = df['time'].iloc[i]
            current_time_ms = current_time_s * 1000
            
            close = df['close'].iloc[i]
            upper = upper_channel.iloc[i]
            lower = lower_channel.iloc[i]
            atr = atr_series.iloc[i]
            
            if pd.isna(upper) or pd.isna(lower) or pd.isna(atr): 
                continue
            
            # Update Trailing Stop
            if self.current_position == 1 and self.trailing_stop_level is not None:
                new_stop = close - (atr * self.atr_mult_trail)
                if new_stop > self.trailing_stop_level:
                    self.trailing_stop_level = new_stop
            
            # Check Trailing Stop Hit
            if self.current_position == 1 and self.trailing_stop_level is not None:
                if close <= self.trailing_stop_level:
                    indicators = {'upper': upper, 'lower': lower, 'atr': atr}
                    self.update_position_state("EXIT_LONG", current_time_ms, indicators, close, "Trailing SL Hit")
                    continue
            
            # Check Partial TP (if enabled)
            if self.enable_partial_tp and self.current_position == 1 and not self.partial_exit_done and self.tp_level is not None:
                if close >= self.tp_level:
                    indicators = {'upper': upper, 'lower': lower, 'atr': atr}
                    self.update_position_state("PARTIAL_EXIT", current_time_ms, indicators, close, "Partial TP Hit")
                    # Continue to check for other signals
            
            # --- Trading Logic ---
            action = None
            
            # Use previous candle's channel for breakout/breakdown detection
            upper_prev = upper_channel.iloc[i-1]
            lower_prev = lower_channel.iloc[i-1]
            
            if self.current_position == 0:
                # Entry: Close breaks above upper channel
                if close >= upper_prev:
                    action = "ENTRY_LONG"
                    # Set levels
                    self.entry_price = close
                    self.entry_bar_index = i
                    self.tp_level = close + (atr * self.atr_mult_tp)
                    self.trailing_stop_level = close - (atr * self.atr_mult_trail)
                    self.partial_exit_done = False
                    
            elif self.current_position == 1:
                # Exit: Close breaks below lower channel
                if close <= lower_prev:
                    action = "EXIT_LONG"
            
            if action:
                indicators = {'upper': upper, 'lower': lower, 'atr': atr}
                reason = "Breakout" if action == "ENTRY_LONG" else "Breakdown"
                self.update_position_state(action, current_time_ms, indicators, close, reason)
                
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")
