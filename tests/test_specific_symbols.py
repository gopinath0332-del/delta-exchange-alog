#!/usr/bin/env python3
"""Quick test to verify specific symbols loading."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config import get_config
from core.logger import setup_logging, get_logger
from api.rest_client import DeltaRestClient

def test_specific_symbols():
    """Test loading specific crypto futures."""
    # Setup
    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger(__name__)
    
    client = DeltaRestClient(config)
    
    print("\n" + "="*70)
    print("Testing Specific Crypto Futures Loading")
    print("="*70 + "\n")
    
    target_symbols = ["BTCUSD", "ETHUSD", "SOLUSD"]
    
    # Fetch all futures
    print("1. Fetching all futures products...")
    all_products = client.get_futures_products()
    print(f"   Total futures available: {len(all_products)}")
    
    # Filter for specific symbols
    print(f"\n2. Filtering for specific symbols: {target_symbols}")
    products = [p for p in all_products if p.get("symbol") in target_symbols]
    print(f"   Found {len(products)} matching products:")
    for p in products:
        print(f"   - {p.get('symbol')}: {p.get('description', 'N/A')}")
    
    # Get tickers
    print(f"\n3. Fetching ticker data for {len(products)} products...")
    symbols = [p.get("symbol") for p in products]
    tickers = client.get_tickers_batch(symbols)
    print(f"   Fetched {len(tickers)} tickers:")
    
    for symbol, ticker in tickers.items():
        price = ticker.get("close", 0)
        volume = ticker.get("volume", 0)
        oi = ticker.get("open_interest", 0)
        print(f"   {symbol}: Price=${price:,.2f}, Volume=${volume:,.0f}, OI=${oi:,.0f}")
    
    print("\n" + "="*70)
    print("Test completed successfully!")
    print("="*70 + "\n")
    
    return True

if __name__ == "__main__":
    try:
        success = test_specific_symbols()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
