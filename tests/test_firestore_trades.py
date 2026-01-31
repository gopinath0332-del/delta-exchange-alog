#!/usr/bin/env python3
"""Test Firestore trade journaling by adding dummy entry and exit trades."""
import time
from core.config import get_config
from core.logger import setup_logging, get_logger
from core.firestore_client import journal_trade, get_firestore_status

logger = get_logger(__name__)
setup_logging(log_level='INFO')

print('\n' + '='*60)
print('🧪 Firestore Trade Journaling Test')
print('='*60 + '\n')

# Initialize configuration
config = get_config()
print('')

# Check Firestore status
status = get_firestore_status()
if not status['connected']:
    print('❌ ERROR: Firestore is not connected!')
    print(f'   Enabled: {status["enabled"]}')
    exit(1)

print('✅ Firestore connected successfully')
print(f'   Collection: {status["collection"]}\n')

# Test 1: Journal a dummy ENTRY trade
print('-' * 60)
print('TEST 1: Journaling ENTRY_LONG trade...')
print('-' * 60)

entry_doc_id = journal_trade(
    symbol="BTCUSD",
    action="ENTRY_LONG",
    side="buy",
    price=95000.00,
    order_size=2,
    leverage=5,
    mode="paper",
    strategy_name="Test Strategy",
    rsi=55.23,
    reason="Test entry signal - RSI crossover above 50",
    is_entry=True,
    is_partial_exit=False,
    entry_price=95000.00,
    exit_price=None,
    execution_price=95005.50,
    pnl=None,
    funding_charges=None,
    trading_fees=None,
    margin_used=38000.00,
    remaining_margin=12000.00,
    product_id=1,
    order_id="TEST_ORDER_ENTRY_001"
)

if entry_doc_id:
    print(f'✅ Entry trade journaled successfully!')
    print(f'   Document ID: {entry_doc_id}\n')
else:
    print('❌ Failed to journal entry trade\n')

# Wait a moment before next trade
time.sleep(1)

# Test 2: Journal a dummy EXIT trade
print('-' * 60)
print('TEST 2: Journaling EXIT_LONG trade...')
print('-' * 60)

exit_doc_id = journal_trade(
    symbol="BTCUSD",
    action="EXIT_LONG",
    side="sell",
    price=97500.00,
    order_size=2,
    leverage=5,
    mode="paper",
    strategy_name="Test Strategy",
    rsi=42.15,
    reason="Test exit signal - Trailing stop hit",
    is_entry=False,
    is_partial_exit=False,
    entry_price=95000.00,
    exit_price=97500.00,
    execution_price=97495.25,
    pnl=4990.50,  # Profit from the trade
    funding_charges=-12.50,  # Funding costs
    trading_fees=23.25,  # Trading fees
    margin_used=None,
    remaining_margin=16954.75,
    product_id=1,
    order_id="TEST_ORDER_EXIT_001"
)

if exit_doc_id:
    print(f'✅ Exit trade journaled successfully!')
    print(f'   Document ID: {exit_doc_id}\n')
else:
    print('❌ Failed to journal exit trade\n')

# Wait a moment before partial exit test
time.sleep(1)

# Test 3: Journal a dummy PARTIAL EXIT trade
print('-' * 60)
print('TEST 3: Journaling EXIT_LONG_PARTIAL trade...')
print('-' * 60)

partial_exit_doc_id = journal_trade(
    symbol="ETHUSD",
    action="EXIT_LONG_PARTIAL",
    side="sell",
    price=3450.00,
    order_size=2,  # Exiting 2 out of 4 contracts (50%)
    leverage=5,
    mode="paper",
    strategy_name="Test Strategy",
    rsi=78.50,
    reason="Test partial exit - Take profit target hit",
    is_entry=False,
    is_partial_exit=True,
    entry_price=3200.00,
    exit_price=3450.00,
    execution_price=3448.75,
    pnl=497.50,  # Partial profit
    funding_charges=-5.25,
    trading_fees=10.35,
    margin_used=None,
    remaining_margin=14000.00,
    product_id=27,
    order_id="TEST_ORDER_PARTIAL_001"
)

if partial_exit_doc_id:
    print(f'✅ Partial exit trade journaled successfully!')
    print(f'   Document ID: {partial_exit_doc_id}\n')
else:
    print('❌ Failed to journal partial exit trade\n')

# Summary
print('='*60)
print('📊 Test Summary')
print('='*60)
print(f'Entry trade:        {"✅ Success" if entry_doc_id else "❌ Failed"}')
print(f'Exit trade:         {"✅ Success" if exit_doc_id else "❌ Failed"}')
print(f'Partial exit trade: {"✅ Success" if partial_exit_doc_id else "❌ Failed"}')
print('')
print('🔍 Next Steps:')
print('   1. Open Firebase Console: https://console.firebase.google.com/')
print('   2. Navigate to: Firestore Database → trades collection')
print('   3. Verify the 3 test documents are present')
print('   4. Check that all fields are populated correctly')
print('')
print('='*60)
