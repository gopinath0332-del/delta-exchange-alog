"""
Candle Utilities Module.

Provides standardized utilities for working with candle data,
including closed candle detection for consistent signal generation.
"""

import pandas as pd
from core.logger import get_logger

logger = get_logger(__name__)


def get_closed_candle_index(df: pd.DataFrame, current_time_ms: float, timeframe: str) -> int:
    """
    Determine the index of the most recent CLOSED candle.
    
    This function checks if the most recent candle (df.iloc[-1]) has closed
    based on the current time and the specified timeframe. This ensures that
    strategies only use confirmed candle data for signal generation, matching
    backtesting behavior and eliminating false signals from developing candles.
    
    Args:
        df: DataFrame containing candle data with 'time' column (unix timestamp in seconds or milliseconds)
        current_time_ms: Current time in milliseconds
        timeframe: Candle timeframe string (e.g., '1h', '3h', '180m', '4h', '1d')
    
    Returns:
        int: Index of the closed candle
            -1: Most recent candle has closed (use df.iloc[-1])
            -2: Most recent candle is still developing (use df.iloc[-2])
    
    Examples:
        >>> # If current time is 14:45 and we're on 1h candles
        >>> # Last candle started at 14:00, still developing
        >>> idx = get_closed_candle_index(df, time_ms, '1h')
        >>> idx  # Returns -2 (use previous closed candle)
        
        >>> # If current time is 14:05 and last candle is from 13:00-14:00
        >>> # Last candle has closed
        >>> idx = get_closed_candle_index(df, time_ms, '1h')
        >>> idx  # Returns -1 (most recent is closed)
    """
    if df.empty or 'time' not in df.columns:
        logger.warning("Empty dataframe or missing 'time' column")
        return -1
    
    # Map timeframe to seconds
    timeframe_seconds = {
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '3h': 10800,
        '180m': 10800,  # 3h in minutes
        '4h': 14400,
        '1d': 86400,
    }
    
    if timeframe not in timeframe_seconds:
        logger.warning(f"Unknown timeframe '{timeframe}', defaulting to 1h (3600s)")
        candle_duration = 3600
    else:
        candle_duration = timeframe_seconds[timeframe]
    
    # Get current time in seconds
    current_time_s = current_time_ms / 1000.0
    
    # Get last candle timestamp
    last_candle_ts = df['time'].iloc[-1]
    
    # Handle timestamps in milliseconds (convert to seconds)
    if last_candle_ts > 1e11:
        last_candle_ts /= 1000
    
    # Calculate time difference
    time_diff = current_time_s - last_candle_ts
    
    # Determine if candle has closed
    # If time difference >= candle duration, the candle has closed
    closed_idx = -1 if time_diff >= candle_duration else -2
    
    if closed_idx == -1:
        logger.debug(f"Using index -1 (closed candle): {time_diff:.0f}s >= {candle_duration}s")
    else:
        logger.debug(f"Using index -2 (developing candle): {time_diff:.0f}s < {candle_duration}s")
    
    return closed_idx


def get_timeframe_seconds(timeframe: str) -> int:
    """
    Convert timeframe string to seconds.
    
    Args:
        timeframe: Timeframe string (e.g., '1h', '3h', '4h', '1d')
    
    Returns:
        int: Duration in seconds
    """
    timeframe_map = {
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '3h': 10800,
        '180m': 10800,
        '4h': 14400,
        '1d': 86400,
    }
    
    return timeframe_map.get(timeframe, 3600)  # Default to 1h
