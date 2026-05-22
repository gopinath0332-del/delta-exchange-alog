import unittest
from unittest.mock import MagicMock, patch

from core.trading import execute_strategy_signal


class TestMilestoneExecution(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_notifier = MagicMock()

        self.mock_client.get_products.return_value = [
            {
                "id": 59172,
                "symbol": "VVVUSD",
                "contract_value": 1.0,
                "tick_size": "0.001",
                "settling_asset": {"symbol": "USD"},
            }
        ]
        self.mock_client.get_positions.return_value = [
            {
                "product_id": 59172,
                "size": "2",
                "entry_price": "16.919",
                "margin": "7.12",
                "unrealized_pnl": "4.0",
                "commission": "0.0",
                "funding_pnl": "0.0",
            }
        ]
        self.mock_client.place_order.return_value = {
            "id": "MILESTONE_ORDER",
            "avg_fill_price": "19.459",
        }
        self.mock_client.get_order.return_value = {
            "id": "MILESTONE_ORDER",
            "state": "closed",
            "avg_fill_price": "19.459",
            "realized_pnl": "2.54",
        }
        self.mock_client.get_wallet_balance.return_value = {
            "result": [{"asset_symbol": "USD", "balance": "290", "available_balance": "280"}]
        }
        self.mock_client.get_wallet_transactions.return_value = []
        self.mock_client.get_funding_transactions.return_value = []

        self.env_patcher = patch.dict("os.environ", {"ENABLE_ORDER_PLACEMENT": "true"})
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("core.trading.time.sleep", return_value=None)
    @patch("core.trading.journal_trade")
    @patch("core.trading.get_open_trade_by_symbol", return_value="VVV_OPEN_TRADE")
    @patch(
        "core.trading.get_trade_config",
        return_value={
            "order_size": 1,
            "leverage": 5,
            "enabled": True,
            "base_asset": "VVV",
            "target_margin": 40.0,
            "sizing_type": "margin",
            "sizing_method": "fixed",
            "risk_pct": 0.01,
            "fractional_margin_cap": 0.2,
            "settlement_asset": "USD",
            "atr_multiplier": 2.0,
            "atr_margin_cap_multiplier": 1.0,
        },
    )
    def test_milestone_exit_rounds_small_position_to_one_lot(
        self, _mock_trade_config, _mock_trade_lookup, _mock_journal, _mock_sleep
    ):
        result = execute_strategy_signal(
            client=self.mock_client,
            notifier=self.mock_notifier,
            symbol="VVVUSD",
            action="MILESTONE_EXIT",
            price=19.459,
            market_price=19.459,
            rsi=None,
            reason="Milestone 1: Exchange PnL 55.0% >= 50.0% | exit_pct=0.30",
            mode="live",
            strategy_name="donchian_channel",
        )

        self.mock_client.place_order.assert_called_once_with(
            product_id=59172,
            size=1,
            side="sell",
            order_type="market_order",
        )
        self.assertTrue(result["success"])
        self.assertTrue(result["order_placed"])
        self.assertEqual(result["order_id"], "MILESTONE_ORDER")


if __name__ == "__main__":
    unittest.main()
