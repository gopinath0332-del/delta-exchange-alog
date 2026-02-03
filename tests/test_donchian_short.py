
import unittest
import pandas as pd
import numpy as np
import time
from unittest.mock import MagicMock, patch
from strategies.donchian_strategy import DonchianChannelStrategy
from core.config import Config

class TestDonchianShort(unittest.TestCase):
    def setUp(self):
        # Mock Config to return "Both" mode
        self.config_patcher = patch('strategies.donchian_strategy.get_config')
        self.mock_get_config = self.config_patcher.start()
        
        self.mock_config_instance = MagicMock()
        self.mock_config_instance.settings = {
            "strategies": {
                "donchian_channel": {
                    "trade_mode": "Both",
                    "enter_period": 20,
                    "exit_period": 10,
                    "atr_period": 14,
                    "atr_mult_tp": 4.0,
                    "atr_mult_trail": 2.0,
                    "min_long_days": 0 # Disable wait for test simplicity
                }
            }
        }
        self.mock_get_config.return_value = self.mock_config_instance
        
        self.strategy = DonchianChannelStrategy()

    def tearDown(self):
        self.config_patcher.stop()

    def create_mock_df(self, length=50, price_trend="flat"):
        # Create a dataframe with enough length for indicators
        dates = pd.date_range(end=pd.Timestamp.now(), periods=length, freq='1h')
        times = [d.timestamp() * 1000 for d in dates] # ms
        
        # Base price
        prices = np.full(length, 100.0)
        
        if price_trend == "down":
            # Sharp drop at end to trigger Breakdown
            prices[-5:] = [99, 98, 97, 80, 75] 
        elif price_trend == "up":
             # Sharp rise
             prices[-5:] = [101, 102, 103, 120, 125]
             
        df = pd.DataFrame({
            'time': times,
            'open': prices,
            'high': prices + 1,
            'low': prices - 1,
            'close': prices
        })
        
        # Adjust time to ms
        df['time'] = df['time'].astype(float)
        
        return df

    def test_short_entry_signal(self):
        # Setup: Flat then Drop below lower channel
        df = self.create_mock_df(length=60, price_trend="flat")
        
        # Force a lower channel breach
        # Enter period 20, Exit period 10
        # Make previous lows 90, now we drop to 80
        
        # Manually construct scenario
        # 0-40: Range 100-110
        # 41-59: Drop to 85 (Lower channel will be around 100 if we keep lows there)
        
        # Let's just mock exact needed values for simplicity or use big price moves
        # Create stable channel
        df['high'] = 110.0
        df['low'] = 90.0
        df['close'] = 100.0
        
        # Ensure we have enough history
        # At index -2 (closed candle), we want a breakdown
        
        # Make prev candles (before -2) define lower channel at 90
        # At -2, Close is 80 (Breakdown)
        
        df.loc[df.index[-2], 'close'] = 80.0
        df.loc[df.index[-2], 'low'] = 79.0
        
        # Set current time to be > 1h after last candle (fully closed)
        last_ts = df['time'].iloc[-1]
        current_time = last_ts + 3100 # < 3600, so last is developing, -2 is closed
        
        # Run check
        action, reason = self.strategy.check_signals(df, current_time)
        
        self.assertEqual(action, "ENTRY_SHORT")
        self.assertIn("Breakdown", reason)
        self.assertEqual(self.strategy.current_position, 0) # Should verify state update happens OUTSIDE check usually, but signal is key
        
        # Simulate Runner updating state
        self.strategy.update_position_state(action, current_time, None, 80.0, reason)
        self.assertEqual(self.strategy.current_position, -1)

    def test_short_exit_signal(self):
        # Setup: Already Short
        self.strategy.current_position = -1
        self.strategy.allow_short = True
        
        df = self.create_mock_df(length=60, price_trend="flat")
        
        # Define Upper Channel at 110 (Highs)
        # Breakout to 120
        df['high'] = 110.0
        df['low'] = 90.0
        df['close'] = 100.0
        
        df.loc[df.index[-2], 'close'] = 112.0 # Break 110
        
        last_ts = df['time'].iloc[-1]
        current_time = last_ts + 3500 
        
        action, reason = self.strategy.check_signals(df, current_time)
        
        self.assertEqual(action, "EXIT_SHORT")
        self.assertIn("Breakout", reason)

    def test_reconcile_short(self):
        # Test reconciling a negative position
        self.strategy.current_position = 0
        self.strategy.reconcile_position(-100, 95000.0)
        
        self.assertEqual(self.strategy.current_position, -1)
        self.assertIsNotNone(self.strategy.active_trade)
        self.assertEqual(self.strategy.active_trade['type'], "SHORT")
        self.assertEqual(self.strategy.active_trade['entry_price'], 95000.0)

if __name__ == '__main__':
    unittest.main()
