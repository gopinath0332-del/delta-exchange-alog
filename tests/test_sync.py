
import unittest

class MockStrategy:
    def __init__(self):
        self.current_position = -1 # Start with SHORT
        self.active_trade = {"type": "SHORT", "status": "OPEN"}
        self.trades = []
        
    def reconcile_position(self, size, entry_price, market_price, live_pos_data=None):
        expected_pos = 0
        if size > 0: expected_pos = 1
        elif size < 0: expected_pos = -1
        
        if self.current_position != expected_pos:
            self.current_position = expected_pos
            if expected_pos == 0:
                self.active_trade = None
                print("Internal state reconciled to FLAT")

class TestSyncLogic(unittest.TestCase):
    def test_reconciliation_trigger(self):
        strategy = MockStrategy()
        
        # Simulating the cycle logic I added to runner.py
        # Exchange says FLAT (size=0)
        size = 0.0
        entry_price = 0.0
        market_price = 0.04365
        
        # This is the call that now happens every cycle in the updated runner.py
        strategy.reconcile_position(size, entry_price, market_price, live_pos_data=None)
        
        self.assertEqual(strategy.current_position, 0)
        self.assertIsNone(strategy.active_trade)
        print("Success: Strategy reconciled to FLAT when exchange is FLAT")

if __name__ == "__main__":
    unittest.main()
