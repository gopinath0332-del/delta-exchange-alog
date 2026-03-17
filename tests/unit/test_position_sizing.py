
import unittest
import os
from unittest.mock import MagicMock, patch
from core.trading import calculate_position_size, get_trade_config

class TestPositionSizing(unittest.TestCase):
    def test_calculate_position_size_margin(self):
        """Test standard margin-based sizing."""
        # (40 * 5) / (50000 * 0.001) = 200 / 50 = 4
        size = calculate_position_size(
            target_margin=40.0,
            price=50000.0,
            leverage=5,
            contract_value=0.001,
            sizing_type="margin"
        )
        self.assertEqual(size, 4)

    def test_calculate_position_size_atr(self):
        """Test ATR-based sizing."""
        # Target Margin / (ATR * Multiplier * Contract Value)
        # 40 / (100 * 2.0 * 0.001) = 40 / 0.2 = 200
        size = calculate_position_size(
            target_margin=40.0,
            price=50000.0,
            leverage=5,
            contract_value=0.001,
            sizing_type="atr",
            atr=100.0,
            atr_multiplier=2.0,
            atr_margin_cap_multiplier=100.0
        )
        self.assertEqual(size, 200)

    def test_calculate_position_size_partial_tp_rounding(self):
        """Test rounding to even number when partial TP is enabled."""
        # Margin: (40 * 5) / (60000 * 0.001) = 200 / 60 = 3.33 -> 3
        # Should round to 4 because 3 is odd and partial TP is enabled
        size = calculate_position_size(
            target_margin=40.0,
            price=60000.0,
            leverage=5,
            contract_value=0.001,
            enable_partial_tp=True,
            sizing_type="margin"
        )
        self.assertEqual(size, 4)

    def test_calculate_position_size_atr_safety_cap(self):
        """Test that ATR safety cap limits position size when volatility is extremely low."""
        # Target Margin / (ATR * Multiplier * Contract Value)
        # 40 / (1 * 2.0 * 0.001) = 40 / 0.002 = 20,000 contracts
        # Actual Margin @ 5x: (20,000 * 50000 * 0.001) / 5 = 1,000,000 / 5 = 200,000 (WAY OVER)
        # 1.5x Cap: 40 * 1.5 = 60 USD Max Margin
        # Max Size = (60 * 5) / (50000 * 0.001) = 300 / 50 = 6 contracts
        size = calculate_position_size(
            target_margin=40.0,
            price=50000.0,
            leverage=5,
            contract_value=0.001,
            sizing_type="atr",
            atr=1.0,
            atr_multiplier=2.0,
            atr_margin_cap_multiplier=1.5
        )
        self.assertEqual(size, 6)

    @patch('core.config.get_config')
    def test_get_trade_config_overrides(self, mock_get_config):
        """Test that get_trade_config correctly picks up overrides from sizing_config and Env."""
        mock_config = MagicMock()
        mock_config.risk_management.position_sizing_type = "margin"
        mock_config.risk_management.atr_margin_multiplier = 2.0
        mock_config.risk_management.atr_margin_cap_multiplier = 1.5
        mock_get_config.return_value = mock_config
        
        # Setup sizing_config (as it would come from multi_coin in settings.yaml)
        sizing_cfg = {
            "position_sizing_type": "atr",
            "atr_margin_multiplier": 3.0,
            "leverage": 20,
            "target_margin": 150.0,
            "atr_margin_cap_multiplier": 2.0
        }
        
        # Environment variables (lower priority)
        with patch.dict(os.environ, {
            'TARGET_MARGIN_BTC': '125',
            'LEVERAGE_BTC': '10',
            'POSITION_SIZING_TYPE_BTC': 'margin'
        }, clear=True):
            config = get_trade_config("BTCUSD", sizing_config=sizing_cfg)
        
        # YAML sizing_config (Priority 1) wins for EVERYTHING
        self.assertEqual(config['target_margin'], 150.0)
        self.assertEqual(config['leverage'], 20)
        self.assertEqual(config['sizing_type'], "atr")
        self.assertEqual(config['atr_multiplier'], 3.0)
        self.assertEqual(config['atr_margin_cap_multiplier'], 2.0)

if __name__ == '__main__':
    unittest.main()
