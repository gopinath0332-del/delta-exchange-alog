
import os
import sys
import pandas as pd
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import get_config
from core.logger import setup_logging, get_logger
from api.rest_client import DeltaRestClient

def fetch_backtest_data(symbols, timeframe="1h", days=90):
    setup_logging(log_level="INFO")
    logger = get_logger(__name__)
    config = get_config()
    client = DeltaRestClient(config)
    
    data_dir = Path("data/historical")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    for symbol in symbols:
        logger.info(f"Fetching {days} days of {timeframe} data for {symbol}...")
        try:
            candles = client.get_historical_candles(
                symbol=symbol,
                resolution=timeframe,
                days=days
            )
            
            if not candles:
                logger.warning(f"No data received for {symbol}")
                continue
                
            df = pd.DataFrame(candles)
            
            # Map API column names to what DataLoader expects if necessary
            # DataLoader expects: time, open, high, low, close, volume
            # The API returns: {'time': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}
            # so it should be fine.
            
            filename = f"{symbol}_{timeframe}.csv"
            filepath = data_dir / filename
            df.to_csv(filepath, index=False)
            logger.info(f"Saved {len(df)} rows to {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")

if __name__ == "__main__":
    # Symbols from settings.yaml + some extras for comparison
    symbols_to_fetch = [
        "PIPPINUSD", "PIUSD", "JTOUSD", "RIVERUSD", "TAOUSD", "HYPEUSD",
        "BTCUSD", "ETHUSD", "SOLUSD", "SUIUSD", "XRPUSD"
    ]
    fetch_backtest_data(symbols_to_fetch)
