"""
Verification script for stop-loss order placement logic.
"""

import unittest
from unittest.mock import MagicMock, patch
from core.trading import execute_strategy_signal

class TestStopLossExecution(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_notifier = MagicMock()
        
        # Setup Mock Product
        self.mock_client.get_products.return_value = [
            {
                "id": 123,
                "symbol": "RIVERUSD",
                "contract_value": 1.0,
                "tick_size": "0.001",
                "settling_asset": {"symbol": "USD"}
            }
        ]
        
        # Setup Mock Wallet
        self.mock_client.get_wallet_balance.return_value = {
            "result": [
                {"asset_symbol": "USD", "available_balance": "1000"}
            ]
        }
        
        # Default: No positions found
        self.mock_client.get_positions.return_value = []

        # Patch environment variables
        self.env_patcher = patch.dict('os.environ', {
            'ENABLE_ORDER_PLACEMENT_RIVER': 'true',
            'TARGET_MARGIN_RIVER': '50',
            'LEVERAGE_RIVER': '5',
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    def test_bracket_stop_loss_placement(self):
        print("\nTesting Bracket Stop Loss Placement...")
        
        # Mock Place Order Response
        self.mock_client.place_order.return_value = {
            "id": "ORDER123",
            "avg_fill_price": "30.0"
        }
        
        # Call execute_strategy_signal with a stop_loss_price
        result = execute_strategy_signal(
            client=self.mock_client,
            notifier=self.mock_notifier,
            symbol="RIVERUSD",
            action="ENTRY_LONG",
            price=30.0,
            market_price=30.0,
            rsi=50.0,
            reason="Test SL",
            mode="live",
            strategy_name="donchian_channel",
            stop_loss_price=27.0  # 10% below entry
        )
        
        # Verify Place Order was called
        self.mock_client.place_order.assert_called()
        
        # Verify place_bracket_order was called with correct arguments
        self.mock_client.place_bracket_order.assert_called_with(
            product_id=123,
            product_symbol="RIVERUSD",
            stop_price="27.000",  # Formatted to 3 decimals based on tick_size 0.001
            stop_order_type="market_order"
        )
        
        self.assertTrue(result['success'])
        print("Bracket Stop Loss Placement Verified successfully.")

if __name__ == '__main__':
    unittest.main()
