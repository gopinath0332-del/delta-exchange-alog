import os
from dotenv import load_dotenv
from api.rest_client import DeltaRestClient
from core.config import Config
from core.logger import get_logger

logger = get_logger(__name__)

def debug_wallet():
    """
    Debug script to verify the exact asset symbols and balances 
    returned by the Delta Exchange API.
    """
    load_dotenv()
    
    # Initialize config and client
    config = Config()
    client = DeltaRestClient(config)
    
    print("\n--- Delta Exchange Wallet Debug ---")
    try:
        # Fetch balances
        response = client.get_wallet_balance()
        balances = response.get('result', [])
        
        found_usdt = False
        for balance in balances:
            symbol = balance.get('asset_symbol')
            total = balance.get('balance')
            available = balance.get('available_balance')
            
            # Print any asset that has a balance > 0
            if float(total) > 0:
                print(f"[OK] Asset: {symbol}")
                print(f"   Total Balance: {total}")
                print(f"   Available: {available}")
                print("-" * 30)
                if symbol == "USDT":
                    found_usdt = True
        
        if not found_usdt:
            print("[WARN] 'USDT' asset not found in your wallet response.")
            print("Please see the symbols listed above and tell me which one has your $273.")
        else:
            print("[SUCCESS] 'USDT' found. The 1% Risk Model is ready for launch!")

    except Exception as e:
        print(f"[ERROR] Failed to fetch balance. Check your API keys in .env.")
        print(f"Details: {e}")

if __name__ == "__main__":
    debug_wallet()
