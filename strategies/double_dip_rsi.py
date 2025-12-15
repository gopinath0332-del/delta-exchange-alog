import logging
from typing import Dict, Optional, Tuple

import pandas as pd
import ta

logger = logging.getLogger(__name__)

class DoubleDipRSIStrategy:
    """
    Double-Dip RSI Strategy for BTCUSD.
    
    Logic based on Pine Script:
    - Long Entry: RSI > 50
    - Long Exit: RSI < 40
    - Short Entry: RSI < 35 (with duration condition)
    - Short Exit: RSI > 35
    """
    
    def __init__(self):
        # Parameters
        self.rsi_period = 14
        self.long_entry_level = 50.0
        self.long_exit_level = 40.0
        self.short_entry_level = 35.0
        self.short_exit_level = 35.0
        
        # Duration Condition
        self.require_prev_long_min_duration = True
        self.min_days_long = 2
        
        # State
        self.last_long_entry_time = None
        self.last_long_duration = 0.0
        self.current_position = 0  # 1 for Long, -1 for Short, 0 for Flat
        self.last_rsi = 0.0
        
        # Trade History
        self.trades = [] # List of completed trades
        self.active_trade = None # Current active trade details
        
    def calculate_rsi(self, closes: pd.Series) -> Tuple[float, float]:
        """
        Calculate RSI for the given series of close prices.
        
        Returns:
            Tuple[float, float]: (Current RSI, Previous RSI)
        """
        try:
            rsi_series = ta.momentum.rsi(closes, window=self.rsi_period)
            if len(rsi_series) < 2:
                return rsi_series.iloc[-1] if len(rsi_series) > 0 else 0.0, 0.0
            return rsi_series.iloc[-1], rsi_series.iloc[-2]
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return 0.0, 0.0

    def check_signals(self, current_rsi: float, current_time_ms: float) -> Tuple[str, str]:
        """
        Check for entry/exit signals based on current RSI and state.
        
        Returns:
            Tuple[str, str]: (Action, Reason)
            Action: "ENTRY_LONG", "EXIT_LONG", "ENTRY_SHORT", "EXIT_SHORT", or None
        """
        self.last_rsi = current_rsi
        action = None
        reason = ""
        
        # --- Logic from Pine Script ---
        
        # Long Signal: crossover(rsi, longEntryLevel) -> RSI crosses above 50
        # Simplification: RSI > 50 (and wasn't already long, handled by caller or state check)
        # Note: Pine 'crossover' implies it just happened. Here we might check continuous condition
        # or rely on the caller to provide previous RSI. For simplicity, we check absolute levels 
        # combined with "not in position" state.
        
        # Long Entry
        if self.current_position <= 0: # Flat or Short
            if current_rsi > self.long_entry_level:
                action = "ENTRY_LONG"
                reason = f"RSI {current_rsi:.2f} > {self.long_entry_level}"

        # Long Exit
        if self.current_position > 0: # In Long
             if current_rsi < self.long_exit_level:
                action = "EXIT_LONG"
                reason = f"RSI {current_rsi:.2f} < {self.long_exit_level}"
        
        # Short Entry Logic
        # shortSignal = crossunder(rsi, shortEntryLevel) -> RSI crosses below 35
        short_signal = current_rsi < self.short_entry_level
        
        if self.require_prev_long_min_duration:
            # Check duration of last long
            ms_per_day = 24 * 60 * 60 * 1000
            threshold = self.min_days_long * ms_per_day
            
            # Logic: Short allowed ONLY if Last long duration >= threshold
            # If last_long_duration is 0 (no history), we BLOCK shorts to be conservative 
            # and match the "Wait 2 days" constraint safety.
            short_allowed = (self.last_long_duration >= threshold) and (self.last_long_duration > 0)
            
            if short_signal:
                days_duration = self.last_long_duration / ms_per_day
                logger.info(f"DEBUG: Short Signal Check | RSI={current_rsi:.2f} | LastLongDur={days_duration:.2f}d | Allowed={short_allowed}")

            if not short_allowed:
                 # Optional: Log reason if needed, but for now we just block
                 reason = f"Blocked: Prev Long duration {self.last_long_duration/ms_per_day:.2f}d < {self.min_days_long}d"
                 
        if self.current_position >= 0: # Flat or Long
            if short_signal and short_allowed:
                action = "ENTRY_SHORT"
                reason = f"RSI {current_rsi:.2f} < {self.short_entry_level} (Duration OK)"
            elif short_signal and not short_allowed:
                 # Log/Reason but don't act? or just ignore
                 pass
                 
        # Short Exit
        if self.current_position < 0: # In Short
            if current_rsi > self.short_exit_level:
                action = "EXIT_SHORT"
                reason = f"RSI {current_rsi:.2f} > {self.short_exit_level}"
                
        return action, reason

    def update_position_state(self, action: str, current_time_ms: float, current_rsi: float = 0.0, price: float = 0.0):
        """Update internal state based on executed action."""
        import datetime
        
        # Helper to format time
        def format_time(ts_ms):
            return datetime.datetime.fromtimestamp(ts_ms/1000).strftime('%d-%m-%y %H:%M')

        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_long_entry_time = current_time_ms
            
            # Start New Trade
            self.active_trade = {
                "type": "LONG",
                "entry_time": format_time(current_time_ms),
                "entry_rsi": current_rsi,
                "entry_price": price,
                "exit_time": "-",
                "exit_rsi": "-",
                "exit_price": "-",
                "status": "OPEN"
            }
            
        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.last_long_entry_time:
                self.last_long_duration = current_time_ms - self.last_long_entry_time
            self.last_long_entry_time = None
            
            # Close Trade
            if self.active_trade and self.active_trade["type"] == "LONG":
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_rsi"] = current_rsi
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                self.trades.append(self.active_trade)
                self.active_trade = None
            
        elif action == "ENTRY_SHORT":
            self.current_position = -1
            
            # Reset duration so we don't allow multiple shorts from one long duration
            self.last_long_duration = 0.0
            
            # Start New Trade
            self.active_trade = {
                "type": "SHORT",
                "entry_time": format_time(current_time_ms),
                "entry_rsi": current_rsi,
                "entry_price": price,
                "exit_time": "-",
                "exit_rsi": "-",
                "exit_price": "-",
                "status": "OPEN"
            }
            
        elif action == "EXIT_SHORT":
            self.current_position = 0
            
            # Close Trade
            if self.active_trade and self.active_trade["type"] == "SHORT":
                self.active_trade["exit_time"] = format_time(current_time_ms)
                self.active_trade["exit_rsi"] = current_rsi
                self.active_trade["exit_price"] = price
                self.active_trade["status"] = "CLOSED"
                self.trades.append(self.active_trade)
                self.active_trade = None
            
    def set_position(self, position: int):
        """Manually set position state (e.g. from API sync)."""
        self.current_position = position

    def run_backtest(self, df: pd.DataFrame):
        """
        Run backtest on historical data to check conditions/populate history.
        Assumes df has 'close' and 'time' columns. dates in ascending order.
        """
        import ta
        
        # Reset State for clean backtest? 
        # Or just clear trades/history but keep config?
        self.trades = []
        self.active_trade = None
        self.current_position = 0
        self.last_long_duration = 0.0
        self.last_long_entry_time = None
        
        if df.empty:
            return

        # Calculate RSI for entire series
        rsi_series = ta.momentum.rsi(df['close'], window=self.rsi_period)
        
        # Iterate through history
        # We need at least RSI_PERIOD data points
        for i in range(len(df)):
            if i < self.rsi_period:
                continue
                
            current_rsi = rsi_series.iloc[i]
            if pd.isna(current_rsi):
                continue
                
            current_price = float(df['close'].iloc[i])
                
            # Convert timestamp to ms if needed (DataFrame time usually string or datetime object?)
            # API returns ISO strings usually, but main_window parsing might have kept them?
            # main_window logic: df = pd.DataFrame(candles) -> candles has 'time' (int unix timestamp in seconds?)?
            # Let's check main_window.py... line 614: end_time = int(time.time())...
            # Delta API returns candles with 'time' as Unix timestamp (seconds).
            # So df['time'] is seconds. Strategy expects ms for update_position_state?
            # update_position_state uses ms (current_time_ms).
            
            # Correction: API candles time is usually Unix Seconds.
            # verify main_window sends time.time() * 1000 in LIVE loop.
            # So backtest should scale seconds to ms.
            
            current_time_s = df['time'].iloc[i]
            current_time_ms = current_time_s * 1000
            
            # Check Signals
            # Strategy stores state. check_signals reads state.
            # But check_signals return action, doesn't update state.
            # So we simulate the loop: check -> update.
            
            action, _ = self.check_signals(current_rsi, current_time_ms)
            
            if action:
                self.update_position_state(action, current_time_ms, current_rsi, current_price)
                
        logger.info(f"Backtest complete. Trades found: {len(self.trades)}")
