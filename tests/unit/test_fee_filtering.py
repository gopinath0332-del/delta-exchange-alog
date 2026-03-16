import unittest
from unittest.mock import MagicMock, patch
from api.rest_client import DeltaRestClient
from core.config import Config

class TestFeeFiltering(unittest.TestCase):
    def setUp(self):
        self.mock_config = MagicMock(spec=Config)
        self.mock_config.base_url = "https://test.delta.exchange"
        self.mock_config.api_key = "test_key"
        self.mock_config.api_secret = "test_secret"
        self.mock_config.environment = "testnet"
        
        with patch('api.rest_client.BaseDeltaClient'):
            self.client = DeltaRestClient(self.mock_config)

    @patch('api.rest_client.DeltaRestClient._make_auth_request')
    def test_get_wallet_transactions_filtering(self, mock_make_auth):
        # Mock response with mixed product_ids
        mock_make_auth.return_value = {
            "result": [
                {"id": 1, "product_id": 123, "amount": "-0.1"},
                {"id": 2, "product_id": 456, "amount": "-0.2"},
                {"id": 3, "product_id": 123, "amount": "-0.3"},
                {"id": 4, "product_id": "123", "amount": "-0.4"}, # String ID case
            ],
            "meta": {"after": None}
        }
        
        # Test filtering by product_id 123
        txns = self.client.get_wallet_transactions("commission", 0, 1000, product_id=123)
        
        self.assertEqual(len(txns), 3)
        for t in txns:
            self.assertIn(str(t["product_id"]), ["123"])
            self.assertNotEqual(t["product_id"], 456)
            
        # Test filtering by product_id 456
        txns = self.client.get_wallet_transactions("commission", 0, 1000, product_id=456)
        self.assertEqual(len(txns), 1)
        self.assertEqual(txns[0]["product_id"], 456)

        # Test no filtering
        txns = self.client.get_wallet_transactions("commission", 0, 1000, product_id=None)
        self.assertEqual(len(txns), 4)

    @patch('api.rest_client.DeltaRestClient._make_auth_request')
    def test_pagination_restored(self, mock_make_auth):
        # Mock multiple pages
        mock_make_auth.side_effect = [
            {
                "result": [{"id": 1, "product_id": 123}],
                "meta": {"after": "cursor2"}
            },
            {
                "result": [{"id": 2, "product_id": 123}],
                "meta": {"after": None}
            }
        ]
        
        txns = self.client.get_wallet_transactions("commission", 0, 1000)
        
        self.assertEqual(len(txns), 2)
        self.assertEqual(mock_make_auth.call_count, 2)
        # Verify 'after' was passed in second call
        self.assertEqual(mock_make_auth.call_args_list[1][1]['params']['after'], "cursor2")

if __name__ == '__main__':
    unittest.main()
