#!/usr/bin/env python3
"""Test Firestore trade journaling WITH trade_id linking."""
import time
import uuid
from datetime import datetime
from core.config import get_config
from core.logger import setup_logging, get_logger
from core.firestore_client import journal_trade, get_firestore_status

logger = get_logger(__name__)
setup_logging(log_level='INFO')

print('\n' + '='*70)
print('🧪 Firestore Trade Journaling Test - WITH trade_id Linking')
print('='*70 + '\n')

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

# Generate a unique trade_id for the complete trade journey
symbol = "BTCUSD"
strategy_name = "Test Strategy (Linked)"
timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M%S')
trade_id = f"{symbol}_{strategy_name}_{timestamp_str}_{uuid.uuid4().hex[:8]}"

print('🔗 Generated trade_id for this trade journey:')
print(f'   {trade_id}\n')

# Test 1: Journal ENTRY trade with trade_id
print('-' * 70)
print('TEST 1: Journaling ENTRY_LONG trade (with trade_id)...')
print('-' * 70)

entry_doc_id = journal_trade(
    symbol=symbol,
    action="ENTRY_LONG",
    side="buy",
    price=96000.00,
    order_size=3,
    leverage=5,
    mode="paper",
    trade_id=trade_id,  # 🔗 Link entry and exit
    strategy_name=strategy_name,
    rsi=58.45,
    reason="Test entry - Breakout confirmed",
    is_entry=True,
    is_partial_exit=False,
    entry_price=96000.00,
    exit_price=None,
    execution_price=96010.25,
    pnl=None,
    funding_charges=None,
    trading_fees=None,
    margin_used=57600.00,
    remaining_margin=10000.00,
    product_id=1,
    order_id="TEST_ENTRY_LINKED_001"
)

if entry_doc_id:
    print(f'✅ Entry trade journaled!')
    print(f'   Document ID: {entry_doc_id}')
    print(f'   trade_id: {trade_id}\n')
else:
    print('❌ Failed to journal entry trade\n')

# Wait a moment to simulate time between entry and exit
time.sleep(2)

# Test 2: Journal EXIT trade with SAME trade_id
print('-' * 70)
print('TEST 2: Journaling EXIT_LONG trade (with SAME trade_id)...')
print('-' * 70)

exit_doc_id = journal_trade(
    symbol=symbol,
    action="EXIT_LONG",
    side="sell",
    price=98500.00,
    order_size=3,
    leverage=5,
    mode="paper",
    trade_id=trade_id,  # 🔗 SAME trade_id links to entry above
    strategy_name=strategy_name,
    rsi=38.20,
    reason="Test exit - Trailing stop triggered",
    is_entry=False,
    is_partial_exit=False,
    entry_price=96000.00,
    exit_price=98500.00,
    execution_price=98485.75,
    pnl=7457.25,
    funding_charges=-18.50,
    trading_fees=35.10,
    margin_used=None,
    remaining_margin=17403.65,
    product_id=1,
    order_id="TEST_EXIT_LINKED_001"
)

if exit_doc_id:
    print(f'✅ Exit trade journaled!')
    print(f'   Document ID: {exit_doc_id}')
    print(f'   trade_id: {trade_id} (SAME as entry)\n')
else:
    print('❌ Failed to journal exit trade\n')

# Generate another trade_id for a different trade
time.sleep(1)
symbol2 = "ETHUSD"
timestamp_str2 = datetime.utcnow().strftime('%Y%m%d%H%M%S')
trade_id2 = f"{symbol2}_{strategy_name}_{timestamp_str2}_{uuid.uuid4().hex[:8]}"

print('='*70)
print('🔗 Generated DIFFERENT trade_id for a separate trade:')
print(f'   {trade_id2}\n')

# Test 3: Journal another ENTRY with different trade_id
print('-' * 70)
print('TEST 3: Journaling ENTRY_LONG for ETHUSD (different trade_id)...')
print('-' * 70)

entry2_doc_id = journal_trade(
    symbol=symbol2,
    action="ENTRY_LONG",
    side="buy",
    price=3500.00,
    order_size=5,
    leverage=5,
    mode="paper",
    trade_id=trade_id2,  # 🔗 Different trade_id for different trade
    strategy_name=strategy_name,
    rsi=62.30,
    reason="Test entry - RSI bullish divergence",
    is_entry=True,
    is_partial_exit=False,
    entry_price=3500.00,
    exit_price=None,
    execution_price=3501.25,
    pnl=None,
    funding_charges=None,
    trading_fees=None,
    margin_used=3500.00,
    remaining_margin=14000.00,
    product_id=27,
    order_id="TEST_ENTRY_LINKED_002"
)

if entry2_doc_id:
    print(f'✅ Entry trade journaled!')
    print(f'   Document ID: {entry2_doc_id}')
    print(f'   trade_id: {trade_id2}\n')
else:
    print('❌ Failed to journal entry trade\n')

# Summary
print('='*70)
print('📊 Test Summary')
print('='*70)
print(f'BTCUSD Entry:  {"✅ Success" if entry_doc_id else "❌ Failed"} - trade_id: {trade_id[:40]}...')
print(f'BTCUSD Exit:   {"✅ Success" if exit_doc_id else "❌ Failed"} - trade_id: {trade_id[:40]}... (SAME)')
print(f'ETHUSD Entry:  {"✅ Success" if entry2_doc_id else "❌ Failed"} - trade_id: {trade_id2[:40]}... (DIFFERENT)')
print('')
print('🔍 Verification Steps:')
print('   1. Open Firebase Console: https://console.firebase.google.com/')
print('   2. Navigate to: Firestore Database → trades collection')
print('   3. Filter/search by trade_id to see linked entry and exit')
print('   4. Verify:')
print('      - BTCUSD entry and exit share the SAME trade_id')
print('      - ETHUSD entry has a DIFFERENT trade_id')
print('      - You can now track complete trade journeys!')
print('')
print('='*70)
