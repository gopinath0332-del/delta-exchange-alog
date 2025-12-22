import os
import sys
import unittest
import pandas as pd
import time
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategies.rsi_50_ema_strategy import RSI50EMAStrategy

class TestCandleSelection(unittest.TestCase):
    def setUp(self):
        self.strategy = RSI50EMAStrategy()
        
        # Create a mock dataframe
        # Times: 00:30, 01:30, 02:30
        # Create a mock dataframe with enough rows for EMA 50
        self.base_ts = 1766430000 # Reference time
        
        data = []
        # Generate 60 candles
        for i in range(60):
            ts = self.base_ts + (i * 3600)
            data.append({
                'time': ts, 
                'close': 100 + i, 
                'open': 100 + i, 
                'high': 105 + i, 
                'low': 95 + i
            })
            
        self.df = pd.DataFrame(data)
        
    def test_fresh_candle_developing(self):
        """
        Scenario: Current time is 02:40. The 02:30 candle (Index -1) exists and is developing.
        Strategy should verify 'Closed' condition on Index -2 (01:30).
        """
        last_candle_time = self.df['time'].iloc[-1] # 02:30
        current_time = last_candle_time + 600 # 02:40 (+10 mins)
        
        # Run calculation
        self.strategy.calculate_indicators(self.df, current_time=current_time)
        
        # Check cached "Last Closed" time string
        expected_closed_ts = self.df['time'].iloc[-2] # 01:30
        expected_str = datetime.fromtimestamp(expected_closed_ts).strftime('%H:%M')
        
        print(f"\nTest 1 (Developing): Current {datetime.fromtimestamp(current_time).strftime('%H:%M')}, " 
              f"Last Candle {datetime.fromtimestamp(last_candle_time).strftime('%H:%M')}")
        print(f"Result: Last Closed Used: {self.strategy.last_closed_time_str} | Expected: {expected_str}")
        
        self.assertEqual(self.strategy.last_closed_time_str, expected_str)

    def test_stale_candle_just_closed(self):
        """
        Scenario: Current time is 03:31. The 02:30 candle (Index -1) is the last one returned by API.
        The 03:30 candle is NOT yet in the df.
        Strategy should verify 'Closed' condition on Index -1 (02:30).
        """
        last_candle_time = self.df['time'].iloc[-1] # 02:30
        current_time = last_candle_time + 3660 # 03:31 (+1h 1min)
        
        # Run calculation
        self.strategy.calculate_indicators(self.df, current_time=current_time)
        
        # Check cached "Last Closed" time string
        expected_closed_ts = self.df['time'].iloc[-1] # 02:30 (Last one IS the closed one)
        expected_str = datetime.fromtimestamp(expected_closed_ts).strftime('%H:%M')
        
        print(f"\nTest 2 (Stale/Closed): Current {datetime.fromtimestamp(current_time).strftime('%H:%M')}, " 
              f"Last Candle {datetime.fromtimestamp(last_candle_time).strftime('%H:%M')}")
        print(f"Result: Last Closed Used: {self.strategy.last_closed_time_str} | Expected: {expected_str}")
        
        self.assertEqual(self.strategy.last_closed_time_str, expected_str)

if __name__ == "__main__":
    unittest.main()
