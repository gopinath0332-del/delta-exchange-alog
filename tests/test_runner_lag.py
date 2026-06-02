import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
from core.runner import run_strategy_terminal
from core.config import Config

class TestRunnerLag(unittest.TestCase):
    @patch('core.runner.DeltaRestClient')
    @patch('core.runner.NotificationManager')
    @patch('core.runner.time.sleep')
    @patch('core.runner.get_trade_config')
    @patch('core.runner.execute_strategy_signal')
    @patch('core.runner._add_per_symbol_log_handler')
    def test_transient_api_lag_retry(self, mock_add_handler, mock_exec_signal, mock_get_trade_config, mock_sleep, mock_notifier, mock_client_class):
        # Setup mocks
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        
        # Product mock
        mock_client.get_products.return_value = [{'symbol': 'ARCUSD', 'id': 123, 'tick_size': '0.01'}]
        
        # Wallet balance mock
        mock_client.get_wallet_balance.return_value = [{'asset_symbol': 'USD', 'available_balance': 1000.0}]
        
        # Config mock
        mock_config = MagicMock(spec=Config)
        mock_config.log_max_bytes = 1024
        mock_config.log_backup_count = 1
        mock_config.default_historical_days = 1
        mock_config.settings = {
            "strategies": {
                "donchian_channel": {
                    "trade_mode": "Both",
                    "enter_period": 20,
                    "exit_period": 10,
                    "atr_period": 14,
                    "atr_mult_tp": 4.0,
                    "atr_mult_trail": 2.0,
                    "historical_days": 1
                }
            }
        }
        
        # Trade config mock
        mock_get_trade_config.return_value = {
            'enabled': True,
            'leverage': 1,
            'order_size': 1,
            'target_margin': 100.0
        }
        
        # Candle mock (historical candles)
        mock_candles = []
        for i in range(50):
            mock_candles.append({
                'time': 1700000000 + i * 3600,
                'open': 100.0,
                'high': 101.0,
                'low': 99.0,
                'close': 100.0,
                'volume': 100.0
            })
        mock_client.get_historical_candles.return_value = mock_candles
        
        # Positions mock - first returns FLAT (empty list), second returns actual position
        mock_client.get_positions.side_effect = [
            [],  # First call: transient flat
            [{'product_id': 123, 'size': '1.0', 'entry_price': '100.0'}]  # Second call: actual position
        ]
        
        from strategies.donchian_strategy import DonchianChannelStrategy
        mock_strategy = DonchianChannelStrategy(symbol='ARCUSD')
        mock_strategy.current_position = 1  # Memory says in trade
        mock_strategy.entry_price = 100.0
        mock_strategy.tp_level = 104.0
        
        # We will mock the strategy class instantiation or patch check_signals
        with patch('strategies.donchian_strategy.DonchianChannelStrategy.check_signals', side_effect=KeyboardInterrupt("Stop Loop")):
            with patch('strategies.donchian_strategy.DonchianChannelStrategy', return_value=mock_strategy):
                try:
                    run_strategy_terminal(
                        config=mock_config,
                        strategy_name="donchian_channel",
                        symbol="ARCUSD",
                        mode="paper",
                        candle_type="standard",
                        timeframe="1h",
                        shared_client=mock_client
                    )
                except KeyboardInterrupt:
                    pass
                
        # Assertions
        # 1. sleep should have been called with 2 to mitigate transient lag
        mock_sleep.assert_any_call(2)
        
        # 2. get_positions should have been called twice (first flat, retry next)
        self.assertEqual(mock_client.get_positions.call_count, 2)
        
        # 3. strategy.current_position should remain 1 (not reconciled to 0/flat)
        self.assertEqual(mock_strategy.current_position, 1)

if __name__ == '__main__':
    unittest.main()
