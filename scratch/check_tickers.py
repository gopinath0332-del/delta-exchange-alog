import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import get_config
from api.rest_client import DeltaRestClient

def main():
    config = get_config()
    client = DeltaRestClient(config)
    
    symbols = ["SPCXXUSD", "VELVETUSD", "ALLOUSD", "OPNUSD"]
    for s in symbols:
        try:
            ticker = client.get_ticker(s)
            print(f"=== {s} ===")
            if ticker:
                for k, v in ticker.items():
                    print(f"  {k}: {v}")
            else:
                print("  No ticker data returned")
        except Exception as e:
            print(f"  Error fetching {s}: {e}")

if __name__ == "__main__":
    main()
