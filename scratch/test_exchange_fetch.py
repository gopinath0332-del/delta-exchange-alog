import os
import time
from datetime import datetime
from core.config import get_config
from api.rest_client import DeltaRestClient
from core.logger import setup_logging

def test_fetch_transactions():
    setup_logging(log_level="INFO")
    config = get_config()
    client = DeltaRestClient(config)
    
    # Symbols from user report
    symbols = ["PIPPINUSD", "RIVERUSD"]
    products = client.get_products()
    
    for symbol in symbols:
        product = next((p for p in products if p['symbol'] == symbol), None)
        if not product:
            print(f"Product {symbol} not found")
            continue
            
        product_id = product['id']
        print(f"\n--- Testing {symbol} (ID: {product_id}) ---")
        
        # Test window: last 24 hours to find recent exits
        now_us = int(time.time() * 1_000_000)
        start_us = now_us - (24 * 60 * 60 * 1_000_000)
        
        print(f"Fetching transactions from {datetime.fromtimestamp(start_us/1e6)} to {datetime.fromtimestamp(now_us/1e6)}")
        
        try:
            orders = client.get_order_history(
                product_id=product_id,
                start_time=start_us,
                end_time=now_us
            )
            
            if orders:
                print(f"Found {len(orders)} orders")
                import pprint
                pprint.pprint(orders[0])
            else:
                print("No orders found in the last 24 hours.")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_fetch_transactions()
