import logging
from typing import Dict, Optional, Tuple, Any

import pandas as pd
import ta
import numpy as np
from core.config import get_config
from core.candle_utils import get_closed_candle_index

logger = logging.getLogger(__name__)

class DoubleDipRSIStrategy:
    """
    Double-Dip RSI Strategy for BTCUSD.
    
    Updated Logic:
    - Long Entry: RSI > 50
    - Long Exit: RSI < 40 OR Trailing Stop
    - Short Entry: RSI < 35 (with duration condition)
    - Short Exit: RSI > 35 OR Trailing Stop
    - Partial Exit (50%): Entry +/- (ATR * Multiplier)
    """
    
    def __init__(self):
        # Load Config
        config = get_config()
        cfg = config.settings.get("strategies", {}).get("double_dip_rsi", {})

        # Parameters
        self.rsi_period = cfg.get("rsi_period", 14)
        self.long_entry_level = cfg.get("long_entry_level", 50.0)
        self.long_exit_level = cfg.get("long_exit_level", 40.0)
        self.short_entry_level = cfg.get("short_entry_level", 35.0)
        self.short_exit_level = cfg.get("short_exit_level", 35.0)
        
        # New Parameters
        self.atr_length = cfg.get("atr_length", 14)
        self.atr_mult_tp = cfg.get("atr_mult_tp", 4.0)
        self.trail_atr_mult = cfg.get("trail_atr_mult", 4.0)
        self.partial_pct = cfg.get("partial_pct", 0.5)
        self.enable_partial_tp = cfg.get("enable_partial_tp", False)  # Disable partial exits by default
        
        self.indicator_label = "RSI"
        
        # Timeframe (set by runner, defaults to 1h)
        self.timeframe = "1h"

        # Duration Condition
        self.require_prev_long_min_duration = cfg.get("require_prev_long_min_duration", True)
        self.min_days_long = cfg.get("min_days_long", 2)
        
        # State
        self.last_long_entry_time = None
        self.last_long_duration = 0.0
        self.current_position = 0  # 1 for Long, -1 for Short, 0 for Flat
        
        # Dashboard/Live State
        self.last_rsi = 0.0
        self.last_atr = 0.0
        self.trailing_stop_level = None # Tracks active trailing stop price
        self.next_partial_target = None # Tracks next partial TP level
        
        
        # Trade History
        self.trades = [] # List of completed trades
        self.active_trade = None # Current active trade details
        
    def calculate_indicators(self, df: pd.DataFrame):
        """Calculate Technical Indicators (RSI, ATR)."""
        # Ensure we have enough data
        if len(df) < max(self.rsi_period, self.atr_length) + 1:
             return df
        
        df = df.copy() # Avoid SettingWithCopyWarning
        
        # RSI
        df['rsi'] = ta.momentum.rsi(df['close'], window=self.rsi_period)
        
        # ATR
        # ta library ATR might require high/low/close
        if 'high' in df.columns and 'low' in df.columns:
            df['atr'] = ta.volatility.average_true_range(
                high=df['high'], 
                low=df['low'], 
                close=df['close'], 
                window=self.atr_length
            )
        else:
            # Fallback if only close exists (approximate)
            df['atr'] = df['close'].diff().abs().rolling(window=self.atr_length).mean()
            
        return df

    def check_signals(self, df: pd.DataFrame, current_time_ms: float) -> Tuple[str, str]:
        """
        Check for entry/exit signals based on CLOSED candle data.
        
        Uses closed candle logic to match backtesting behavior and prevent
        false signals from developing candles. Trailing stops are checked
        against current price for real-time protection.
        
        Args:
            df: DataFrame containing candles (with calculated indicators)
            current_time_ms: Current timestamp in milliseconds
            
        Returns:
            Tuple[str, str]: (Action, Reason)
        """
        # 1. Update Indicators
        df = self.calculate_indicators(df)
        
        if len(df) < 5 or 'rsi' not in df.columns:
            return None, ""
        
        # 2. Get Closed Candle Index
        closed_idx = get_closed_candle_index(df, current_time_ms, self.timeframe)
        
        # Get both closed and current candle data
        closed_candle = df.iloc[closed_idx]
        current_candle = df.iloc[-1]  # For trailing stop price checks only
        
        # Safe access to CLOSED candle indicators (for entry/exit signals)
        try:
            closed_rsi = float(closed_candle['rsi'])
            closed_atr = float(closed_candle['atr'])
            closed_price = float(closed_candle['close'])
        except (KeyError, ValueError, TypeError):
            logger.warning("Missing indicator data in closed candle")
            return None, ""
        
        # Current candle data (for trailing stop hit detection)
        try:
            current_high = float(current_candle['high'])
            current_low = float(current_candle['low'])
            current_price = float(current_candle['close'])
        except (KeyError, ValueError, TypeError):
            logger.warning("Missing price data in current candle")
            return None, ""
        
        # Update dashboard values with closed candle data
        self.last_rsi = closed_rsi
        self.last_atr = closed_atr
        
        action = None
        reason = ""
        
        # --- LOGIC ---
        
        # ---------------------------------------------------------------------
        # LONG LOGIC
        # ---------------------------------------------------------------------
        if self.current_position == 1: # ALREADY LONG
            # 1. Partial Exit Logic
            # Target calculated from CLOSED candle ATR for stability
            entry_price = float(self.active_trade.get('entry_price', 0)) if self.active_trade else 0
            
            if self.enable_partial_tp and entry_price > 0 and not self.active_trade.get('partial_exit_done'):
                # Use CLOSED ATR for target calculation
                tp_target = entry_price + (closed_atr * self.atr_mult_tp)
                self.next_partial_target = tp_target
                # Check if current High hit TP (real-time check for better fills)
                if current_high >= tp_target:
                    action = "EXIT_LONG_PARTIAL"
                    reason = f"Partial TP Hit: Price {current_high:.2f} >= {tp_target:.2f} (Entry: {entry_price:.2f} + {self.atr_mult_tp}*ATR)"
                    return action, reason # Priority Return
            
            # 2. Trailing Stop Logic
            # Level calculated from CLOSED candle for stability
            # Hit detection uses current price for real-time protection
            
            # Calculate potential trail from CLOSED candle data
            potential_trail = closed_price - (closed_atr * self.trail_atr_mult)
            
            if self.trailing_stop_level is None:
                self.trailing_stop_level = potential_trail
            else:
                # Move UP only for Longs
                if potential_trail > self.trailing_stop_level:
                    self.trailing_stop_level = potential_trail
                    
            # Check Hit: Current Low <= Trail (real-time protection)
            if current_low <= self.trailing_stop_level:
                action = "EXIT_LONG"
                reason = f"Trailing Stop Hit: Low {current_low:.2f} <= {self.trailing_stop_level:.2f}"
                return action, reason
                
            # 3. RSI Exit (Hard Stop) - uses CLOSED candle RSI
            if closed_rsi < self.long_exit_level:
                action = "EXIT_LONG"
                reason = f"RSI Exit: {closed_rsi:.2f} < {self.long_exit_level}"
                return action, reason

        elif self.current_position == 0: # FLAT (Check Entries)
             # Entry signal based on CLOSED candle RSI
             if closed_rsi > self.long_entry_level:
                 action = "ENTRY_LONG"
                 reason = f"RSI Entry (Closed): {closed_rsi:.2f} > {self.long_entry_level}"
                 # Reset State
                 self.trailing_stop_level = None
                 self.next_partial_target = None 
                 return action, reason

        # ---------------------------------------------------------------------
        # SHORT LOGIC
        # ---------------------------------------------------------------------
        if self.current_position == -1: # ALREADY SHORT
            # 1. Partial Exit Logic
            # Target calculated from CLOSED candle ATR
            entry_price = float(self.active_trade.get('entry_price', 0)) if self.active_trade else 0
            
            if self.enable_partial_tp and entry_price > 0 and not self.active_trade.get('partial_exit_done'):
                # Use CLOSED ATR for target calculation
                tp_target = entry_price - (closed_atr * self.atr_mult_tp)
                self.next_partial_target = tp_target
                # Check if current Low hit TP (real-time check)
                if current_low <= tp_target:
                    action = "EXIT_SHORT_PARTIAL"
                    reason = f"Partial TP Hit: Price {current_low:.2f} <= {tp_target:.2f}"
                    return action, reason 
            
            # 2. Trailing Stop Logic
            # Level calculated from CLOSED candle, hit checked with current price
            potential_trail = closed_price + (closed_atr * self.trail_atr_mult)
            
            if self.trailing_stop_level is None:
                self.trailing_stop_level = potential_trail
            else:
                # Move DOWN only for Shorts
                if potential_trail < self.trailing_stop_level:
                    self.trailing_stop_level = potential_trail
            
            # Check Hit: Current High >= Trail (real-time protection)
            if current_high >= self.trailing_stop_level:
                 action = "EXIT_SHORT"
                 reason = f"Trailing Stop Hit: High {current_high:.2f} >= {self.trailing_stop_level:.2f}"
                 return action, reason

            # 3. RSI Exit - uses CLOSED candle RSI
            if closed_rsi > self.short_exit_level:
                action = "EXIT_SHORT"
                reason = f"RSI Exit (Closed): {closed_rsi:.2f} > {self.short_exit_level}"
                return action, reason
                
        elif self.current_position == 0: # FLAT (Check Short Entry)
            # Entry signal based on CLOSED candle RSI
            if closed_rsi < self.short_entry_level:
                 # Check Duration
                 short_allowed = True
                 if self.require_prev_long_min_duration:
                     ms_per_day = 24 * 60 * 60 * 1000
                     threshold = self.min_days_long * ms_per_day
                     if self.last_long_duration > 0 and self.last_long_duration < threshold:
                         short_allowed = False
                     # Assuming if last_long_duration is 0 (first run), we allow it or block?
                     # Code says: (last_long_duration >= threshold)
                     if self.last_long_duration == 0: 
                          # If strictly following "require duration", maybe block? 
                          # Pine: (lastLongDuration == 0) or ... -> Allows if 0
                          pass 
                          
                 if short_allowed:
                     action = "ENTRY_SHORT"
                     reason = f"RSI Entry (Closed): {closed_rsi:.2f} < {self.short_entry_level}"
                     self.trailing_stop_level = None
                     self.next_partial_target = None
                     return action, reason

        return None, ""

    def update_position_state(self, action: str, current_time_ms: float, current_rsi: float = 0.0, price: float = 0.0, reason: str = ""):
        """Update internal state based on executed action."""
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')

        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_long_entry_time = current_time_ms
            
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_rsi": current_rsi,
                "entry_price": price,
                "exit_time": None,
                "exit_rsi": None,
                "exit_price": None,
                "status": "OPEN",
                "partial_exit_done": False
            }
            
        elif action == "ENTRY_SHORT":
            self.current_position = -1
            self.last_long_duration = 0.0 # Reset per logic
            
            self.active_trade = {
                "type": "SHORT",
                "entry_time": format_time(current_time_ms),
                "entry_rsi": current_rsi,
                "entry_price": price,
                "exit_time": None,
                "exit_rsi": None,
                "exit_price": None,
                "status": "OPEN",
                "partial_exit_done": False
            }
            
        elif action == "EXIT_LONG_PARTIAL":
            if self.active_trade:
                self.active_trade['partial_exit_done'] = True
                self.next_partial_target = None # Clear target after hit
                
                # Log a "Partial" record in history
                partial_trade = self.active_trade.copy()
                partial_trade["exit_time"] = format_time(current_time_ms)
                partial_trade["exit_price"] = price
                partial_trade["exit_rsi"] = current_rsi
                partial_trade["status"] = "PARTIAL" # Distinct status for table
                partial_trade["points"] = price - float(self.active_trade['entry_price']) # Approx points
                
                self.trades.append(partial_trade)
                
        elif action == "EXIT_SHORT_PARTIAL":
             if self.active_trade:
                self.active_trade['partial_exit_done'] = True
                self.next_partial_target = None # Clear target after hit
                
                # Log a "Partial" record in history
                partial_trade = self.active_trade.copy()
                partial_trade["exit_time"] = format_time(current_time_ms)
                partial_trade["exit_price"] = price
                partial_trade["exit_rsi"] = current_rsi
                partial_trade["status"] = "PARTIAL"
                partial_trade["points"] = float(self.active_trade['entry_price']) - price
                
                self.trades.append(partial_trade)

        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.last_long_entry_time:
                self.last_long_duration = current_time_ms - self.last_long_entry_time
            self.last_long_entry_time = None
            self.trailing_stop_level = None
            self.next_partial_target = None
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_rsi"] = current_rsi
                self.active_trade["exit_price"] = price
                
                
                # Annotate Status
                if self.active_trade.get('partial_exit_done'):
                    status_note = "CLOSED (P)"
                else:
                    status_note = "CLOSED"
                
                # Calculate Points
                entry = float(self.active_trade['entry_price'])
                points = price - entry if self.current_position == 0 else entry - price # Wait, pos is 0 now. Logic: Long exit -> price - entry. Short exit -> entry - price.
                # But we reset current_position BEFORE this block?
                # Ah, we are in EXIT_LONG block, so it WAS Long.
                points = price - entry
                
                self.active_trade["points"] = points
                self.active_trade["status"] = status_note
                self.trades.append(self.active_trade)
                self.active_trade = None
            
        elif action == "EXIT_SHORT":
            self.current_position = 0
            self.trailing_stop_level = None
            self.next_partial_target = None
            
            if self.active_trade:
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_rsi"] = current_rsi
                self.active_trade["exit_price"] = price
                
                # Annotate Status
                if self.active_trade.get('partial_exit_done'):
                     status_note = "CLOSED (P)"
                else:
                     status_note = "CLOSED"

                # Calculate Points (Short: Entry - Exit)
                entry = float(self.active_trade['entry_price'])
                points = entry - price

                self.active_trade["points"] = points
                self.active_trade["status"] = status_note
                self.trades.append(self.active_trade)
                self.active_trade = None

            
    def set_position(self, position: int):
        """Manually set position state."""
        self.current_position = position

    def reconcile_position(self, size: float, entry_price: float):
        """Reconcile internal state with actual exchange position."""
        import time
        import datetime
        
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')

        current_ts = int(time.time() * 1000)
        
        # Determine expected position based on size
        expected_pos = 0
        if size > 0: expected_pos = 1
        if size < 0: expected_pos = -1
        
        if self.current_position != expected_pos:
            logger.warning(f"Reconciling: Internal {self.current_position} -> Exchange {expected_pos} (Size: {size})")
            self.current_position = expected_pos
            
            # Recover Trade Object if needed
            if expected_pos != 0 and not self.active_trade:
                side = "LONG" if expected_pos == 1 else "SHORT"
                self.active_trade = {
                    "type": side,
                    "entry_time": format_time(current_ts) + " (Rec)",
                    "entry_rsi": 0.0,
                    "entry_price": entry_price,
                    "exit_time": None,
                    "exit_rsi": None,
                    "exit_price": None,
                    "status": "OPEN",
                    "partial_exit_done": False # Assumption
                }
            elif expected_pos == 0 and self.active_trade:
                # Close mismatch
                self.active_trade["exit_time"] = format_time(current_ts) + " (Rec)"
                self.active_trade["status"] = "CLOSED"
                self.trades.append(self.active_trade)
                self.active_trade = None

    def run_backtest(self, df: pd.DataFrame):
        """Run backtest on historical data."""
        self.trades = []
        self.active_trade = None
        self.current_position = 0
        self.last_long_duration = 0.0
        
        if df.empty: return

        # Indicators
        df = self.calculate_indicators(df)
        
        # Simulate
        for i in range(len(df)):
            if i < max(self.rsi_period, self.atr_length) + 1: continue
            
            # Slice up to i for "current" view (inefficient but safe) or just use logic row-by-row
            # Strategy checks signals on "current_rsi" usually but now needs full df or at least enough rows
            # check_signals expects 'df' and uses .iloc[-1]
            
            subset = df.iloc[:i+1] # Simulate live feed up to i
            current_time = float(df['time'].iloc[i]) * 1000
            current_price = float(df['close'].iloc[i])
            current_rsi = float(df['rsi'].iloc[i])
            
            action, reason = self.check_signals(subset, current_time)
            
            if action:
                self.update_position_state(action, current_time, current_rsi, current_price, reason=reason)
                
        logger.info(f"Backtest complete. Trades: {len(self.trades)}")

