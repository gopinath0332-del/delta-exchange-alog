import os
import sys
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.trading import execute_strategy_signal

def run_test():
    print("Running Per-Symbol Order Flag Verification...")
    
    # Mock dependencies
    mock_client = MagicMock()
    mock_notifier = MagicMock()
    
    # Mock product response
    mock_client.get_products.return_value = [{'symbol': 'BTC-USD', 'id': 100, 'contract_value': 0.001}]
    mock_client.get_positions.return_value = []
    
    # Helper to run test case
    def check_case(symbol, action, mock_env, expected_enable, description):
        with patch.dict(os.environ, mock_env, clear=True):
            print(f"\n--- Test Case: {description} ---")
            print(f"Env: {mock_env}")
            
            # Action
            execute_strategy_signal(
                client=mock_client,
                notifier=mock_notifier,
                symbol=symbol,
                action=action,
                price=50000,
                rsi=50,
                reason="Test"
            )
            
            # Check calls
            if expected_enable:
                if mock_client.place_order.called:
                    print("✅ PASS: Order was placed as expected.")
                else:
                    print("❌ FAIL: Order SHOULD have been placed but was not.")
            else:
                if not mock_client.place_order.called:
                    print("✅ PASS: Order was correctly valid/skipped.")
                else:
                    print("❌ FAIL: Order was placed but SHOULD NOT have been.")
                    
            mock_client.place_order.reset_mock()

    # Case 1: No flag set -> Should NOT place order
    check_case(
        symbol="BTC-USD", 
        action="ENTRY_LONG", 
        mock_env={}, 
        expected_enable=False, 
        description="No flags set"
    )

    # Case 2: Specific flag set to true -> Should place order
    check_case(
        symbol="BTC-USD", 
        action="ENTRY_LONG", 
        mock_env={"ENABLE_ORDER_PLACEMENT_BTC": "true"}, 
        expected_enable=True, 
        description="Specific BTC=true"
    )

    # Case 3: Specific flag set to false -> Should NOT place order
    check_case(
        symbol="BTC-USD", 
        action="ENTRY_LONG", 
        mock_env={"ENABLE_ORDER_PLACEMENT_BTC": "false"}, 
        expected_enable=False, 
        description="Specific BTC=false"
    )

    # Case 4: Wrong symbol flag (e.g. ETH set, testing BTC) -> Should NOT place order
    check_case(
        symbol="BTC-USD", 
        action="ENTRY_LONG", 
        mock_env={"ENABLE_ORDER_PLACEMENT_ETH": "true"}, 
        expected_enable=False, 
        description="Flag for other symbol (ETH) set"
    )

    # Case 5: Global flag present (should be IGNORED now) -> Should NOT place order
    check_case(
        symbol="BTC-USD", 
        action="ENTRY_LONG", 
        mock_env={"ENABLE_ORDER_PLACEMENT": "true"}, 
        expected_enable=False, 
        description="Global flag present (Should be IGNORED)"
    )

if __name__ == "__main__":
    run_test()
