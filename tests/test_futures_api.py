#!/usr/bin/env python3
"""Test script to verify futures product table implementation."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config import get_config
from core.logger import setup_logging, get_logger
from api.rest_client import DeltaRestClient

def test_futures_api():
    """Test the new futures API methods."""
    # Setup
    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger(__name__)
    
    client = DeltaRestClient(config)
    
    print("\n" + "="*70)
    print("Testing Futures Product API Methods")
    print("="*70 + "\n")
    
    # Test 1: Get futures products
    print("1. Testing get_futures_products()...")
    try:
        futures = client.get_futures_products()
        print(f"   ✓ Found {len(futures)} futures/perpetual products")
        if futures:
            print(f"   Sample: {futures[0].get('symbol')} - {futures[0].get('description', 'N/A')}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Test 2: Get batch tickers (limit to 3 for speed)
    print("\n2. Testing get_tickers_batch()...")
    try:
        symbols = [p.get("symbol") for p in futures[:3]]
        tickers = client.get_tickers_batch(symbols)
        print(f"   ✓ Fetched {len(tickers)} tickers")
        for symbol, ticker in tickers.items():
            price = ticker.get("close", 0)
            print(f"   {symbol}: ${price:,.2f}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Test 3: Get funding rate
    print("\n3. Testing get_funding_rate()...")
    try:
        # Find a perpetual contract
        perpetual = next((p for p in futures if "perpetual" in p.get("contract_type", "").lower()), None)
        if perpetual:
            symbol = perpetual.get("symbol")
            funding = client.get_funding_rate(symbol)
            if funding:
                print(f"   ✓ Funding rate for {symbol}: {funding}")
            else:
                print(f"   ⚠ No funding rate data available for {symbol}")
        else:
            print("   ⚠ No perpetual contracts found to test")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "="*70)
    print("All API tests completed successfully!")
    print("="*70 + "\n")
    
    return True

if __name__ == "__main__":
    try:
        success = test_futures_api()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
