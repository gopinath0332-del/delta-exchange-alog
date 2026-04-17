import os
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from api.rest_client import DeltaRestClient
from core.config import get_config
from core.logger import get_logger

logger = get_logger(__name__)

def fetch_and_save_metadata(output_path="data/historical/product_metadata.json"):
    """
    Fetch all product metadata from Delta Exchange and save it to a JSON file.
    """
    try:
        config = get_config()
        client = DeltaRestClient(config)
        
        logger.info("Fetching products from Delta Exchange...")
        products = client.get_products()
        
        metadata = {}
        for p in products:
            symbol = p.get("symbol")
            if not symbol:
                continue
                
            # Store useful fields for backtesting
            metadata[symbol] = {
                "contract_value": float(p.get("contract_value", 1.0)),
                "tick_size": float(p.get("tick_size", 0.1)),
                "maker_commission_rate": float(p.get("maker_commission_rate", 0.0002)),
                "taker_commission_rate": float(p.get("taker_commission_rate", 0.0005)),
                "lot_size": float(p.get("lot_size", 1.0)),
                "contract_type": p.get("contract_type"),
                "id": p.get("id")
            }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(metadata, f, indent=4)
            
        logger.info(f"Successfully saved metadata for {len(metadata)} products to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to fetch metadata: {e}")
        return False

if __name__ == "__main__":
    fetch_and_save_metadata()
