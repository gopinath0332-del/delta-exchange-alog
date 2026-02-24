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
                "tick_size": "0.5",                        # For SL decimal precision
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

        # Patch asset-specific env vars that trading.py checks.
        # The code reads ENABLE_ORDER_PLACEMENT_BTC (not generic ENABLE_ORDER_PLACEMENT)
        # and TARGET_MARGIN_BTC / LEVERAGE_BTC for position sizing.
        self.env_patcher = patch.dict('os.environ', {
            'ENABLE_ORDER_PLACEMENT_BTC': 'true',
            'TARGET_MARGIN_BTC': '40',
            'LEVERAGE_BTC': '5',
        })
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
        
        # Verify Leverage Set (trading.py passes leverage as string)
        self.mock_client.set_leverage.assert_called_with(123, '5')
        
        # Dynamic position size: (TARGET_MARGIN_BTC * LEVERAGE_BTC) / (ticker_price * contract_value)
        # The mock ticker price resolves to $1 (no ticker mock) so size = (40*5)/(1*0.001) = 200000
        # This is expected for the mock environment.
        self.mock_client.place_order.assert_called_with(
            product_id=123,
            size=200000,
            side="buy",
            order_type="market_order"
        )
        
        # Verify Return Value
        self.assertTrue(result['success'])
        self.assertEqual(result['execution_price'], 50010.5)
        
        # Verify Alert Sent
        self.mock_notifier.send_trade_alert.assert_called()
        args = self.mock_notifier.send_trade_alert.call_args[1]
        self.assertEqual(args['side'], "ENTRY_LONG")
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
        
        self.mock_client.set_leverage.assert_called_with(123, '5')
        self.mock_client.place_order.assert_called_with(
            product_id=123,
            size=200000,
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

    def test_bracket_sl_placed_after_donchian_entry(self):
        """
        Verify that after a Donchian ENTRY_LONG, a bracket stop-loss order is placed
        on the exchange at a price below the entry fill price.

        Setup: Use a high mock entry price ($100,000) so the SL distance is meaningful
        relative to tick_size=0.5. We patch the ticker response to return $100,000 so
        position_size = (40 * 5) / (100000 * 0.001) = 2 contracts.

        Formula: distance = (target_margin * stop_loss_pct) / (order_size * contract_value)
                          = (40 * 0.10) / (2 * 0.001) = 4 / 0.002 = $2000
        Stop price (LONG) = 100000 - 2000 = $98000
        """
        print("\nTesting bracket SL placed after Donchian ENTRY_LONG...")

        entry_price = 100000.0

        # Patch ticker so the price-based position sizing uses $100,000
        self.mock_client.get_ticker.return_value = {"close": str(entry_price), "mark_price": str(entry_price)}

        # Mock fill at entry_price
        self.mock_client.place_order.return_value = {
            "id": "ORDER_SL_TEST",
            "avg_fill_price": str(entry_price)
        }

        result = execute_strategy_signal(
            client=self.mock_client,
            notifier=self.mock_notifier,
            symbol="BTCUSD",
            action="ENTRY_LONG",
            price=entry_price,
            rsi=55.0,
            reason="Test SL Placement",
            strategy_name="DonchianChannel",
            stop_loss_pct=0.10  # Activates bracket SL
        )

        # The entry order must have been placed
        self.assertTrue(self.mock_client.place_order.called, "place_order not called")

        # The bracket SL must have been placed
        self.assertTrue(
            self.mock_client.place_bracket_order.called,
            "place_bracket_order was NOT called despite stop_loss_pct being provided"
        )

        # Verify stop_price in the SL call is BELOW the entry fill price
        kwargs = self.mock_client.place_bracket_order.call_args[1]
        actual_stop = float(kwargs["stop_price"])
        self.assertLess(
            actual_stop, entry_price,
            f"Stop price {actual_stop} should be < entry {entry_price} for LONG"
        )

        # The order type should be market (for guaranteed fill)
        self.assertEqual(kwargs.get("stop_order_type", "market_order"), "market_order")

        print(f"Bracket SL confirmed at {actual_stop} (entry={entry_price}, distance={entry_price - actual_stop})")
        print("test_bracket_sl_placed_after_donchian_entry Verified successfully.")

if __name__ == '__main__':
    unittest.main()
