"""Candle Aggregation Utility for unsupported timeframes."""

import pandas as pd
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def aggregate_candles_to_3h(candles_1h: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate 1-hour candles into 3-hour candles.
    
    Args:
        candles_1h: List of 1-hour OHLCV candles
        
    Returns:
        List of 3-hour OHLCV candles
    """
    if not candles_1h:
        return []
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(candles_1h)
    
    # Ensure time is in seconds (not milliseconds)
    if df['time'].iloc[0] > 1e11:
        df['time'] = df['time'] / 1000
    
    # Convert time to datetime for grouping
    df['datetime'] = pd.to_datetime(df['time'], unit='s')
    
    # Group by 3-hour intervals
    # Floor to 3-hour boundaries (0:00, 3:00, 6:00, 9:00, 12:00, 15:00, 18:00, 21:00)
    df['group'] = df['datetime'].dt.floor('3H')
    
    # Aggregate OHLCV data
    aggregated = df.groupby('group').agg({
        'time': 'first',  # Use timestamp of first candle in group
        'open': 'first',  # Open of first candle
        'high': 'max',    # Highest high
        'low': 'min',     # Lowest low
        'close': 'last',  # Close of last candle
        'volume': 'sum'   # Sum of volumes
    }).reset_index(drop=True)
    
    # Convert back to list of dicts
    candles_3h = aggregated.to_dict('records')
    
    logger.info(f"Aggregated {len(candles_1h)} 1h candles into {len(candles_3h)} 3h candles")
    
    return candles_3h
