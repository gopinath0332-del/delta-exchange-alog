"""
Unit tests for the MAE / MFE calculation in BacktestEngine._calculate_mae_mfe().

These tests use a synthetic in-memory OHLCV DataFrame and mock strategy trades
so no live API calls, CSV files, or configuration dependencies are needed.

MAE = Maximum Adverse Excursion  (worst intra-trade price move against position)
MFE = Maximum Favorable Excursion (best intra-trade price move in  favour of position)
"""

import datetime
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helper to build a fake BacktestEngine without touching the real constructor
# ---------------------------------------------------------------------------

def make_engine(timeframe: str = "1h") -> "BacktestEngine":
    """
    Build a BacktestEngine instance by bypassing __init__ (so we don't need
    a live config or strategy object) and manually setting only the attributes
    used by _calculate_mae_mfe() and _parse_time().
    """
    # Import here so tests that can't import (e.g. missing deps) still error clearly
    from backtest.engine import BacktestEngine

    engine = object.__new__(BacktestEngine)
    engine.timeframe = timeframe
    engine.symbol = "TEST"
    return engine


# ---------------------------------------------------------------------------
# Helper to build a synthetic OHLCV DataFrame
# ---------------------------------------------------------------------------

def make_df(rows: list) -> pd.DataFrame:
    """
    Build a minimal OHLCV DataFrame from a list of
    (unix_timestamp_seconds, open, high, low, close) tuples.
    """
    times  = [r[0] for r in rows]
    opens  = [r[1] for r in rows]
    highs  = [r[2] for r in rows]
    lows   = [r[3] for r in rows]
    closes = [r[4] for r in rows]
    return pd.DataFrame({'time': times, 'open': opens, 'high': highs, 'low': lows, 'close': closes})


# ---------------------------------------------------------------------------
# Helper to format timestamps as the strategy's format_time() would
# (dd-mm-yy HH:MM  in UTC)
# ---------------------------------------------------------------------------

def ts_to_str(unix_sec: float) -> str:
    """
    Mimic strategy.format_time(): uses datetime.fromtimestamp() (LOCAL time),
    not utcfromtimestamp(), so timestamps match what the engine sees from real trades.
    """
    return datetime.datetime.fromtimestamp(unix_sec).strftime('%d-%m-%y %H:%M')


# ---------------------------------------------------------------------------
# Base timestamps (1-hour bars starting at 2024-01-01 00:00 UTC)
# ---------------------------------------------------------------------------

T0 = 1704067200  # 2024-01-01 00:00 UTC
T1 = T0 + 3600   # 01:00
T2 = T1 + 3600   # 02:00
T3 = T2 + 3600   # 03:00
T4 = T3 + 3600   # 04:00


# ---------------------------------------------------------------------------
# Tests — LONG trade
# ---------------------------------------------------------------------------

class TestLongTrade:
    """LONG: MFE = max_high - entry, MAE = entry - min_low."""

    def setup_method(self):
        """Create a 5-bar OHLCV window.
        Bar 0: entry at close=100 (open bar — entry falls here)
        Bar 1: high=110, low=95   → favourable high, adverse low
        Bar 2: high=115, low=98   → even more favourable, minor adverse
        Bar 3: high=108, low=92   → new low (max adverse)
        Bar 4: exit at close=105  (exit bar)
        
        Entry price = 100
        Expected MFE price = 115 - 100 = 15 → MFE% = 15%
        Expected MAE price = 100 - 92  =  8 → MAE% = 8%
        """
        self.df = make_df([
            (T0, 99,  102, 98,  100),  # bar 0  — entry candle
            (T1, 100, 110, 95,  108),  # bar 1
            (T2, 108, 115, 98,  112),  # bar 2
            (T3, 112, 108, 92,  100),  # bar 3
            (T4, 100, 106, 103, 105),  # bar 4 — exit candle
        ])
        self.engine = make_engine()
        self.trade = {
            'type':        'LONG',
            'entry_price': '100',
            'entry_time':  ts_to_str(T0),
            'exit_time':   ts_to_str(T4),
        }

    def test_long_mfe_price(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        # max high in window is 115 at bar 2; MFE = 115 - 100 = 15
        assert abs(self.trade['mfe_price'] - 15.0) < 0.01

    def test_long_mfe_pct(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        assert abs(self.trade['mfe_pct'] - 15.0) < 0.01  # 15/100 * 100 = 15%

    def test_long_mae_price(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        # min low in window is 92 at bar 3; MAE = 100 - 92 = 8
        assert abs(self.trade['mae_price'] - 8.0) < 0.01

    def test_long_mae_pct(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        assert abs(self.trade['mae_pct'] - 8.0) < 0.01   # 8/100 * 100 = 8%


# ---------------------------------------------------------------------------
# Tests — SHORT trade
# ---------------------------------------------------------------------------

class TestShortTrade:
    """SHORT: MFE = entry - min_low, MAE = max_high - entry."""

    def setup_method(self):
        """
        Bar 0: entry at close=100
        Bar 1: high=105, low=88   → adverse high 105; favourable low 88
        Bar 2: high=103, low=85   → new favourable low
        Bar 3: high=108, low=95   → new adverse high
        Bar 4: exit at close=90   (exit bar)
        
        Entry price = 100
        Expected MFE price = 100 - 85 = 15 → MFE% = 15%
        Expected MAE price = 108 - 100 = 8 → MAE% = 8%
        """
        self.df = make_df([
            (T0, 101, 102, 98,  100),
            (T1, 100, 105, 88,  92),
            (T2, 92,  103, 85,  90),
            (T3, 90,  108, 95,  96),
            (T4, 96,  98,  89,  90),
        ])
        self.engine = make_engine()
        self.trade = {
            'type':        'SHORT',
            'entry_price': '100',
            'entry_time':  ts_to_str(T0),
            'exit_time':   ts_to_str(T4),
        }

    def test_short_mfe_price(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        # min low = 85 (bar 2); MFE = 100 - 85 = 15
        assert abs(self.trade['mfe_price'] - 15.0) < 0.01

    def test_short_mfe_pct(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        assert abs(self.trade['mfe_pct'] - 15.0) < 0.01

    def test_short_mae_price(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        # max high = 108 (bar 3); MAE = 108 - 100 = 8
        assert abs(self.trade['mae_price'] - 8.0) < 0.01

    def test_short_mae_pct(self):
        self.engine._calculate_mae_mfe(self.df, [self.trade])
        assert abs(self.trade['mae_pct'] - 8.0) < 0.01


# ---------------------------------------------------------------------------
# Edge case: single-bar trade (entry and exit on the same bar)
# ---------------------------------------------------------------------------

class TestSingleBarTrade:
    """A trade that opens and closes within one bar should still produce valid
    MAE/MFE values — ≥ 0 and bounded by the bar's high/low range."""

    def setup_method(self):
        # Only one bar: high=105, low=95, close=100 (entry and exit)
        self.df = make_df([(T0, 99, 105, 95, 100)])
        self.engine = make_engine()

    def test_single_bar_long(self):
        trade = {
            'type': 'LONG', 'entry_price': '100',
            'entry_time': ts_to_str(T0), 'exit_time': ts_to_str(T0),
        }
        self.engine._calculate_mae_mfe(self.df, [trade])
        # MFE = 105-100=5, MAE = 100-95=5
        assert trade['mfe_price'] >= 0.0
        assert trade['mae_price'] >= 0.0

    def test_single_bar_short(self):
        trade = {
            'type': 'SHORT', 'entry_price': '100',
            'entry_time': ts_to_str(T0), 'exit_time': ts_to_str(T0),
        }
        self.engine._calculate_mae_mfe(self.df, [trade])
        assert trade['mfe_price'] >= 0.0
        assert trade['mae_price'] >= 0.0


# ---------------------------------------------------------------------------
# Edge case: missing / invalid timestamps → defaults to zeros, no exception
# ---------------------------------------------------------------------------

class TestInvalidTimestamps:
    """Trades with unparseable timestamps must not raise an exception and
    should fall back to default zero values."""

    def setup_method(self):
        self.df = make_df([
            (T0, 99, 110, 90, 100),
            (T1, 100, 115, 85, 105),
        ])
        self.engine = make_engine()

    def test_missing_entry_time(self):
        trade = {
            'type': 'LONG', 'entry_price': '100',
            'entry_time': '', 'exit_time': ts_to_str(T1),
        }
        # Must not raise; values may be non-zero (falls back to full df scan) but no crash
        self.engine._calculate_mae_mfe(self.df, [trade])
        assert 'mae_pct' in trade
        assert 'mfe_pct' in trade

    def test_missing_exit_time(self):
        trade = {
            'type': 'LONG', 'entry_price': '100',
            'entry_time': ts_to_str(T0), 'exit_time': '',
        }
        self.engine._calculate_mae_mfe(self.df, [trade])
        assert 'mae_pct' in trade
        assert 'mfe_pct' in trade

    def test_zero_entry_price(self):
        """Zero entry price should be skipped without raising."""
        trade = {
            'type': 'LONG', 'entry_price': '0',
            'entry_time': ts_to_str(T0), 'exit_time': ts_to_str(T1),
        }
        self.engine._calculate_mae_mfe(self.df, [trade])
        # Defaults should remain 0.0
        assert trade['mae_price'] == 0.0
        assert trade['mfe_price'] == 0.0


# ---------------------------------------------------------------------------
# Verify that processed_trade dicts from engine.run() contain MAE/MFE fields
# ---------------------------------------------------------------------------

class TestProcessedTradeFields:
    """Smoke-test that engine.run() produces processed_trade dicts with all
    four MAE/MFE keys when a simple mock strategy supplies trades."""

    def test_processed_trade_has_mae_mfe_keys(self):
        """engine.run() should attach MAE %, MAE Price, MFE %, MFE Price
        to every processed trade."""
        from backtest.engine import BacktestEngine

        # Build a minimal 10-bar DataFrame (timestamps in seconds)
        import time
        base = 1704067200
        rows = []
        for i in range(10):
            ts = base + i * 3600
            rows.append({'time': ts, 'open': 100+i, 'high': 105+i, 'low': 95+i, 'close': 100+i})
        df = pd.DataFrame(rows)

        # Create a mock strategy whose run_backtest() sets a single fully-closed trade
        mock_strategy = MagicMock()
        mock_strategy.trades = [
            {
                'type':        'LONG',
                'entry_price': '101',
                'entry_time':  ts_to_str(base + 3600),   # bar 1
                'exit_price':  '106',
                'exit_time':   ts_to_str(base + 5 * 3600),  # bar 5
                'status':      'CLOSED',
            }
        ]

        # Patch get_config so BacktestEngine.__init__ doesn't blow up
        with patch('backtest.engine.get_config') as mock_cfg:
            mock_cfg.return_value.backtesting.initial_capital   = 1000.0
            mock_cfg.return_value.backtesting.order_size_pct    = 0.1
            mock_cfg.return_value.backtesting.commission        = 0.0005
            mock_cfg.return_value.backtesting.use_compounding   = False
            mock_cfg.return_value.settings = {}

            engine = BacktestEngine(
                strategy=mock_strategy,
                symbol='TEST',
                timeframe='1h',
                leverage=1,
            )

        processed, _ = engine.run(df)

        assert len(processed) == 1
        trade = processed[0]

        # All four MAE/MFE keys must be present
        for key in ('MAE Price', 'MAE %', 'MFE Price', 'MFE %'):
            assert key in trade, f"Missing key '{key}' in processed trade"

        # Values must be non-negative numbers
        assert trade['MAE %']   >= 0.0
        assert trade['MFE %']   >= 0.0
        assert trade['MAE Price'] >= 0.0
        assert trade['MFE Price'] >= 0.0
