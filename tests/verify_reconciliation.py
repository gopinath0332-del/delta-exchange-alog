import os
import sys
import unittest
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from strategies.rsi_50_ema_strategy import RSI50EMAStrategy

class TestReconciliation(unittest.TestCase):
    def test_reconcile_closes_phantom_trade(self):
        strategy = RSI50EMAStrategy()
        
        # Setup phantom state: Bot thinks it's Long, but Exchange is Flat
        strategy.current_position = 1
        strategy.active_trade = {
            "type": "LONG",
            "entry_time": "FakeTime",
            "entry_price": 100.0,
            "entry_rsi": 50.0,
            "status": "OPEN"
        }
        
        # Action: Reconcile with 0 size (FLAT)
        print("Running reconciliation with size=0...")
        strategy.reconcile_position(size=0, entry_price=0)
        
        # Assertions
        self.assertEqual(strategy.current_position, 0, "Position should be FLAT")
        self.assertIsNone(strategy.active_trade, "Active trade should be None")
        self.assertEqual(len(strategy.trades), 1, "Trade should be moved to history")
        
        closed_trade = strategy.trades[0]
        self.assertEqual(closed_trade['status'], "CLOSED (SYNC)", "Status should indicate sync closure")
        print("✅ PASS: Phantom trade closed successfully.")

if __name__ == "__main__":
    unittest.main()
