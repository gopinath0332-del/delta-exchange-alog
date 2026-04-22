import sys
import os
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_config
from core.trading import execute_strategy_signal
from core.firestore_client import initialize_firestore

def test_lifecycle():
    print("Starting Firestore Lifecycle Test...")
    
    # 1. Initialize Configuration
    config = get_config()
    
    # Ensure Firestore is initialized for the test with the 'crypto' collection
    initialize_firestore(
        service_account_path=config.firestore_service_account_path,
        collection_name="crypto",
        enabled=True
    )
    
    # Mock Notifier and Client (so we don't spam Discord or hit the exchange)
    mock_notifier = MagicMock()
    mock_client = MagicMock()
    
    # Configure mock client to return a valid product list
    mock_product = {
        "id": 1,
        "symbol": "BTCUSD",
        "product_type": "futures",
        "tick_size": "0.5",
        "contract_value": "0.001"
    }
    mock_client.get_products.return_value = [mock_product]
    mock_client.place_order.return_value = {"id": "test_order_123"}
    mock_client.get_ticker.return_value = {"mark_price": "65000.0"}
    
    # Test Data
    symbol = "BTCUSD"
    
    # --- PHASE 1: ENTRY ---
    print("\n--- PHASE 1: ENTRY ---")
    entry_result = execute_strategy_signal(
        client=mock_client,
        notifier=mock_notifier,
        symbol=symbol,
        action="ENTRY_LONG",
        price=100.0,
        market_price=100.0,
        rsi=None,
        reason="Test Entry Condition",
        mode="paper",
        strategy_name="LifecycleTest"
    )
    
    trade_id = entry_result.get('trade_id') if isinstance(entry_result, dict) else None
    
    if trade_id:
        print(f"Entry Successful! Trade ID: {trade_id}")
        print("Check Firestore: A new document should exist in the 'crypto' collection.")
    else:
        print("Entry Failed!")
        return

    time.sleep(1)

    # --- PHASE 2: MILESTONE ---
    print("\n--- PHASE 2: MILESTONE ---")
    execute_strategy_signal(
        client=mock_client,
        notifier=mock_notifier,
        symbol=symbol,
        action="MILESTONE_EXIT",
        price=110.0,
        market_price=110.0,
        rsi=None,
        reason="Test Milestone 1 (30% exit)",
        mode="paper",
        strategy_name="LifecycleTest",
        trade_id=trade_id
    )
    print(f"Milestone Logged to {trade_id}")
    print("Check Firestore: The 'events' array should now have 2 items (Entry + Milestone).")

    time.sleep(1)

    # --- PHASE 3: FINAL EXIT ---
    print("\n--- PHASE 3: FINAL EXIT ---")
    execute_strategy_signal(
        client=mock_client,
        notifier=mock_notifier,
        symbol=symbol,
        action="EXIT_LONG",
        price=120.0,
        market_price=120.0,
        rsi=None,
        reason="Test Final Take Profit",
        mode="paper",
        strategy_name="LifecycleTest",
        trade_id=trade_id
    )
    print(f"Final Exit Logged to {trade_id}")
    print("Check Firestore: The document should now be 'CLOSED' with 3 events in history.")
    print("Lifecycle Test Complete!")

if __name__ == "__main__":
    test_lifecycle()
