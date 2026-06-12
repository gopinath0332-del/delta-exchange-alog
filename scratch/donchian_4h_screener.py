#!/usr/bin/env python3
"""
Donchian Channel 4H Screener — Best Symbol Finder

Runs Donchian Channel (Heikin-Ashi) backtests for ALL 4H coins
using LIVE CONFIG from settings.yaml (pnl_exit_pct=102, milestones, etc.)
and produces a ranked leaderboard with the best symbol to trade.

Usage:
    python scratch/donchian_4h_screener.py
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

from core.logger import setup_logging, get_logger
from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.candle_transform import apply_heikin_ashi

setup_logging(log_level="WARNING")
logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_FOLDER = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_4H"
TIMEFRAME   = "4h"
LEVERAGE    = 5
MIN_TRADES  = 5        # 4H has fewer trades, lower threshold
MIN_DATA_ROWS = 200    # 4H has fewer bars, lower threshold
TOP_N       = 15
MAX_WORKERS = 6

# Composite score weights
SCORE_WEIGHTS = {
    'Profit Factor':   0.35,
    'Total Return %':  0.25,
    'Sharpe Ratio':    0.20,
    'Win Rate %':      0.10,
    'Max Drawdown %': -0.10,
}

OUT_DIR = Path("scratch/screener_results")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Filters — skip stablecoins, derivatives, tiny data files
# ---------------------------------------------------------------------------
SKIP_SYMBOLS = {
    "BUSD", "FRAX", "USDT", "USDC", "DAI",
    "TONUSD", "LABUSD", "CHIPUSD",
    "SKYAIUSD", "RAVEUSD", "ENJUSD",
    "AIOTUSD", "ARIAUSD", "BASEDUSD",
    "PIEVERSEUSD", "SIRENUSD", "XAUTUSD",
    "QQQXUSD", "SPYXUSD", "AAPLXUSD",
    "AMZNXUSD", "GOOGLXUSD", "NVDAXUSD",
    "TSLAXUSD", "METAXUSD", "CRCLXUSD",
    "COINXUSD", "ALLOUSD", "OPNUSD",
    "AIGENSYNUSD", "BILLUSD",
}


def get_strategy():
    from strategies.donchian_strategy import DonchianChannelStrategy
    # All params (pnl_exit_pct, enable_partial_tp, milestones, etc.) are loaded
    # directly from settings.yaml — identical to live bot config.
    s = DonchianChannelStrategy()
    s._suppress_persistence = True
    s.timeframe = TIMEFRAME
    if hasattr(s, '_update_bars_per_day'):
        s._update_bars_per_day(TIMEFRAME)
    s.leverage = LEVERAGE
    return s


def run_one(csv_path: Path) -> Optional[dict]:
    """Run a single backtest and return a metrics dict (or None on failure/skip)."""
    symbol = csv_path.stem.split('_')[0]
    if symbol in SKIP_SYMBOLS:
        return None

    try:
        loader = DataLoader(str(csv_path.parent))
        df = loader.load_data(csv_path)
        if df.empty or len(df) < MIN_DATA_ROWS:
            return None

        df = apply_heikin_ashi(df)

        strategy = get_strategy()
        engine = BacktestEngine(
            strategy, symbol, TIMEFRAME,
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
            'Symbol':         symbol,
            'Total Return %': round(metrics.get('Total Return %', 0), 2),
            'Max Drawdown %': round(metrics.get('Max Drawdown %', 0), 2),
            'Sharpe Ratio':   round(metrics.get('Sharpe Ratio', 0), 3),
            'Sortino Ratio':  round(metrics.get('Sortino Ratio', 0), 3),
            'Win Rate %':     round(metrics.get('Win Rate %', 0), 2),
            'Profit Factor':  round(metrics.get('Profit Factor', 0), 3),
            'Num Trades':     n_trades,
            'Final Capital':  round(metrics.get('Final Capital', 0), 2),
            'Avg Win ($)':    round(metrics.get('Average Win', 0), 4),
            'Avg Loss ($)':   round(metrics.get('Average Loss', 0), 4),
        }
    except Exception as e:
        logger.debug(f"Error on {symbol}: {e}")
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
            pct = (col_data - col_min) / (col_max - col_min)
        score += weight * pct
    return score


def main():
    print("\n" + "=" * 80)
    print("  DONCHIAN CHANNEL 4H SCREENER")
    print("  Strategy: Heikin-Ashi | Leverage: 5x | Compounding: ON | Config: Live (settings.yaml)")
    print("  Includes: PnL exit @ 102%, 50% milestone (30% out), ATR partial TP, trailing stop")
    print("  Ranking: Composite score (PF 35% | Return 25% | Sharpe 20% | WR 10% | DD -10%)")
    print("=" * 80)

    folder_path = Path(DATA_FOLDER)
    csv_files = sorted(folder_path.glob("*_4h.csv"))
    print(f"\n  Screening {len(csv_files)} 4H files...\n")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as exe:
        futures = {exe.submit(run_one, f): f for f in csv_files}
        for fut in tqdm(as_completed(futures), total=len(futures), desc="  Backtesting", ncols=80):
            r = fut.result()
            if r:
                results.append(r)

    if not results:
        print("  No valid results found.")
        return

    df = pd.DataFrame(results)
    df['Score'] = compute_score(df).round(4)
    df = df.sort_values('Score', ascending=False).reset_index(drop=True)
    df.index += 1
    df.insert(0, 'Rank', df.index)

    # Save CSV
    csv_out = OUT_DIR / "donchian_screener_4h.csv"
    df.to_csv(csv_out, index=False)

    # Print leaderboard
    print(f"\n{'='*120}")
    print(f"  4H TIMEFRAME — TOP {TOP_N} DONCHIAN CHANNEL COINS (ranked by composite score)")
    print(f"{'='*120}")
    header = (f"{'Rank':<5} {'Symbol':<14} {'Total Return':>13} {'Max DD':>10} "
              f"{'Sharpe':>10} {'Win Rate':>10} {'Prof Factor':>13} {'Trades':>8} {'Score':>8}")
    print(header)
    print("-" * 120)
    for _, row in df[['Rank','Symbol','Total Return %','Max Drawdown %','Sharpe Ratio',
                       'Win Rate %','Profit Factor','Num Trades','Score']].head(TOP_N).iterrows():
        print(f"  {int(row['Rank']):<4} {row['Symbol']:<14} "
              f"{row['Total Return %']:>12.2f}%  "
              f"{row['Max Drawdown %']:>9.2f}%  "
              f"{row['Sharpe Ratio']:>9.3f}  "
              f"{row['Win Rate %']:>9.2f}%  "
              f"{row['Profit Factor']:>12.3f}  "
              f"{int(row['Num Trades']):>8}  "
              f"{row['Score']:>7.4f}")
    print(f"{'='*120}")

    # Winner announcement
    winner = df.iloc[0]
    print(f"\n\n  🏆 BEST SYMBOL TO TRADE ON 4H: {winner['Symbol']}")
    print(f"     Total Return:    {winner['Total Return %']:+.2f}%")
    print(f"     Profit Factor:   {winner['Profit Factor']:.3f}")
    print(f"     Sharpe Ratio:    {winner['Sharpe Ratio']:.3f}")
    print(f"     Win Rate:        {winner['Win Rate %']:.2f}%")
    print(f"     Max Drawdown:    {winner['Max Drawdown %']:.2f}%")
    print(f"     Num Trades:      {int(winner['Num Trades'])}")
    print(f"     Composite Score: {winner['Score']:.4f}")

    # Top 3
    print(f"\n  Top 3 Recommendations:")
    for i in range(min(3, len(df))):
        row = df.iloc[i]
        print(f"    {i+1}. {row['Symbol']:<14} — Return: {row['Total Return %']:+.2f}%  "
              f"PF: {row['Profit Factor']:.2f}  Sharpe: {row['Sharpe Ratio']:.2f}  "
              f"DD: {row['Max Drawdown %']:.2f}%  Trades: {int(row['Num Trades'])}")

    print(f"\n  📁 Full results saved → {csv_out.resolve()}")
    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
