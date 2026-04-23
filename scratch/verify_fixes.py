
import logging
from typing import Dict, Optional, Any
import unittest
from unittest.mock import MagicMock

# Mock dependencies that might be imported at module level
import sys
from unittest.mock import patch

# Mock strategies for testing
sys.modules['core.persistence'] = MagicMock()
sys.modules['core.config'] = MagicMock()

from strategies.donchian_strategy import DonchianChannelStrategy
from strategies.macd_psar_100ema_strategy import MACDPSAR100EMAStrategy
from strategies.rsi_supertrend_strategy import RSISupertrendStrategy
from strategies.rsi_50_ema_strategy import RSI50EMAStrategy
from strategies.cci_ema_strategy import CCIEMAStrategy

class TestReconciliation(unittest.TestCase):
    def test_donchian_reconciliation(self):
        strategy = DonchianChannelStrategy("BTCUSDT")
        strategy.current_position = 1
        strategy.entry_price = 1000.0
        strategy.active_trade = {"status": "OPEN"}
        
        # Test transition to FLAT
        action, reason = strategy.reconcile_position(size=0, entry_price=0.0)
        self.assertEqual(action, "EXIT_LONG")
        self.assertIn("External Exit", reason)
        self.assertEqual(strategy.current_position, 0)
        self.assertIsNone(strategy.active_trade)

    def test_macd_psar_reconciliation(self):
        strategy = MACDPSAR100EMAStrategy("BTCUSDT")
        strategy.current_position = 1
        strategy.active_trade = {"status": "OPEN"}
        
        # Test transition to FLAT
        action, reason = strategy.reconcile_position(size=0, entry_price=0.0)
        self.assertEqual(action, "EXIT_LONG")
        self.assertIn("External Exit", reason)
        self.assertEqual(strategy.current_position, 0)
        self.assertIsNone(strategy.active_trade)

    def test_rsi_supertrend_reconciliation(self):
        strategy = RSISupertrendStrategy("BTCUSDT")
        strategy.current_position = 1
        strategy.active_trade = {"status": "OPEN"}
        
        # Test transition to FLAT
        action, reason = strategy.reconcile_position(size=0, entry_price=0.0)
        self.assertEqual(action, "EXIT_LONG")
        self.assertIn("External Exit", reason)
        self.assertEqual(strategy.current_position, 0)
        self.assertIsNone(strategy.active_trade)

    def test_rsi_50_ema_reconciliation(self):
        strategy = RSI50EMAStrategy("BTCUSDT")
        strategy.current_position = 1
        strategy.active_trade = {"status": "OPEN"}
        
        # Test transition to FLAT
        action, reason = strategy.reconcile_position(size=0, entry_price=0.0)
        self.assertEqual(action, "EXIT_LONG")
        self.assertIn("External Exit", reason)
        self.assertEqual(strategy.current_position, 0)
        self.assertIsNone(strategy.active_trade)

    def test_cci_ema_reconciliation(self):
        strategy = CCIEMAStrategy("BTCUSDT")
        strategy.current_position = 1
        strategy.active_trade = {"status": "OPEN"}
        
        # Test transition to FLAT
        action, reason = strategy.reconcile_position(size=0, entry_price=0.0)
        self.assertEqual(action, "EXIT_LONG")
        self.assertIn("External Exit", reason)
        self.assertEqual(strategy.current_position, 0)
        self.assertIsNone(strategy.active_trade)

if __name__ == "__main__":
    unittest.main()
