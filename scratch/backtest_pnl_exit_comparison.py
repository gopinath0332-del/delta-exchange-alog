#!/usr/bin/env python3
"""
Backtest Comparison: Donchian Strategy — Baseline vs PnL ≥99% Exit Idea

Runs both versions for all multi_coin → donchian_channel symbols and
prints a side-by-side comparison table. Results also saved as markdown.

Usage:
    python scratch/backtest_pnl_exit_comparison.py
"""

import os
import sys
import time

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Set TZ to UTC for consistent timestamp reporting (matches run_backtest.py)
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from typing import Dict, List, Tuple, Optional
import pandas as pd

from core.logger import setup_logging, get_logger
from core.config import get_config
from core.trading import get_trade_config
from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.candle_transform import apply_heikin_ashi

setup_logging(log_level="WARNING")  # Suppress INFO noise during batch run
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Multi-coin donchian_channel symbols + their timeframes/candle config
# (mirrors config/settings.yaml → multi_coin.donchian_channel)
# ---------------------------------------------------------------------------
SYMBOLS = [
    {"symbol": "PIPPINUSD", "timeframe": "1h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "ZECUSD",    "timeframe": "1h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "PAXGUSD",   "timeframe": "1h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "RIVERUSD",  "timeframe": "2h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "EVAAUSD",   "timeframe": "2h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "DEEPUSD",   "timeframe": "4h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "BERAUSD",   "timeframe": "4h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "IPUSD",     "timeframe": "6h",  "candle_type": "heikin_ashi", "leverage": 5},
    {"symbol": "VVVUSD",    "timeframe": "6h",  "candle_type": "heikin_ashi", "leverage": 5},
]

# Timeframe → data folder mapping
TF_TO_FOLDER = {
    "1h": r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H",
    "2h": r"D:\Workspace\crypto-backtest-data\delta_crypto_data_2H",
    "4h": r"D:\Workspace\crypto-backtest-data\delta_crypto_data_4H",
    "6h": r"D:\Workspace\crypto-backtest-data\delta_crypto_data_6h",
}

PNL_EXIT_THRESHOLD = 99.0  # Exit when margin PnL% >= this value


def get_strategy(pnl_exit_pct: Optional[float] = None, timeframe: str = "1h"):
    """Create a DonchianChannelStrategy instance, optionally with PnL exit enabled."""
    from strategies.donchian_strategy import DonchianChannelStrategy
    strategy = DonchianChannelStrategy()
    strategy._suppress_persistence = True
    strategy.timeframe = timeframe
    if hasattr(strategy, '_update_bars_per_day'):
        strategy._update_bars_per_day(timeframe)
    # Inject PnL exit threshold (None = disabled for baseline)
    strategy.pnl_exit_pct = pnl_exit_pct
    return strategy


def run_single_backtest(symbol: str, timeframe: str, candle_type: str,
                        leverage: int, data_folder: str,
                        pnl_exit_pct: Optional[float]) -> Optional[Dict]:
    """Run one backtest and return metrics dict, or None on failure."""
    folder = Path(data_folder)
    csv_file = folder / f"{symbol}_{timeframe}.csv"
    if not csv_file.exists():
        print(f"  [WARN] CSV not found: {csv_file}")
        return None

    loader = DataLoader(str(folder))
    df = loader.load_data(csv_file)
    if df.empty:
        print(f"  [WARN] Empty data for {symbol}")
        return None

    if candle_type == "heikin_ashi":
        df = apply_heikin_ashi(df)

    strategy = get_strategy(pnl_exit_pct=pnl_exit_pct, timeframe=timeframe)
    strategy.leverage = leverage

    engine = BacktestEngine(
        strategy, symbol, timeframe,
        strategy_name="donchian_channel",
        leverage=leverage
    )
    trades, equity_df = engine.run(df)

    # Capture raw strategy trades BEFORE engine processes them (for status-based counting)
    raw_strategy_trades = list(getattr(strategy, 'trades', []))

    label = f"donchian_channel ({symbol})"
    metrics = calculate_metrics(
        strategy_name=label,
        initial_capital=engine.initial_capital,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df,
        data_df=df
    )
    metrics['Symbol'] = symbol
    metrics['Timeframe'] = timeframe
    metrics['RawTrades'] = raw_strategy_trades  # raw for status counting
    return metrics


def count_pnl_exits(metrics: dict) -> int:
    """Count trades closed by the PnL exit condition using raw strategy trades."""
    return sum(1 for t in metrics.get('RawTrades', []) if t.get('status') == 'PNL EXIT')


def format_delta(new_val, base_val, higher_is_better=True, is_pct=False):
    """Return a formatted delta string with arrow."""
    if base_val == 0:
        return "N/A"
    diff = new_val - base_val
    arrow = ""
    if diff > 0:
        arrow = "▲" if higher_is_better else "▼"
    elif diff < 0:
        arrow = "▼" if higher_is_better else "▲"
    fmt = f"{diff:+.2f}%" if is_pct else f"{diff:+.2f}"
    return f"{arrow} {fmt}"


def main():
    print("\n" + "=" * 80)
    print("  DONCHIAN STRATEGY — BACKTEST COMPARISON")
    print(f"  Baseline vs PnL ≥{PNL_EXIT_THRESHOLD:.0f}% Exit Idea")
    print("=" * 80)

    baseline_results = []
    new_idea_results = []

    for cfg in SYMBOLS:
        symbol    = cfg["symbol"]
        timeframe = cfg["timeframe"]
        candle    = cfg["candle_type"]
        leverage  = cfg["leverage"]
        folder    = TF_TO_FOLDER[timeframe]

        print(f"\n  [{symbol} | {timeframe}]")

        print(f"    Running BASELINE...", end=" ", flush=True)
        base = run_single_backtest(symbol, timeframe, candle, leverage, folder,
                                   pnl_exit_pct=None)
        if base:
            baseline_results.append(base)
            print(f"Done  ({base['Number of Trades']} trades, "
                  f"Return: {base['Total Return %']:+.2f}%)")
        else:
            print("FAILED")

        print(f"    Running NEW IDEA (PnL >= {PNL_EXIT_THRESHOLD:.0f}%)...", end=" ", flush=True)
        new = run_single_backtest(symbol, timeframe, candle, leverage, folder,
                                  pnl_exit_pct=PNL_EXIT_THRESHOLD)
        if new:
            new_idea_results.append(new)
            pnl_exits = count_pnl_exits(new)
            print(f"Done  ({new['Number of Trades']} trades, "
                  f"Return: {new['Total Return %']:+.2f}%, "
                  f"PnL-exits: {pnl_exits})")
        else:
            print("FAILED")

    # ---------------------------------------------------------------------------
    # Print comparison table
    # ---------------------------------------------------------------------------
    print("\n\n" + "=" * 120)
    print(f"{'COMPARISON TABLE — BASELINE vs PnL ≥99% EXIT':^120}")
    print("=" * 120)

    # Header
    h = (f"{'Symbol':<12} | {'TF':<4} | "
         f"{'Return% (Base)':<16} | {'Return% (New)':<15} | {'Δ Return':<12} | "
         f"{'MaxDD (Base)':<13} | {'MaxDD (New)':<12} | {'Δ MaxDD':<10} | "
         f"{'Trades(B)':<10} | {'Trades(N)':<10} | "
         f"{'WinRate(B)':<11} | {'WinRate(N)':<11} | "
         f"{'PF(B)':<7} | {'PF(N)':<7} | "
         f"{'PnL-Exits':<9}")
    print(h)
    print("-" * 120)

    # Build lookup by symbol
    base_map = {m['Symbol']: m for m in baseline_results}
    new_map  = {m['Symbol']: m for m in new_idea_results}

    summary_rows = []
    for cfg in SYMBOLS:
        symbol = cfg["symbol"]
        tf     = cfg["timeframe"]
        b = base_map.get(symbol)
        n = new_map.get(symbol)
        if not b or not n:
            print(f"{symbol:<12} | {tf:<4} | MISSING DATA")
            continue

        pnl_exits = count_pnl_exits(n)

        b_ret  = b['Total Return %']
        n_ret  = n['Total Return %']
        b_dd   = b['Max Drawdown %']
        n_dd   = n['Max Drawdown %']
        b_tr   = b['Number of Trades']
        n_tr   = n['Number of Trades']
        b_wr   = b['Win Rate %']
        n_wr   = n['Win Rate %']
        b_pf   = b['Profit Factor']
        n_pf   = n['Profit Factor']

        d_ret = n_ret - b_ret
        d_dd  = n_dd  - b_dd
        d_pf  = n_pf  - b_pf

        ret_arrow = ("▲" if d_ret > 0 else ("▼" if d_ret < 0 else "="))
        dd_arrow  = ("▼" if d_dd  < 0 else ("▲" if d_dd  > 0 else "="))  # lower DD = better

        row = (f"{symbol:<12} | {tf:<4} | "
               f"{b_ret:>14.2f}% | {n_ret:>13.2f}% | "
               f"{ret_arrow} {d_ret:>+7.2f}%   | "
               f"{b_dd:>11.2f}% | {n_dd:>10.2f}% | "
               f"{dd_arrow} {d_dd:>+5.2f}%  | "
               f"{b_tr:>9} | {n_tr:>9} | "
               f"{b_wr:>9.2f}% | {n_wr:>9.2f}% | "
               f"{b_pf:>5.2f} | {n_pf:>5.2f} | "
               f"{pnl_exits:>9}")
        print(row)
        summary_rows.append({
            'Symbol': symbol, 'TF': tf,
            'Base Return%': b_ret, 'New Return%': n_ret, 'Δ Return%': d_ret,
            'Base MaxDD%': b_dd,   'New MaxDD%': n_dd,   'Δ MaxDD%': d_dd,
            'Base Trades': b_tr,   'New Trades': n_tr,
            'Base WinRate%': b_wr, 'New WinRate%': n_wr,
            'Base PF': b_pf,       'New PF': n_pf,       'Δ PF': d_pf,
            'PnL Exits': pnl_exits
        })

    print("=" * 120)

    # Portfolio-level aggregates
    if summary_rows:
        df_s = pd.DataFrame(summary_rows)
        print(f"\n  Portfolio Aggregate (sum / mean across {len(summary_rows)} symbols):")
        print(f"  {'Metric':<30} {'Baseline':>12} {'New Idea':>12} {'Delta':>12}")
        print(f"  {'-'*66}")

        metrics_agg = [
            ("Avg Total Return %",  'Base Return%', 'New Return%', True),
            ("Avg Max Drawdown %",  'Base MaxDD%',  'New MaxDD%',  False),
            ("Avg Win Rate %",      'Base WinRate%','New WinRate%',True),
            ("Avg Profit Factor",   'Base PF',      'New PF',      True),
            ("Total Trades",        'Base Trades',  'New Trades',  None),
            ("Total PnL Exits",     None,           'PnL Exits',   None),
        ]

        for label, b_col, n_col, higher_better in metrics_agg:
            if b_col is None:
                n_val = df_s[n_col].sum()
                print(f"  {label:<30} {'—':>12} {n_val:>12.0f} {'':>12}")
            elif b_col in ('Base Trades', 'New Trades'):
                b_val = df_s[b_col].sum()
                n_val = df_s[n_col].sum()
                diff  = n_val - b_val
                print(f"  {label:<30} {b_val:>12.0f} {n_val:>12.0f} {diff:>+12.0f}")
            else:
                b_val = df_s[b_col].mean()
                n_val = df_s[n_col].mean()
                diff  = n_val - b_val
                arrow = ""
                if diff > 0:
                    arrow = "▲" if higher_better else "▼"
                elif diff < 0:
                    arrow = "▼" if higher_better else "▲"
                print(f"  {label:<30} {b_val:>12.2f} {n_val:>12.2f} {arrow} {diff:>+9.2f}")

    print("\n")

    # ---------------------------------------------------------------------------
    # Save markdown report
    # ---------------------------------------------------------------------------
    report_path = Path(__file__).parent / "pnl_exit_comparison_results.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# Donchian Strategy: Baseline vs PnL ≥{PNL_EXIT_THRESHOLD:.0f}% Exit\n\n")
        f.write(f"**Condition:** Exit position when unrealized margin PnL ≥ {PNL_EXIT_THRESHOLD:.0f}%  \n")
        f.write(f"**Formula:** `(price_change / entry_price) × leverage × 100 ≥ {PNL_EXIT_THRESHOLD:.0f}`  \n")
        f.write(f"**Leverage:** 5x  \n")
        f.write(f"**Candle Type:** Heikin-Ashi  \n\n")

        f.write("## Results\n\n")
        f.write("| Symbol | TF | Return%(B) | Return%(N) | ΔReturn% | MaxDD%(B) | MaxDD%(N) | ΔMaxDD% | Trades(B) | Trades(N) | WinRate%(B) | WinRate%(N) | PF(B) | PF(N) | ΔPF | PnL-Exits |\n")
        f.write("|--------|-----|------------|------------|----------|-----------|-----------|---------|-----------|-----------|------------|------------|-------|-------|-----|----------|\n")
        for row in summary_rows:
            sign_ret = "+" if row['Δ Return%'] >= 0 else ""
            sign_dd  = "+" if row['Δ MaxDD%']  >= 0 else ""
            sign_pf  = "+" if row['Δ PF']      >= 0 else ""
            f.write(f"| {row['Symbol']} | {row['TF']} "
                    f"| {row['Base Return%']:.2f}% | {row['New Return%']:.2f}% | {sign_ret}{row['Δ Return%']:.2f}% "
                    f"| {row['Base MaxDD%']:.2f}% | {row['New MaxDD%']:.2f}% | {sign_dd}{row['Δ MaxDD%']:.2f}% "
                    f"| {row['Base Trades']} | {row['New Trades']} "
                    f"| {row['Base WinRate%']:.2f}% | {row['New WinRate%']:.2f}% "
                    f"| {row['Base PF']:.2f} | {row['New PF']:.2f} | {sign_pf}{row['Δ PF']:.2f} "
                    f"| {row['PnL Exits']} |\n")

        if summary_rows:
            df_s = pd.DataFrame(summary_rows)
            f.write("\n## Portfolio Aggregate\n\n")
            f.write("| Metric | Baseline | New Idea | Delta |\n")
            f.write("|--------|----------|----------|-------|\n")
            for label, b_col, n_col, hb in metrics_agg:
                if b_col is None:
                    n_val = df_s[n_col].sum()
                    f.write(f"| {label} | — | {n_val:.0f} | — |\n")
                elif b_col in ('Base Trades', 'New Trades'):
                    b_val = df_s[b_col].sum()
                    n_val = df_s[n_col].sum()
                    diff  = n_val - b_val
                    f.write(f"| {label} | {b_val:.0f} | {n_val:.0f} | {diff:+.0f} |\n")
                else:
                    b_val = df_s[b_col].mean()
                    n_val = df_s[n_col].mean()
                    diff  = n_val - b_val
                    f.write(f"| {label} | {b_val:.2f} | {n_val:.2f} | {diff:+.2f} |\n")

    print(f"  Markdown report saved to: {report_path.resolve()}")
    print()


if __name__ == "__main__":
    main()
