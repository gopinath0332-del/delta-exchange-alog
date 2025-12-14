import pytest
import pandas as pd
from strategies.double_dip_rsi import DoubleDipRSIStrategy

class TestDoubleDipRSIStrategy:
    def test_rsi_calculation(self):
        strategy = DoubleDipRSIStrategy()
        # Create a series of prices
        prices = pd.Series([100, 101, 102, 103, 104, 105, 104, 103, 102, 101, 100] * 5)
        rsi, prev_rsi = strategy.calculate_rsi(prices)
        assert isinstance(rsi, float)
        assert isinstance(prev_rsi, float)
        assert 0 <= rsi <= 100

    def test_long_entry_signal(self):
        strategy = DoubleDipRSIStrategy()
        current_time = 1000
        
        # Test Entry Long: RSI > 50 and Flat
        strategy.current_position = 0
        action, reason = strategy.check_signals(55.0, current_time)
        assert action == "ENTRY_LONG"
        
        # Update state
        strategy.update_position_state(action, current_time)
        assert strategy.current_position == 1

    def test_short_entry_signal_blocked(self):
        strategy = DoubleDipRSIStrategy()
        current_time = 1000
        
        # Simulate a short signal (RSI < 35) but prevent it due to no prior long duration check?
        # Default strategy logic: allowed if last_long_duration == 0 (initial)
        
        # Manually set a short duration for last long (e.g., 1 hour) which matches min_days_long=2 requirement?
        # Wait, requirement is >= 2 days. So 1 hour should BLOCK it.
        # NOW: Even 0 (no history) should block it.
        strategy.last_long_duration = 0 
        strategy.current_position = 0
        
        # Trigger Short Signal
        action, reason = strategy.check_signals(30.0, current_time)
        assert action is None # Should be blocked (conservative default)
        
    def test_short_entry_signal_allowed(self):
        strategy = DoubleDipRSIStrategy()
        current_time = 1000
        
        # Set duration > 2 days
        strategy.last_long_duration = 3 * 24 * 3600 * 1000 
        strategy.current_position = 0
        
        action, reason = strategy.check_signals(30.0, current_time)
        assert action == "ENTRY_SHORT"

if __name__ == "__main__":
    pytest.main([__file__])
