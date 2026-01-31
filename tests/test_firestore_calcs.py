#!/usr/bin/env python3
"""Test calculated fields: days_held and pnl_percentage."""
import time
import uuid
from datetime import datetime
from core.config import get_config
from core.logger import setup_logging, get_logger
from core.firestore_client import journal_trade, get_firestore_status

logger = get_logger(__name__)
setup_logging(log_level='INFO')

print('\n' + '='*70)
print('🧪 Testing Calculated Fields: days_held & pnl_percentage')
print('='*70 + '\n')

# Initialize configuration
config = get_config()
print('')

# Check Firestore status
status = get_firestore_status()
if not status['connected']:
    print('❌ ERROR: Firestore is not connected!')
    exit(1)

print('✅ Firestore connected\n')

# Generate trade_id
symbol = "ETHUSD"
strategy_name = "Calc Fields Test"
timestamp_str = datetime.utcnow().strftime('%Y%m%d%H%M%S')
trade_id = f"{symbol}_{strategy_name}_{timestamp_str}_{uuid.uuid4().hex[:8]}"

print(f'📝 trade_id: {trade_id}\n')

# Create ENTRY
print('-' * 70)
print('STEP 1: Creating ENTRY')
print('-' * 70)

journal_trade(
    symbol=symbol,
    action="ENTRY_LONG",
    side="buy",
    price=3400.00,
    order_size=5,
    leverage=10,  # 10x leverage
    mode="paper",
    trade_id=trade_id,
    strategy_name=strategy_name,
    rsi=58.30,
    reason="Entry signal",
    is_entry=True,
    is_partial_exit=False,
    entry_price=3400.00,
    execution_price=3402.50,
    margin_used=1700.00,
    remaining_margin=8300.00,
    product_id=27,
    order_id="CALC_TEST_ENTRY"
)

print('✅ Entry created\n')

# Wait to simulate trade duration (5 seconds = ~0.00006 days)
print('⏳ Waiting 5 seconds to simulate trade duration...\n')
time.sleep(5)

# Create EXIT with profit
print('-' * 70)
print('STEP 2: Creating EXIT (with calculated fields)')
print('-' * 70)

# Exit at higher price for profit
exit_price_value = 3570.00  # +5% price increase
# Expected pnl_percentage = ((3570 - 3400) / 3400) * 100 * 10 = 5% * 10 = +50%

journal_trade(
    symbol=symbol,
    action="EXIT_LONG",
    side="sell",
    price=exit_price_value,
    order_size=5,
    leverage=10,
    mode="paper",
    trade_id=trade_id,
    strategy_name=strategy_name,
    rsi=42.10,
    reason="Profit target",
    is_entry=False,
    is_partial_exit=False,
    entry_price=3400.00,
    exit_price=exit_price_value,
    execution_price=3568.75,
    pnl=850.00,
    funding_charges=-5.25,
    trading_fees=12.50,
    remaining_margin=9532.25,
    product_id=27,
    order_id="CALC_TEST_EXIT"
)

print('✅ Exit updated with calculated fields\n')

# Summary
print('='*70)
print('📊 Expected Calculated Fields')
print('='*70)
print(f'Entry Price:   $3,400.00')
print(f'Exit Price:    $3,570.00')
print(f'Price Change:  +5.00%')
print(f'Leverage:      10x')
print('')
print(f'Expected pnl_percentage: +50.00% (5% × 10x leverage)')
print(f'Expected days_held:      ~0.00006 days (5 seconds)')
print('')
print('🔍 Verify in Firestore:')
print(f'   1. Find document: {trade_id}')
print('   2. Check fields:')
print('      - pnl_percentage: should be ~50.00')
print('      - days_held: should be ~0.00006')
print('      - status: CLOSED')
print('')
print('='*70)
