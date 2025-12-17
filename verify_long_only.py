
import sys
import os
import logging

# Add project root to path
sys.path.append('/Users/admin/Projects/delta-exchange-alog')

from strategies.double_dip_rsi import DoubleDipRSIStrategy

def test_long_only():
    strategy = DoubleDipRSIStrategy()
    
    # 1. Test Low RSI - Should NOT trigger ENTRY_SHORT
    print("Testing Low RSI (normally Short Entry)...")
    strategy.current_position = 0 # Flat
    strategy.require_prev_long_min_duration = False # Disable duration check to make it easier to trigger short if logic was there
    
    # Even if we disable duration check, the short logic is commented out, so it should return None
    action, reason = strategy.check_signals(current_rsi=20.0, current_time_ms=100000)
    
    print(f"Action: {action}, Reason: {reason}")
    if action == "ENTRY_SHORT":
        print("FAIL: Strategy triggered ENTRY_SHORT")
        sys.exit(1)
    else:
        print("PASS: Strategy did not trigger ENTRY_SHORT")

    # 2. Test High RSI - Should trigger ENTRY_LONG
    print("\nTesting High RSI (Long Entry)...")
    strategy.current_position = 0
    action, reason = strategy.check_signals(current_rsi=60.0, current_time_ms=100000)
    print(f"Action: {action}, Reason: {reason}")
    
    if action == "ENTRY_LONG":
        print("PASS: Strategy triggered ENTRY_LONG")
    else:
        print("FAIL: Strategy did not trigger ENTRY_LONG")
        sys.exit(1)

if __name__ == "__main__":
    test_long_only()
