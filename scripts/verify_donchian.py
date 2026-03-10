import sys
import os
import pandas as pd
import numpy as np

# Add project root to path
sys.path.append('/Users/admin/Projects/delta-exchange-alog')

from unittest.mock import MagicMock, patch
from strategies.donchian_strategy import DonchianChannelStrategy

# Mock Data: 20 candles with a huge low wick in one candle
data = {
    'open':  [100.0] * 20,
    'high':  [102.0] * 20,
    'low':   [98.0] * 20,
    'close': [100.0] * 20
}
# Add a volatile wick at index 10 (well within the 10-period exit window for index 19)
data['low'][10] = 80.0
data['close'][10] = 99.0 # Body is 99-100

df = pd.DataFrame(data)

def run_test(channel_source):
    cfg = {
        "enter_period": 20,
        "exit_period": 10,
        "atr_period": 16,
        "atr_mult_tp": 4.0,
        "atr_mult_trail": 2.0,
        "channel_source": channel_source
    }
    
    mock_config = MagicMock()
    mock_config.settings = {"strategies": {"donchian_channel": cfg}}
    
    with patch('strategies.donchian_strategy.get_config', return_value=mock_config):
        strategy = DonchianChannelStrategy()
        # Mock 'time' column for indicator calculation (needed for closed candle logic)
        df['time'] = 0 # Dummy values
        upper, lower, atr, ema = strategy.calculate_indicators(df)
        return lower

print("Running verification for Donchian Channel Smoothing Fix...")

# Test 1: Wick mode
lower_wick = run_test("wick")
print(f"Lower (Wick mode, expected 80.0): {lower_wick}")

# Test 2: Body mode
lower_body = run_test("body")
print(f"Lower (Body mode, expected 98.0): {lower_body}")

# Validation logic
if lower_wick == 80.0 and lower_body == 98.0:
    print("\n✅ Verification SUCCESSFUL!")
    print("Standard wicks are correctly filtered in 'body' mode.")
else:
    print(f"\n❌ Verification FAILED! Wick: {lower_wick}, Body: {lower_body}")
    sys.exit(1)

# Validation logic
if lower_wick == 80.0 and lower_body == 98.0:
    print("\n✅ Verification SUCCESSFUL!")
    print("Standard wicks are correctly filtered in 'body' mode.")
else:
    print("\n❌ Verification FAILED!")
    sys.exit(1)
