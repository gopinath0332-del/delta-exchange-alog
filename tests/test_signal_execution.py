"""
Dry run verification script for order placement logic.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from core.trading import execute_strategy_signal

class TestTradingExecution(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_notifier = MagicMock()
        
        # Setup Mock Product
        self.mock_client.get_products.return_value = [
            {
                "id": 123,
                "symbol": "BTCUSD",
                "contract_value": 0.001,
                "settling_asset": {"symbol": "USDT"}
            }
        ]
        
        # Setup Mock Wallet
        self.mock_client.get_wallet_balance.return_value = {
            "result": [
                {"asset_symbol": "USDT", "balance": "1000", "available_balance": "900"}
            ]
        }
        
        # Default: No positions found
        self.mock_client.get_positions.return_value = []
        
        # Patch Environment Variable
        self.env_patcher = patch.dict('os.environ', {'ENABLE_ORDER_PLACEMENT': 'true'})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        
    def test_entry_long(self):
        print("\nTesting ENTRY_LONG...")
        
        # Mock Place Order Response with Fill Price
        self.mock_client.place_order.return_value = {
            "id": "ORDER123",
            "avg_fill_price": "50010.5" # Slippage
        }
        
        result = execute_strategy_signal(
            client=self.mock_client,
            notifier=self.mock_notifier,
            symbol="BTCUSD",
            action="ENTRY_LONG",
            price=50000.0,
            rsi=55.0,
            reason="Test Long",
            strategy_name="TestStrategy"
        )
        
        # Verify Leverage Set
        self.mock_client.set_leverage.assert_called_with(123, "5")
        
        # Verify Order Placed
        self.mock_client.place_order.assert_called_with(
            product_id=123,
            size=1,
            side="buy",
            order_type="market_order"
        )
        
        # Verify Return Value
        self.assertTrue(result['success'])
        self.assertEqual(result['execution_price'], 50010.5)
        
        # Verify Alert Sent with Margin
        # Margin = (50000 * 1 * 0.001) / 5 = 10.0
        self.mock_notifier.send_trade_alert.assert_called()
        args = self.mock_notifier.send_trade_alert.call_args[1]
        self.assertEqual(args['side'], "ENTRY_LONG")
        self.assertAlmostEqual(args['margin_used'], 10.0)
        self.assertEqual(args['remaining_margin'], 900.0)
        # Verify alert uses fill price? The code currently uses max(price, exec_price) logic or similar? 
        # Actually in my update: price=execution_price if execution_price else price
        self.assertEqual(args['price'], 50010.5)
        self.assertEqual(args['strategy_name'], "TestStrategy")
        
        print("ENTRY_LONG Verified successfully.")

    def test_entry_short(self):
        print("\nTesting ENTRY_SHORT...")
        execute_strategy_signal(
            client=self.mock_client,
            notifier=self.mock_notifier,
            symbol="BTCUSD",
            action="ENTRY_SHORT",
            price=50000.0,
            rsi=25.0,
            reason="Test Short"
        )
        
        self.mock_client.set_leverage.assert_called_with(123, "5")
        self.mock_client.place_order.assert_called_with(
            product_id=123,
            size=1,
            side="sell",
            order_type="market_order"
        )
        print("ENTRY_SHORT Verified successfully.")

    def test_entry_skipped_if_position_exists(self):
        print("\nTesting ENTRY_SKIPPED (Position Exists)...")
        
        # Mock existing position
        self.mock_client.get_positions.return_value = [
            {"product_id": 123, "size": 10, "entry_price": 50000}
        ]
        
        execute_strategy_signal(
            client=self.mock_client,
            notifier=self.mock_notifier,
            symbol="BTCUSD",
            action="ENTRY_LONG",
            price=50000.0,
            rsi=55.0,
            reason="Test Long Duplicate"
        )
        
        # Verify get_positions was called
        self.mock_client.get_positions.assert_called_with(product_id=123)
        
        # Verify Place Order was NOT called
        self.mock_client.place_order.assert_not_called()
        self.mock_client.set_leverage.assert_not_called()
        
        print("ENTRY_SKIPPED Verified successfully.")

if __name__ == '__main__':
    unittest.main()
