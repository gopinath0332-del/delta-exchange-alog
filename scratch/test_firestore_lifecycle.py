import sys
import os
import time
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_config
from core.trading import execute_strategy_signal
from core.firestore_client import initialize_firestore

def test_premium_metrics():
    print("Starting Premium Metrics Verification Test...")
    
    # 1. Initialize Configuration
    config = get_config()
    initialize_firestore(
        service_account_path=config.firestore_service_account_path,
        collection_name="crypto",
        enabled=True
    )
    
    mock_notifier = MagicMock()
    mock_client = MagicMock()
    
    # Configure mock client
    mock_product = {
        "id": 1,
        "symbol": "BTCUSD",
        "product_type": "futures",
        "tick_size": "0.5",
        "contract_value": "0.001"
    }
    mock_client.get_products.return_value = [mock_product]
    mock_client.place_order.return_value = {"id": "test_order_premium"}
    mock_client.get_ticker.return_value = {"mark_price": "65000.0"}
    
    symbol = "BTCUSD"
    entry_price = 65000.0
    sl_price = 63000.0
    
    # --- PHASE 1: ENTRY ---
    print("\n--- PHASE 1: ENTRY ---")
    entry_result = execute_strategy_signal(
        client=mock_client,
        notifier=mock_notifier,
        symbol=symbol,
        action="ENTRY_LONG",
        price=entry_price,
        market_price=entry_price,
        rsi=45.0,
        reason="Premium Metrics Test",
        mode="paper",
        strategy_name="PremiumTest",
        stop_loss_price=sl_price # Setting initial SL for Risk calculation
    )
    
    trade_id = entry_result.get('trade_id')
    print(f"Trade Opened: {trade_id}")

    time.sleep(1)

    # --- PHASE 2: EXIT (WITH EXCURSIONS) ---
    print("\n--- PHASE 2: EXIT (VERIFYING MAE/MFE/R-MULTIPLE) ---")
    # Simulate excursion data tracked by the bot
    max_price_seen = 68000.0
    min_price_seen = 64500.0
    exit_price = 67000.0
    
    execute_strategy_signal(
        client=mock_client,
        notifier=mock_notifier,
        symbol=symbol,
        action="EXIT_LONG",
        price=exit_price,
        market_price=exit_price,
        rsi=65.0,
        reason="Taking Profit",
        mode="paper",
        strategy_name="PremiumTest",
        trade_id=trade_id,
        # Passing excursion data that would normally come from strategy state
        max_price_seen=max_price_seen,
        min_price_seen=min_price_seen
    )
    
    print(f"Trade Closed: {trade_id}")
    print("\nTest Complete! Check your Firestore document for:")
    print(f" - initial_risk: Should be around $2.00 (per 0.001 BTC lot)")
    print(f" - mfe_pct: Should be positive (Best Price: {max_price_seen})")
    print(f" - mae_pct: Should be negative (Worst Price: {min_price_seen})")
    print(f" - r_multiple: Should be around 1.0 (Profit=Risk)")

if __name__ == "__main__":
    test_premium_metrics()
