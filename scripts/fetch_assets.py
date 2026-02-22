
import os
import sys
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_config
from core.logger import setup_logging, get_logger
from api.rest_client import DeltaRestClient

def fetch_and_save_assets():
    """
    Fetch all available assets from Delta Exchange and save to Excel.
    """
    logger = get_logger(__name__)
    
    try:
        # Initialize
        setup_logging(log_level="INFO")
        config = get_config()
        client = DeltaRestClient(config)
        
        logger.info("Fetching products from Delta Exchange...")
        products = client.get_products()
        
        if not products:
            logger.warning("No products found.")
            return

        logger.info(f"Found {len(products)} products. Processing data...")
        
        # Create DataFrame
        df = pd.DataFrame(products)
        
        # Select relevant columns if they exist, otherwise keep all but organize
        # Common useful columns for traders
        target_columns = [
            'symbol', 'description', 'base_asset_symbol', 'quote_currency', 
            'contract_type', 'state', 'contract_value', 'tick_size', 
            'maker_commission_rate', 'taker_commission_rate', 'is_quanto',
            'initial_margin', 'maintenance_margin', 'sort_priority'
        ]
        
        # Filter columns that actually exist in the response
        existing_columns = [col for col in target_columns if col in df.columns]
        
        # Add any other columns at the end
        other_columns = [col for col in df.columns if col not in existing_columns]
        final_columns = existing_columns + other_columns
        
        # Reorder DataFrame
        df = df[final_columns]
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"delta_assets_{timestamp}.xlsx"
        
        # Save to Excel
        logger.info(f"Saving to {filename}...")
        df.to_excel(filename, index=False)
        
        logger.info(f"Successfully saved {len(df)} assets to {filename}")
        print(f"\nSuccess! Asset list saved to: {os.path.abspath(filename)}")
        
    except Exception as e:
        logger.error(f"Failed to fetch and save assets: {e}", exc_info=True)
        print(f"\nError: {e}")

if __name__ == "__main__":
    fetch_and_save_assets()
