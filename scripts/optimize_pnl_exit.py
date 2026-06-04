#!/usr/bin/env python3
"""
Optimize pnl_exit_pct for the Donchian Channel strategy.

Sweeps a range of pnl_exit_pct values across selected top symbols
on the 1H Heikin Ashi timeframe and prints a comparison table.

Usage:
    python scripts/optimize_pnl_exit.py
"""

import os
import sys
import time
import pandas as pd
from pathlib import Path
from itertools import product

os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_FOLDER  = Path(r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H")
TIMEFRAME    = "1h"
CANDLE_TYPE  = "heikin_ashi"

# Top symbols from previous 1H backtest (diverse, all ≥ 80 trades)
SYMBOLS = [
    "PIPPINUSD",
    "ZECUSD",
    "RIVERUSD",
    "EVAAUSD",
    "VVVUSD",
    "XPLUSD",
    "PIUSD",
    "HUSD",
    "PENGUUSD",
    "BEATUSD",
]

# Pinpoint sweep: 99 zone
PNL_EXIT_VALUES = [97, 98, 99, 100, 101, 102, 103, 104, 105]

# ── Imports ───────────────────────────────────────────────────────────────────
from core.logger   import setup_logging, get_logger
from core.config   import get_config
from core.trading  import get_trade_config
from backtest.data_loader     import DataLoader
from backtest.engine          import BacktestEngine
from backtest.metrics         import calculate_metrics
from backtest.candle_transform import apply_heikin_ashi

setup_logging(log_level="WARNING")   # suppress noise
logger = get_logger(__name__)


def run_single(symbol: str, df_raw: pd.DataFrame, pnl_exit_pct, leverage: int) -> dict:
    """Run one backtest for a symbol with a specific pnl_exit_pct value."""
    from strategies.donchian_strategy import DonchianChannelStrategy

    strategy = DonchianChannelStrategy()
    strategy.timeframe = TIMEFRAME
    strategy._update_bars_per_day(TIMEFRAME)
    strategy.leverage = leverage
    strategy.pnl_exit_pct = pnl_exit_pct   # override directly
    strategy._suppress_persistence = True

    df = apply_heikin_ashi(df_raw.copy()) if CANDLE_TYPE == "heikin_ashi" else df_raw.copy()

    engine = BacktestEngine(strategy, symbol, TIMEFRAME, "donchian-channel", leverage=leverage)
    trades, equity_df = engine.run(df)

    metrics = calculate_metrics(
        strategy_name=f"donchian ({symbol})",
        initial_capital=engine.initial_capital,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df,
        data_df=df,
    )
    return {
        "symbol":         symbol,
        "pnl_exit_pct":   pnl_exit_pct if pnl_exit_pct is not None else "OFF",
        "total_return":   round(metrics.get("Total Return %", 0), 2),
        "max_drawdown":   round(metrics.get("Max Drawdown %", 0), 2),
        "profit_factor":  round(metrics.get("Profit Factor", 0), 3),
        "sharpe":         round(metrics.get("Sharpe Ratio", 0), 3),
        "sortino":        round(metrics.get("Sortino Ratio", 0), 3),
        "win_rate":       round(metrics.get("Win Rate %", 0), 2),
        "num_trades":     metrics.get("Number of Trades", 0),
    }


def main():
    config   = get_config()
    loader   = DataLoader(str(DATA_FOLDER))
    all_files = {f.stem.split("_")[0]: f for f in loader.get_available_files()}

    rows = []

    total = len(SYMBOLS) * len(PNL_EXIT_VALUES)
    done  = 0

    for symbol in SYMBOLS:
        key = symbol
        if key not in all_files:
            print(f"  [SKIP] {symbol} — file not found")
            continue

        df_raw = loader.load_data(all_files[key])
        if df_raw.empty:
            print(f"  [SKIP] {symbol} — empty data")
            continue

        trade_cfg = get_trade_config(symbol)
        leverage  = trade_cfg.get("leverage", 5)

        for pnl_val in PNL_EXIT_VALUES:
            result = run_single(symbol, df_raw, pnl_val, leverage)
            rows.append(result)
            done += 1
            label = str(pnl_val) if pnl_val is not None else "OFF"
            print(f"  [{done:>3}/{total}] {symbol:<15} pnl_exit={label:<5} "
                  f"-> Return={result['total_return']:>7.2f}%  "
                  f"PF={result['profit_factor']:>5.3f}  "
                  f"DD={result['max_drawdown']:>6.2f}%  "
                  f"Sharpe={result['sharpe']:>6.3f}")

    df = pd.DataFrame(rows)

    # ── Per-value aggregate (mean across all symbols) ─────────────────────────
    agg = (
        df.groupby("pnl_exit_pct")
          .agg(
              avg_return   =("total_return",  "mean"),
              avg_drawdown =("max_drawdown",  "mean"),
              avg_pf       =("profit_factor", "mean"),
              avg_sharpe   =("sharpe",        "mean"),
              avg_sortino  =("sortino",       "mean"),
              avg_winrate  =("win_rate",      "mean"),
              avg_trades   =("num_trades",    "mean"),
          )
          .reset_index()
    )

    # Sort by a composite score: PF * Sharpe / max_drawdown
    agg["score"] = (agg["avg_pf"] * agg["avg_sharpe"]) / agg["avg_drawdown"].replace(0, 1)
    agg = agg.sort_values("score", ascending=False)

    print("\n" + "=" * 110)
    print(f"{'PNL EXIT OPTIMIZATION — DONCHIAN 1H HEIKIN ASHI':^110}")
    print(f"{'Symbols: ' + ', '.join(SYMBOLS):^110}")
    print("=" * 110)
    header = (f"{'pnl_exit_pct':<14} | {'Avg Return':>10} | {'Avg MaxDD':>10} | "
              f"{'Avg PF':>8} | {'Avg Sharpe':>10} | {'Avg Sortino':>11} | "
              f"{'Avg WinRate':>11} | {'Avg Trades':>10} | {'Score':>8}")
    print(header)
    print("-" * 110)

    for _, r in agg.iterrows():
        print(
            f"{str(r['pnl_exit_pct']):<14} | "
            f"{r['avg_return']:>9.2f}% | "
            f"{r['avg_drawdown']:>9.2f}% | "
            f"{r['avg_pf']:>8.3f} | "
            f"{r['avg_sharpe']:>10.3f} | "
            f"{r['avg_sortino']:>11.3f} | "
            f"{r['avg_winrate']:>10.2f}% | "
            f"{r['avg_trades']:>10.1f} | "
            f"{r['score']:>8.4f}"
        )

    print("=" * 110)
    best = agg.iloc[0]
    print(f"\n*** OPTIMAL pnl_exit_pct = {best['pnl_exit_pct']}  "
          f"(Score: {best['score']:.4f} | "
          f"Avg Return: {best['avg_return']:.2f}% | "
          f"Avg PF: {best['avg_pf']:.3f} | "
          f"Avg Sharpe: {best['avg_sharpe']:.3f} | "
          f"Avg MaxDD: {best['avg_drawdown']:.2f}%)")

    # Also save CSV
    out_csv = ROOT / "reports" / "pnl_exit_optimization.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n📄 Full per-symbol results saved → {out_csv}")


if __name__ == "__main__":
    main()
