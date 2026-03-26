"""
backtest/candle_transform.py
----------------------------
Utility functions for transforming raw OHLCV candle data before
running a backtest simulation.

Currently supported transforms:
  - Heikin Ashi (HA): smoother candles that reduce noise and make
    trend signals cleaner. Signals generated on HA candles may differ
    from those on standard candles.

Heikin Ashi formulas
--------------------
  HA_Close = (Open + High + Low + Close) / 4
  HA_Open  = (prev_HA_Open + prev_HA_Close) / 2
              first bar: (Open + Close) / 2
  HA_High  = max(High, HA_Open, HA_Close)
  HA_Low   = min(Low,  HA_Open, HA_Close)
"""

import pandas as pd
import numpy as np
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


def apply_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform a standard OHLCV DataFrame into Heikin Ashi candles.

    The function creates a *new* DataFrame so the caller's original data
    is never mutated.  The raw (standard) 'close' column is preserved as
    'raw_close' so that price-based calculations that must reflect real
    market prices (e.g. MAE/MFE, position sizing) can still access it.

    Args:
        df: DataFrame with columns ['open', 'high', 'low', 'close'] and
            optionally ['volume', 'time'].  Values must be numeric.

    Returns:
        A new DataFrame with the same index and columns as ``df`` but
        with OHLC values replaced by Heikin Ashi equivalents.
        The original 'close' is kept in a 'raw_close' column.

    Raises:
        ValueError: If required OHLC columns are missing.
    """
    # Validate that the required columns are present
    required_cols = {'open', 'high', 'low', 'close'}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"apply_heikin_ashi: DataFrame is missing columns: {missing}"
        )

    # Work on a copy so we never mutate the caller's DataFrame
    ha = df.copy()

    # --- Step 1: Preserve original close for downstream calculations ------
    ha['raw_close'] = ha['close'].values

    # --- Step 2: Compute HA Close -----------------------------------------
    # HA_Close is always the average of the four standard OHLC values.
    ha_close = (
        df['open'].values + df['high'].values +
        df['low'].values  + df['close'].values
    ) / 4.0

    # --- Step 3: Compute HA Open iteratively (depends on previous bar) ----
    n = len(df)
    ha_open = np.empty(n, dtype=float)

    # Seed: first bar's HA_Open uses standard (Open + Close) / 2
    ha_open[0] = (df['open'].iloc[0] + df['close'].iloc[0]) / 2.0

    # Each subsequent HA_Open is the midpoint of the *previous* HA bar
    for i in range(1, n):
        ha_open[i] = (ha_open[i - 1] + ha_close[i - 1]) / 2.0

    # --- Step 4: Compute HA High and HA Low capping on HA_Open/HA_Close ---
    # HA_High must be at least as high as both HA_Open and HA_Close
    ha_high = np.maximum(
        df['high'].values,
        np.maximum(ha_open, ha_close)
    )

    # HA_Low must be at most as low as both HA_Open and HA_Close
    ha_low = np.minimum(
        df['low'].values,
        np.minimum(ha_open, ha_close)
    )

    # --- Step 5: Write transformed OHLC back into the copy ----------------
    ha['open']  = ha_open
    ha['high']  = ha_high
    ha['low']   = ha_low
    ha['close'] = ha_close

    logger.debug(
        f"Heikin Ashi transform applied: {n} bars processed. "
        f"First HA_Open={ha_open[0]:.4f}, Last HA_Close={ha_close[-1]:.4f}"
    )

    return ha
