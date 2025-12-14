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
        
    def calculate_rsi(self, closes: pd.Series) -> float:
        """Calculate RSI for the given series of close prices."""
        try:
            rsi_series = ta.momentum.rsi(closes, window=self.rsi_period)
            return rsi_series.iloc[-1]
        except Exception as e:
            logger.error(f"Error calculating RSI: {e}")
            return 0.0

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
        
        short_allowed = True
        if self.require_prev_long_min_duration:
            # Check duration of last long
            ms_per_day = 24 * 60 * 60 * 1000
            threshold = self.min_days_long * ms_per_day
            # Allowed if no prior long OR duration >= threshold
            short_allowed = (self.last_long_duration == 0) or (self.last_long_duration >= threshold)
        
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

    def update_position_state(self, action: str, current_time_ms: float):
        """Update internal state based on executed action."""
        if action == "ENTRY_LONG":
            self.current_position = 1
            self.last_long_entry_time = current_time_ms
            
        elif action == "EXIT_LONG":
            self.current_position = 0
            if self.last_long_entry_time:
                self.last_long_duration = current_time_ms - self.last_long_entry_time
            self.last_long_entry_time = None
            
        elif action == "ENTRY_SHORT":
            self.current_position = -1
            
        elif action == "EXIT_SHORT":
            self.current_position = 0
            
    def set_position(self, position: int):
        """Manually set position state (e.g. from API sync)."""
        self.current_position = position
