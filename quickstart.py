"""Quick start example for the Delta Exchange trading platform."""

import sys
from pathlib import Path

from api.rest_client import DeltaRestClient
from core.config import get_config
from core.logger import setup_logging

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    """Run quick start example."""
    # 1. Setup logging
    print("=" * 60)
    print("Delta Exchange Trading Platform - Quick Start")
    print("=" * 60)
    print()

    setup_logging(log_level="INFO")

    # 2. Load configuration
    print("Loading configuration...")
    try:
        config = get_config()
        print(f"✓ Environment: {config.environment}")
        print(f"✓ Base URL: {config.base_url}")
        print(f"✓ Timeframes: {', '.join(config.timeframes)}")
        print()
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        print("\nPlease ensure:")
        print("1. config/.env file exists (copy from config/.env.example)")
        print("2. DELTA_API_KEY and DELTA_API_SECRET are set")
        return

    # 3. Initialize API client
    print("Initializing Delta Exchange API client...")
    try:
        client = DeltaRestClient(config)
        print("✓ API client initialized")
        print()
    except Exception as e:
        print(f"✗ API client error: {e}")
        return

    # 4. Fetch available products
    print("Fetching available products...")
    try:
        products = client.get_products()
        print(f"✓ Found {len(products)} products")

        # Show first 5 products
        print("\nFirst 5 products:")
        for i, product in enumerate(products[:5], 1):
            symbol = product.get("symbol", "N/A")
            product_id = product.get("id", "N/A")
            print(f"  {i}. {symbol} (ID: {product_id})")
        print()
    except Exception as e:
        print(f"✗ Failed to fetch products: {e}")
        return

    # 5. Get ticker for BTCUSD
    print("Fetching ticker for BTCUSD...")
    try:
        ticker = client.get_ticker("BTCUSD")
        if ticker:
            price = ticker.get("close", ticker.get("mark_price", "N/A"))
            print(f"✓ BTCUSD Price: ${price}")
            print()
        else:
            print("✗ No ticker data available")
            print()
    except Exception as e:
        print(f"✗ Failed to fetch ticker: {e}")
        print()

    # 6. Fetch historical data
    print("Fetching historical candles (last 7 days, 1h timeframe)...")
    try:
        candles = client.get_historical_candles(symbol="BTCUSD", resolution="1h", days=7)
        print(f"✓ Fetched {len(candles)} candles")

        if candles:
            # Show last 3 candles
            print("\nLast 3 candles:")
            for candle in candles[-3:]:
                timestamp = candle.get("time", "N/A")
                open_price = candle.get("open", "N/A")
                high = candle.get("high", "N/A")
                low = candle.get("low", "N/A")
                close = candle.get("close", "N/A")
                volume = candle.get("volume", "N/A")
                print(f"  Time: {timestamp}")
                print(f"    O: {open_price}, H: {high}, L: {low}, C: {close}, V: {volume}")
        print()
    except Exception as e:
        print(f"✗ Failed to fetch candles: {e}")
        print()

    # 7. Get wallet balance (requires authentication)
    print("Fetching wallet balance...")
    try:
        balance = client.get_wallet_balance()
        if balance:
            print("✓ Wallet balance fetched")
            # Note: Balance structure may vary
            print(f"  Balance data: {balance}")
        else:
            print("✗ No balance data available")
        print()
    except Exception as e:
        print(f"✗ Failed to fetch balance: {e}")
        print("  (This is normal if API keys don't have proper permissions)")
        print()

    # Summary
    print("=" * 60)
    print("Quick Start Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Explore the API client methods in api/rest_client.py")
    print("2. Check out the data models in data/models.py")
    print("3. Review the configuration in config/settings.yaml")
    print("4. Run: python main.py fetch-data --symbol BTCUSD --timeframe 1h")
    print()
    print("For more information, see README.md")
    print()


if __name__ == "__main__":
    main()
