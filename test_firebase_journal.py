#!/usr/bin/env python3
"""
Test script for Firebase Journal Integration
"""
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.firebase_journal import get_journal_service

def test_firebase_connection():
    """Test Firebase journal service initialization"""
    print("Testing Firebase Journal Service...\n")
    
    journal = get_journal_service()
    
    if not journal.enabled:
        print("❌ Firebase journal is disabled or misconfigured")
        print("Please check config/.env:")
        print("  - ENABLE_FIREBASE_JOURNAL=true")
        print("  - FIREBASE_API_KEY=...")
        print("  - FIREBASE_PROJECT_ID=...")
        print("  - FIREBASE_USER_ID=...")
        print("  - FIREBASE_CRYPTO_PROFILE_ID=...")
        return False
    
    print("✓ Firebase journal service initialized")
    print(f"  Project ID: {journal.project_id}")
    print(f"  Profile ID: {journal.profile_id}")
    print(f"  User ID: {journal.user_id[:10]}..." if journal.user_id and len(journal.user_id) > 10 else f"  User ID: {journal.user_id}")
    
    return True

def test_log_entry():
    """Test logging a trade entry"""
    print("\nTesting trade entry logging...")
    
    journal = get_journal_service()
    
    # Log a test trade
    trade_id = journal.log_entry(
        symbol="BTCUSD",
        trade_type="BUY",
        entry_price=50000.0,
        quantity=1,
        strategy="TEST",
        contract="Perpetual"
    )
    
    if trade_id:
        print(f"✓ Test trade logged successfully!")
        print(f"  Trade ID: {trade_id}")
        return trade_id
    else:
        print("❌ Failed to log test trade")
        return None

def test_update_exit(trade_id):
    """Test updating a trade exit"""
    if not trade_id:
        print("\nSkipping exit test (no trade ID)")
        return
    
    print("\nTesting trade exit update...")
    
    journal = get_journal_service()
    
    # Update with exit
    success = journal.update_exit(
        trade_id=trade_id,
        exit_price=51000.0,
        pnl_amount=1000.0,
        pnl_percentage=2.0,
        is_partial=False
    )
    
    if success:
        print("✓ Trade exit updated successfully!")
    else:
        print("❌ Failed to update trade exit")

if __name__ == "__main__":
    print("=" * 60)
    print("Firebase Trade Journal Integration Test")
    print("=" * 60)
    
    # Test 1: Initialize
    if not test_firebase_connection():
        sys.exit(1)
    
    # Test 2: Log entry
    trade_id = test_log_entry()
    
    # Test 3: Update exit
    if trade_id:
        test_update_exit(trade_id)
    
    print("\n" + "=" * 60)
    print("Test complete! Check your MyTradeJournal app to verify.")
    print("=" * 60)
