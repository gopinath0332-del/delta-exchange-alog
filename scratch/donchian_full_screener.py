#!/usr/bin/env python3
"""
Donchian Channel Full Screener — All Coins, All Timeframes

Runs Donchian Channel (Heikin-Ashi) backtests for ALL coins in every timeframe
and produces a ranked leaderboard per timeframe with coin recommendations.

Usage:
    python scratch/donchian_full_screener.py

Outputs:
    scratch/screener_results/  — per-TF CSVs + markdown summary
"""

import os, sys, time
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from core.logger import setup_logging, get_logger
from core.config import get_config
from core.trading import get_trade_config
from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.candle_transform import apply_heikin_ashi

setup_logging(log_level="WARNING")
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TIMEFRAMES = {
    "1h":  r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H",
    "2h":  r"D:\Workspace\crypto-backtest-data\delta_crypto_data_2H",
    "4h":  r"D:\Workspace\crypto-backtest-data\delta_crypto_data_4H",
    "6h":  r"D:\Workspace\crypto-backtest-data\delta_crypto_data_6h",
}

LEVERAGE        = 5
MIN_TRADES      = 8        # Skip coins with fewer trades (insufficient sample)
MIN_DATA_ROWS   = 500      # Skip coins with very short history
TOP_N           = 12       # Number of coins to recommend per timeframe
MAX_WORKERS     = 6        # Parallel workers (in-process, CPU-light)

# Composite score weights — tweak these to change ranking priority
SCORE_WEIGHTS = {
    'Profit Factor':   0.35,  # quality of wins vs losses
    'Total Return %':  0.25,  # absolute performance
    'Sharpe Ratio':    0.20,  # risk-adjusted return
    'Win Rate %':      0.10,  # consistency
    'Max Drawdown %': -0.10,  # penalise drawdown (negative weight)
}

OUT_DIR = Path("scratch/screener_results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Filters — skip stablecoins, derivatives, tiny data files
# ---------------------------------------------------------------------------
SKIP_SYMBOLS = {
    "BUSD", "FRAX", "USDT", "USDC", "DAI",      # stablecoins
    "TONUSD", "LABUSD", "CHIPUSD",               # very low data
    "SKYAIUSD", "RAVEUSD", "ENJUSD",             # tiny files
    "AIOTUSD", "ARIAUSD", "BASEDUSD",            # tiny files
    "PIEVERSEUSD", "SIRENUSD", "XAUTUSD",        # tiny files
    "QQQXUSD", "SPYXUSD", "AAPLXUSD",           # equity derivatives
    "AMZNXUSD", "GOOGLXUSD", "NVDAXUSD",        # equity derivatives
    "TSLAXUSD", "METAXUSD", "CRCLXUSD",         # equity derivatives
    "COINXUSD",
}


def get_strategy(timeframe: str):
    from strategies.donchian_strategy import DonchianChannelStrategy
    s = DonchianChannelStrategy()
    s._suppress_persistence = True
    s.timeframe = timeframe
    if hasattr(s, '_update_bars_per_day'):
        s._update_bars_per_day(timeframe)
    s.leverage = LEVERAGE
    s.pnl_exit_pct = None  # baseline — no PnL exit
    return s


def run_one(csv_path: Path, timeframe: str) -> Optional[dict]:
    """Run a single backtest and return a metrics dict (or None on failure/skip)."""
    symbol = csv_path.stem.split('_')[0]   # e.g. PIPPINUSD
    if symbol in SKIP_SYMBOLS:
        return None

    try:
        loader = DataLoader(str(csv_path.parent))
        df = loader.load_data(csv_path)
        if df.empty or len(df) < MIN_DATA_ROWS:
            return None

        df = apply_heikin_ashi(df)

        strategy = get_strategy(timeframe)
        engine = BacktestEngine(
            strategy, symbol, timeframe,
            strategy_name="donchian_channel",
            leverage=LEVERAGE
        )
        trades, equity_df = engine.run(df)

        metrics = calculate_metrics(
            strategy_name=f"donchian_channel ({symbol})",
            initial_capital=engine.initial_capital,
            final_capital=engine.equity,
            trades=trades,
            equity_df=equity_df,
            data_df=df
        )

        n_trades = metrics.get('Number of Trades', 0)
        if n_trades < MIN_TRADES:
            return None

        return {
            'Symbol':          symbol,
            'Timeframe':       timeframe,
            'Total Return %':  round(metrics.get('Total Return %', 0), 2),
            'Max Drawdown %':  round(metrics.get('Max Drawdown %', 0), 2),
            'Sharpe Ratio':    round(metrics.get('Sharpe Ratio', 0), 3),
            'Sortino Ratio':   round(metrics.get('Sortino Ratio', 0), 3),
            'Win Rate %':      round(metrics.get('Win Rate %', 0), 2),
            'Profit Factor':   round(metrics.get('Profit Factor', 0), 3),
            'Num Trades':      n_trades,
            'Avg Win ($)':     round(metrics.get('Average Win', 0), 4),
            'Avg Loss ($)':    round(metrics.get('Average Loss', 0), 4),
        }
    except Exception as e:
        logger.debug(f"Error on {symbol} {timeframe}: {e}")
        return None


def compute_score(df: pd.DataFrame) -> pd.Series:
    """Composite percentile score across the weight dict."""
    score = pd.Series(0.0, index=df.index)
    for col, weight in SCORE_WEIGHTS.items():
        if col not in df.columns:
            continue
        col_data = df[col].copy()
        col_min, col_max = col_data.min(), col_data.max()
        if col_max == col_min:
            pct = pd.Series(0.5, index=df.index)
        else:
            pct = (col_data - col_min) / (col_max - col_min)   # 0..1
        score += weight * pct   # negative weight flips direction
    return score


def screen_timeframe(tf: str, folder: str) -> pd.DataFrame:
    folder_path = Path(folder)
    csv_files   = sorted(folder_path.glob("*.csv"))

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(run_one, f, tf): f for f in csv_files}
        for fut in tqdm(as_completed(futures), total=len(futures),
                        desc=f"  {tf}", ncols=80, leave=False):
            r = fut.result()
            if r:
                results.append(r)

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)
    df['Score'] = compute_score(df).round(4)
    df = df.sort_values('Score', ascending=False).reset_index(drop=True)
    df.index += 1  # 1-based rank
    df.insert(0, 'Rank', df.index)
    return df


def print_leaderboard(df: pd.DataFrame, tf: str, top_n: int = TOP_N):
    print(f"\n{'='*110}")
    print(f"  {tf.upper()} TIMEFRAME — TOP {top_n} DONCHIAN CHANNEL COINS  "
          f"(ranked by composite score)")
    print(f"{'='*110}")
    cols = ['Rank','Symbol','Total Return %','Max Drawdown %',
            'Sharpe Ratio','Win Rate %','Profit Factor','Num Trades','Score']
    sub = df[cols].head(top_n)
    col_widths = {
        'Rank': 5, 'Symbol': 14, 'Total Return %': 14, 'Max Drawdown %': 14,
        'Sharpe Ratio': 13, 'Win Rate %': 11, 'Profit Factor': 14,
        'Num Trades': 11, 'Score': 8
    }
    header = "".join(f"{c:<{w}}" for c, w in col_widths.items())
    print(header)
    print("-" * 110)
    for _, row in sub.iterrows():
        line = (f"{int(row['Rank']):<5}"
                f"{row['Symbol']:<14}"
                f"{row['Total Return %']:>12.2f}%  "
                f"{row['Max Drawdown %']:>12.2f}%  "
                f"{row['Sharpe Ratio']:>11.3f}  "
                f"{row['Win Rate %']:>9.2f}%  "
                f"{row['Profit Factor']:>12.3f}  "
                f"{int(row['Num Trades']):>10}  "
                f"{row['Score']:>7.4f}")
        print(line)
    print(f"{'='*110}")


def main():
    print("\n" + "=" * 80)
    print("  DONCHIAN CHANNEL FULL SCREENER")
    print("  Strategy: Heikin-Ashi | Leverage: 5x | Compounding: ON")
    print("  Ranking: Composite score (PF 35% | Return 25% | Sharpe 20% | WR 10% | DD -10%)")
    print("=" * 80)

    all_tf_dfs = {}

    for tf, folder in TIMEFRAMES.items():
        print(f"\n[{tf}] Screening {tf} coins in {folder} ...")
        df = screen_timeframe(tf, folder)
        if df.empty:
            print(f"  No results for {tf}")
            continue
        all_tf_dfs[tf] = df
        print(f"  Completed: {len(df)} valid coins")
        print_leaderboard(df, tf)

        # Save per-TF CSV
        csv_out = OUT_DIR / f"donchian_screener_{tf}.csv"
        df.to_csv(csv_out, index=False)
        print(f"  Saved → {csv_out}")

    # ---------------------------------------------------------------------------
    # Markdown recommendation report
    # ---------------------------------------------------------------------------
    md_path = OUT_DIR / "donchian_coin_recommendations.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Donchian Channel — Coin Recommendations by Timeframe\n\n")
        f.write("**Strategy:** Heikin-Ashi candles | 5x leverage | Compounding enabled  \n")
        f.write("**Composite Score:** PF (35%) + Return% (25%) + Sharpe (20%) + WinRate (10%) − MaxDD (10%)  \n")
        f.write("**Data:** Jan 2025 → May 2026  \n\n")
        f.write("> [!NOTE]\n")
        f.write("> Minimum 8 trades required for inclusion. Equity derivatives and stablecoins excluded.\n\n")

        for tf, df in all_tf_dfs.items():
            top = df.head(TOP_N)
            f.write(f"## {tf.upper()} Timeframe — Top {TOP_N} Picks\n\n")
            f.write("| Rank | Symbol | Return % | MaxDD % | Sharpe | Win Rate % | Profit Factor | Trades | Score |\n")
            f.write("|------|--------|----------|---------|--------|------------|---------------|--------|-------|\n")
            for _, row in top.iterrows():
                f.write(f"| {int(row['Rank'])} | **{row['Symbol']}** "
                        f"| {row['Total Return %']:+.2f}% "
                        f"| {row['Max Drawdown %']:.2f}% "
                        f"| {row['Sharpe Ratio']:.3f} "
                        f"| {row['Win Rate %']:.2f}% "
                        f"| {row['Profit Factor']:.3f} "
                        f"| {int(row['Num Trades'])} "
                        f"| {row['Score']:.4f} |\n")
            f.write("\n")

            # Recommended set (top 3 highlighted)
            top3 = top.head(3)['Symbol'].tolist()
            f.write(f"**🏆 Recommended for {tf}:** {', '.join(top3)}\n\n")
            f.write("---\n\n")

        # Combined cross-TF top performers (appear in multiple TF top lists)
        f.write("## Cross-Timeframe Champions\n\n")
        f.write("Coins that rank in the Top 12 across multiple timeframes:\n\n")
        all_top_symbols: dict = {}
        for tf, df in all_tf_dfs.items():
            for sym in df.head(TOP_N)['Symbol'].tolist():
                base = sym.replace("USD", "")
                all_top_symbols[base] = all_top_symbols.get(base, []) + [tf]
        champs = {k: v for k, v in all_top_symbols.items() if len(v) > 1}
        champs_sorted = sorted(champs.items(), key=lambda x: len(x[1]), reverse=True)
        if champs_sorted:
            f.write("| Symbol | Timeframes | Count |\n")
            f.write("|--------|------------|-------|\n")
            for sym, tfs in champs_sorted:
                f.write(f"| **{sym}** | {', '.join(tfs)} | {len(tfs)} |\n")
        else:
            f.write("_No cross-timeframe champions found._\n")
        f.write("\n")

    print(f"\n\n  ✅ Recommendation report saved → {md_path.resolve()}")

    # ---------------------------------------------------------------------------
    # Final console summary
    # ---------------------------------------------------------------------------
    print("\n\n" + "=" * 80)
    print("  FINAL RECOMMENDATIONS — SUGGESTED COINS PER TIMEFRAME")
    print("=" * 80)
    for tf, df in all_tf_dfs.items():
        top = df.head(TOP_N)
        symbols = top['Symbol'].tolist()
        print(f"\n  {tf.upper()}  ({len(symbols)} picks):")
        for i, (_, row) in enumerate(top.iterrows(), 1):
            print(f"    {i:2}. {row['Symbol']:<14}  Return: {row['Total Return %']:>7.2f}%  "
                  f"PF: {row['Profit Factor']:.2f}  Sharpe: {row['Sharpe Ratio']:.2f}  "
                  f"DD: {row['Max Drawdown %']:.2f}%  Trades: {int(row['Num Trades'])}")
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
