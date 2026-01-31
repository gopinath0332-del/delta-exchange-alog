#!/usr/bin/env python3
"""Test Firestore single-document trade journaling with status updates."""
import time
import uuid
from datetime import datetime
from core.config import get_config
from core.logger import setup_logging, get_logger
from core.firestore_client import journal_trade, get_firestore_status

logger = get_logger(__name__)
setup_logging(log_level='INFO')

print('\n' + '='*70)
print('🧪 Firestore SINGLE-DOCUMENT Trade Journaling Test')
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

# Generate a unique trade_id
symbol = "BTCUSD"
strategy_name = "Single Doc Test"
timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M%S')
trade_id = f"{symbol}_{strategy_name}_{timestamp_str}_{uuid.uuid4().hex[:8]}"

print('📝 Testing SINGLE document per trade approach')
print(f'   trade_id: {trade_id}\n')

# Step 1: Create ENTRY (status = OPEN)
print('-' * 70)
print('STEP 1: Creating trade document with status = OPEN')
print('-' * 70)

entry_result = journal_trade(
    symbol=symbol,
    action="ENTRY_LONG",
    side="buy",
    price=95500.00,
    order_size=2,
    leverage=5,
    mode="paper",
    trade_id=trade_id,
    strategy_name=strategy_name,
    rsi=56.80,
    reason="Test - Bullish breakout",
    is_entry=True,
    is_partial_exit=False,
    entry_price=95500.00,
    exit_price=None,
    execution_price=95508.50,
    pnl=None,
    funding_charges=None,
    trading_fees=None,
    margin_used=38200.00,
    remaining_margin=11800.00,
    product_id=1,
    order_id="ENTRY_ORDER_001"
)

if entry_result:
    print(f'\n✅ SUCCESS! Trade document created')
    print(f'   Document ID: {entry_result}')
    print(f'   Status: OPEN\n')
else:
    print('\n❌ Failed to create entry\n')
    exit(1)

# Wait to simulate time between entry and exit
print('⏳ Simulating time passing (3 seconds)...\n')
time.sleep(3)

# Step 2: Update to EXIT (status = CLOSED)
print('-' * 70)
print('STEP 2: Updating SAME document with exit data (status = CLOSED)')
print('-' * 70)

exit_result = journal_trade(
    symbol=symbol,
    action="EXIT_LONG",
    side="sell",
    price=97800.00,
    order_size=2,
    leverage=5,
    mode="paper",
    trade_id=trade_id,  # SAME trade_id - updates existing doc
    strategy_name=strategy_name,
    rsi=41.20,
    reason="Test - Profit target hit",
    is_entry=False,
    is_partial_exit=False,
    entry_price=95500.00,
    exit_price=97800.00,
    execution_price=97792.25,
    pnl=4584.50,
    funding_charges=-15.75,
    trading_fees=28.90,
    margin_used=None,
    remaining_margin=16339.85,
    product_id=1,
    order_id="EXIT_ORDER_001"
)

if exit_result:
    print(f'\n✅ SUCCESS! Trade document updated')
    print(f'   Document ID: {exit_result} (SAME as entry)')
    print(f'   Status: CLOSED')
    print(f'   PnL: ${4584.50:+,.2f}\n')
else:
    print('\n❌ Failed to update with exit\n')

# Summary
print('='*70)
print('📊 Test Summary')
print('='*70)
print(f'Entry (CREATE):  {"✅ Success" if entry_result else "❌ Failed"}')
print(f'Exit (UPDATE):   {"✅ Success" if exit_result else "❌ Failed"}')
print(f'Document ID:     {trade_id}')
print('')
print('🎯 Expected Result in Firestore:')
print('   - ONE single document (not two separate documents)')
print('   - Document ID = trade_id')
print('   - Has both entry_ and exit_ fields')
print('   - status field changed from OPEN → CLOSED')
print('')
print('🔍 Verification Steps:')
print('   1. Open Firebase Console: https://console.firebase.google.com/')
print('   2. Navigate to: Firestore Database → trades collection')
print('   3. Find the document with ID: ' + trade_id[:50] + '...')
print('   4. Verify:')
print('      ✓ ONLY ONE document for this trade (not two)')
print('      ✓ Has entry_timestamp AND exit_timestamp')
print('      ✓ Has entry_price AND exit_price')
print('      ✓ Has pnl, funding_charges, trading_fees')
print('      ✓ status = "CLOSED"')
print('')
print('='*70)
