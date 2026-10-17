"""
Full-Universe Backtest Scanner — EMA Crossover Strategy
=========================================================
Tests crypto futures symbols across timeframes (1h, 2h, 4h, 6h) from
D:\\Workspace\\crypto-backtest-data\\Futures using the new EMA Crossover Strategy
(20/50 EMA cross + 200 EMA trend filter + ADX choppiness filter + breakout re-entry
 + Donchian-style ATR trailing stop + ATR partial take profit + profit milestone exit).

Ranks symbols by Composite Score, Profit Factor, Sharpe Ratio, and Return,
and generates an interactive HTML report with Plotly charts and detailed tables.

Usage:
    python run_ema_crossover_scanner.py
    python run_ema_crossover_scanner.py --timeframes 1h 4h --top-n 20
    python run_ema_crossover_scanner.py --symbol BTCUSD --timeframes 1h
"""

import argparse
import sys
import os
import time
import warnings
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any

warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent))

# Set UTC timezone for consistent backtesting
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

from core.config import get_config
from core.logger import setup_logging, get_logger
from core.trading import get_trade_config
from backtest.engine import BacktestEngine
from backtest.data_loader import DataLoader
from backtest.metrics import calculate_metrics
from backtest.candle_transform import apply_heikin_ashi
from strategies.ema_crossover_strategy import EMACrossoverStrategy

# ─────────────────────────────────────────────────────────────
STRATEGY_NAME = "ema_crossover"
DEFAULT_DATA_ROOT = r"D:\Workspace\crypto-backtest-data\Futures"
DEFAULT_WALLET = 1000.0
DEFAULT_LEVERAGE = 5
DEFAULT_TIMEFRAMES = ["1h", "4h"]
MIN_TRADES = 10
MIN_BARS = 300

TF_TO_SUBFOLDER = {
    "1h": "delta_crypto_data_1H",
    "2h": "delta_crypto_data_2H",
    "4h": "delta_crypto_data_4H",
    "6h": "delta_crypto_data_6H",
}

# Composite score weights
SCORE_WEIGHTS = {
    "sharpe": 0.30,         # Risk-adjusted return
    "profit_factor": 0.25,  # Profit vs loss ratio
    "win_rate": 0.15,       # Profitable trades %
    "return": 0.20,         # Net return on wallet
    "drawdown": -0.10,      # Drawdown penalty
}

def find_csv(data_root: str, symbol: str, timeframe: str) -> Optional[Path]:
    """Find CSV file for a given symbol and timeframe."""
    sub = TF_TO_SUBFOLDER.get(timeframe)
    if sub:
        p = Path(data_root) / sub / f"{symbol}_{timeframe}.csv"
        if p.exists():
            return p
    # Fallback to direct path or uppercase/lowercase variants
    for ext in [f"{symbol}_{timeframe}.csv", f"{symbol}_{timeframe.upper()}.csv"]:
        p = Path(data_root) / ext
        if p.exists():
            return p
    return None

def compute_score(r: dict) -> float:
    """Calculate composite quality score for ranking."""
    sh = min(max(r.get("Sharpe Ratio", 0), -3), 10)
    pf = min(max(r.get("Profit Factor", 0), 0), 10)
    wr = r.get("Win Rate %", 0) / 100
    ret = r.get("Total Return %", 0) / 100
    dd = r.get("Max Drawdown %", 0) / 100

    score = (
        SCORE_WEIGHTS["sharpe"] * sh +
        SCORE_WEIGHTS["profit_factor"] * pf +
        SCORE_WEIGHTS["win_rate"] * wr * 10 +
        SCORE_WEIGHTS["return"] * ret * 5 +
        SCORE_WEIGHTS["drawdown"] * dd * 10
    )
    return round(score, 4)

def backtest_one(
    symbol: str,
    timeframe: str,
    data_root: str,
    wallet: float,
    candle_type: str = "standard",
    logger = None,
) -> Optional[dict]:
    """Run EMA Crossover backtest for a single symbol and timeframe."""
    csv_path = find_csv(data_root, symbol, timeframe)
    if csv_path is None or not csv_path.exists():
        return None

    loader = DataLoader(str(csv_path.parent))
    try:
        df = loader.load_data(csv_path)
    except Exception as e:
        if logger:
            logger.debug(f"Failed loading {csv_path}: {e}")
        return None

    if df.empty or len(df) < MIN_BARS:
        return None

    # Apply candle transform if specified
    if candle_type == "heikin_ashi":
        df = apply_heikin_ashi(df)

    trade_cfg = get_trade_config(symbol)
    leverage = trade_cfg.get("leverage", DEFAULT_LEVERAGE)

    strategy = EMACrossoverStrategy(symbol=symbol)
    strategy.timeframe = timeframe
    strategy.leverage = leverage
    if hasattr(strategy, "_update_bars_per_day"):
        strategy._update_bars_per_day(timeframe)

    cfg = get_config()
    orig_capital = cfg.backtesting.initial_capital
    cfg.backtesting.initial_capital = wallet

    try:
        engine = BacktestEngine(strategy, symbol, timeframe, STRATEGY_NAME, leverage=leverage)
        engine.initial_capital = wallet
        engine.equity = wallet
        trades, equity_df = engine.run(df)
    except Exception as e:
        if logger:
            logger.debug(f"Engine run failed for {symbol} ({timeframe}): {e}")
        return None
    finally:
        cfg.backtesting.initial_capital = orig_capital

    if len(trades) < MIN_TRADES:
        return None

    metrics = calculate_metrics(
        strategy_name=f"{STRATEGY_NAME} ({symbol})",
        initial_capital=wallet,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df,
        data_df=df,
    )

    metrics["Symbol"] = symbol
    metrics["Timeframe"] = timeframe
    metrics["Candle Type"] = candle_type
    metrics["Leverage"] = leverage
    metrics["Bars"] = len(df)
    metrics["Score"] = compute_score(metrics)
    metrics["Net PnL $"] = engine.equity - wallet
    metrics["Wallet Impact %"] = (engine.equity - wallet) / wallet * 100
    metrics["Trades"] = len(trades)
    return metrics

def generate_html_report(
    all_results: List[dict],
    top_n: int,
    wallet: float,
    out_dir: Path,
    candle_type: str,
) -> Tuple[Path, List[dict]]:
    """Generate an interactive HTML report for EMA Crossover Strategy."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    # Select best timeframe per symbol
    best_by_symbol: Dict[str, dict] = {}
    for r in all_results:
        sym = r["Symbol"]
        if sym not in best_by_symbol or r["Score"] > best_by_symbol[sym]["Score"]:
            best_by_symbol[sym] = r

    ranked = sorted(best_by_symbol.values(), key=lambda x: x["Score"], reverse=True)
    top = ranked[:top_n]

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tested_count = len(best_by_symbol)
    pass_count = sum(1 for r in ranked if r.get("Net PnL $", 0) > 0)

    # Chart 1: Top Composite Score Bar
    fig_score = go.Figure(go.Bar(
        x=[r["Symbol"] for r in top],
        y=[r["Score"] for r in top],
        marker=dict(
            color=[r["Score"] for r in top],
            colorscale="Tealgrn",
            showscale=True,
            colorbar=dict(title="Score"),
        ),
        text=[f"{r['Score']:.2f}" for r in top],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Score: %{y:.3f}<extra></extra>",
    ))
    fig_score.update_layout(
        title=f"Top {top_n} Coins by Composite Score — EMA Crossover Strategy",
        height=400,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(tickangle=-35, gridcolor="#1e293b"),
        yaxis=dict(gridcolor="#1e293b"),
        margin=dict(l=50, r=30, t=55, b=90),
    )
    score_html = fig_score.to_html(full_html=False, include_plotlyjs="cdn")

    # Chart 2: Net PnL vs Max Drawdown
    fig_pnl_dd = go.Figure()
    fig_pnl_dd.add_trace(go.Bar(
        name="Net Return %",
        x=[r["Symbol"] for r in top],
        y=[r.get("Total Return %", 0) for r in top],
        marker_color="#22c55e",
        text=[f"{r.get('Total Return %', 0):+.1f}%" for r in top],
        textposition="auto",
    ))
    fig_pnl_dd.add_trace(go.Bar(
        name="Max Drawdown %",
        x=[r["Symbol"] for r in top],
        y=[r.get("Max Drawdown %", 0) for r in top],
        marker_color="#ef4444",
        text=[f"{r.get('Max Drawdown %', 0):.1f}%" for r in top],
        textposition="auto",
    ))
    fig_pnl_dd.update_layout(
        title="Net Return % vs Max Drawdown % (Top Coins)",
        barmode="group",
        height=400,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(tickangle=-35, gridcolor="#1e293b"),
        yaxis=dict(gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.1, x=0.3),
        margin=dict(l=50, r=30, t=65, b=90),
    )
    pnl_dd_html = fig_pnl_dd.to_html(full_html=False, include_plotlyjs=False)

    # Chart 3: Win Rate vs Profit Factor Bubble
    fig_bubble = go.Figure(go.Scatter(
        x=[r.get("Win Rate %", 0) for r in top],
        y=[min(r.get("Profit Factor", 0), 10) for r in top],
        mode="markers+text",
        text=[r["Symbol"] for r in top],
        textposition="top center",
        marker=dict(
            size=[max(abs(r.get("Total Return %", 1)), 5) ** 0.5 * 6 for r in top],
            color=[r.get("Sharpe Ratio", 0) for r in top],
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(title="Sharpe"),
            line=dict(width=1, color="#334155"),
        ),
        hovertemplate="<b>%{text}</b><br>Win Rate: %{x:.1f}%<br>Profit Factor: %{y:.2f}<extra></extra>",
    ))
    fig_bubble.add_hline(y=1.0, line_dash="dash", line_color="#64748b", annotation_text="Breakeven (PF=1.0)")
    fig_bubble.update_layout(
        title="Win Rate % vs Profit Factor (Bubble Size = Return %, Color = Sharpe)",
        height=420,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(title="Win Rate %", gridcolor="#1e293b"),
        yaxis=dict(title="Profit Factor", gridcolor="#1e293b"),
        margin=dict(l=50, r=30, t=55, b=50),
    )
    bubble_html = fig_bubble.to_html(full_html=False, include_plotlyjs=False)

    # HTML Cards for Top 6 Recommended Coins
    rec_cards = []
    for i, r in enumerate(top[:6], 1):
        ret_val = r.get("Total Return %", 0)
        pnl_val = r.get("Net PnL $", 0)
        pf_val = r.get("Profit Factor", 0)
        wr_val = r.get("Win Rate %", 0)
        sh_val = r.get("Sharpe Ratio", 0)
        dd_val = r.get("Max Drawdown %", 0)
        trades_val = r.get("Number of Trades", 0)

        card = f"""
        <div class="rec-card">
          <div class="rec-rank">#{i}</div>
          <div class="rec-sym">{r['Symbol']} <span class="badge-tag">{r['Timeframe'].upper()}</span></div>
          <div class="rec-metrics">
            <span class="metric pos">Return: {ret_val:+.1f}%</span>
            <span class="metric">PnL: ${pnl_val:+,.2f}</span>
            <span class="metric">PF: {pf_val:.2f}</span>
            <span class="metric">WR: {wr_val:.1f}%</span>
            <span class="metric">Sharpe: {sh_val:.2f}</span>
            <span class="metric warn">MaxDD: {dd_val:.1f}%</span>
            <span class="metric">Trades: {trades_val}</span>
          </div>
          <div class="rec-score">Composite Score: <b>{r['Score']:.3f}</b></div>
        </div>
        """
        rec_cards.append(card)
    rec_cards_html = "\n".join(rec_cards)

    # Full Table Rows
    table_rows = []
    for i, r in enumerate(ranked, 1):
        ret_val = r.get("Total Return %", 0)
        pnl_val = r.get("Net PnL $", 0)
        pf_val = r.get("Profit Factor", 0)
        wr_val = r.get("Win Rate %", 0)
        sh_val = r.get("Sharpe Ratio", 0)
        dd_val = r.get("Max Drawdown %", 0)
        trades_val = r.get("Number of Trades", 0)

        pnl_cls = "pos" if pnl_val > 0 else "neg"
        pf_str = "inf" if pf_val == float("inf") else f"{pf_val:.2f}"

        row = f"""
        <tr>
          <td class="rank">#{i}</td>
          <td class="symbol">{r['Symbol']}</td>
          <td><span class="tf-badge">{r['Timeframe']}</span></td>
          <td class="score">{r['Score']:.3f}</td>
          <td class="{pnl_cls}">{ret_val:+.2f}%</td>
          <td class="{pnl_cls}">${pnl_val:+,.2f}</td>
          <td>{trades_val}</td>
          <td>{wr_val:.1f}%</td>
          <td>{pf_str}</td>
          <td>{dd_val:.1f}%</td>
          <td>{sh_val:.2f}</td>
        </tr>
        """
        table_rows.append(row)
    table_rows_html = "\n".join(table_rows)

    top_sym = ranked[0]['Symbol'] if ranked else 'N/A'
    top_score_str = f"{ranked[0]['Score']:.3f}" if ranked else "0.000"
    top_tf = ranked[0]['Timeframe'] if ranked else ''
    best_ret = max((r.get('Total Return %', 0) for r in ranked), default=0)
    best_ret_sym = max(ranked, key=lambda x: x.get('Total Return %', 0))['Symbol'] if ranked else 'N/A'

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EMA Crossover Strategy — Coin Ranking & Backtest Analysis</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0b0f19;
    --surface: #111827;
    --border: #1f2937;
    --text: #f3f4f6;
    --muted: #9ca3af;
    --accent: #3b82f6;
    --accent2: #06b6d4;
    --pos: #10b981;
    --neg: #ef4444;
    --warn: #f59e0b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, sans-serif;
    padding-bottom: 60px;
    line-height: 1.5;
  }}
  .hero {{
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 60%, #030712 100%);
    padding: 40px 60px 30px;
    border-bottom: 1px solid var(--border);
  }}
  .hero-badge {{
    display: inline-block;
    background: rgba(59, 130, 246, 0.2);
    border: 1px solid rgba(59, 130, 246, 0.4);
    color: #93c5fd;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    margin-bottom: 12px;
  }}
  h1 {{
    font-size: 2.1rem;
    font-weight: 700;
    margin-bottom: 8px;
    background: linear-gradient(90deg, #60a5fa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }}
  .hero-meta {{
    font-size: 0.88rem;
    color: var(--muted);
    display: flex;
    flex-wrap: wrap;
    gap: 20px;
    margin-top: 8px;
  }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    padding: 24px 60px;
  }}
  .kpi-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
  }}
  .kpi-card::after {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--accent);
  }}
  .kpi-card.pos::after {{ background: var(--pos); }}
  .kpi-card.cyan::after {{ background: var(--accent2); }}
  .kpi-card.warn::after {{ background: var(--warn); }}
  .kpi-label {{
    font-size: 0.72rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
  }}
  .kpi-val {{
    font-size: 1.7rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
  }}
  .kpi-val.pos {{ color: var(--pos); }}
  .kpi-sub {{
    font-size: 0.75rem;
    color: var(--muted);
    margin-top: 4px;
  }}
  .section {{
    padding: 20px 60px;
  }}
  .section-title {{
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .rec-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 16px;
  }}
  .rec-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
    transition: transform 0.2s, border-color 0.2s;
  }}
  .rec-card:hover {{
    transform: translateY(-2px);
    border-color: var(--accent);
  }}
  .rec-rank {{
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--accent2);
    margin-bottom: 4px;
  }}
  .rec-sym {{
    font-size: 1.1rem;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    margin-bottom: 10px;
  }}
  .badge-tag {{
    background: rgba(59, 130, 246, 0.2);
    color: #60a5fa;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.72rem;
    font-weight: 600;
    margin-left: 6px;
  }}
  .rec-metrics {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }}
  .metric {{
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 3px 8px;
    font-family: 'JetBrains Mono', monospace;
  }}
  .metric.pos {{ color: var(--pos); border-color: rgba(16, 185, 129, 0.3); }}
  .metric.warn {{ color: var(--warn); }}
  .rec-score {{
    font-size: 0.8rem;
    color: var(--muted);
  }}
  .chart-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 10px;
    margin-bottom: 24px;
    overflow: hidden;
  }}
  .table-wrapper {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}
  th {{
    background: rgba(255, 255, 255, 0.02);
    padding: 12px 14px;
    text-align: left;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 10px 14px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    white-space: nowrap;
  }}
  tr:hover td {{
    background: rgba(255, 255, 255, 0.03);
  }}
  .symbol {{ font-weight: 600; font-family: 'JetBrains Mono', monospace; }}
  .score {{ font-weight: 700; color: var(--accent2); font-family: 'JetBrains Mono', monospace; }}
  .pos {{ color: var(--pos); font-weight: 600; }}
  .neg {{ color: var(--neg); font-weight: 600; }}
  .tf-badge {{
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 6px;
    font-size: 0.72rem;
    font-family: 'JetBrains Mono', monospace;
  }}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-badge">⚡ EMA Crossover Strategy</div>
  <h1>Coin Ranking & Universe Backtest Analysis</h1>
  <div class="hero-meta">
    <span><b>Generated:</b> {run_date}</span>
    <span><b>Tested Universe:</b> {tested_count} coins</span>
    <span><b>Profitable Coins:</b> {pass_count} / {tested_count} ({pass_count/max(tested_count, 1)*100:.1f}%)</span>
    <span><b>Candle Type:</b> {candle_type.upper()}</span>
    <span><b>Test Capital:</b> ${wallet:,.0f}</span>
  </div>
</div>

<div class="kpi-grid">
  <div class="kpi-card">
    <div class="kpi-label">Tested Coins</div>
    <div class="kpi-val">{tested_count}</div>
    <div class="kpi-sub">Futures Universe</div>
  </div>
  <div class="kpi-card pos">
    <div class="kpi-label">Profitable Coins</div>
    <div class="kpi-val pos">{pass_count}</div>
    <div class="kpi-sub">{pass_count/max(tested_count, 1)*100:.1f}% Win Rate</div>
  </div>
  <div class="kpi-card cyan">
    <div class="kpi-label">Top Ranked Coin</div>
    <div class="kpi-val">{top_sym}</div>
    <div class="kpi-sub">Score: {top_score_str} ({top_tf})</div>
  </div>
  <div class="kpi-card warn">
    <div class="kpi-label">Best Net Return</div>
    <div class="kpi-val pos">+{best_ret:.1f}%</div>
    <div class="kpi-sub">{best_ret_sym}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">⭐ Top Recommended Portfolio Candidates</div>
  <div class="rec-grid">
    {rec_cards_html}
  </div>
</div>

<div class="section">
  <div class="section-title">📊 Rankings & Distribution Charts</div>
  <div class="chart-box">{score_html}</div>
  <div class="chart-box">{pnl_dd_html}</div>
  <div class="chart-box">{bubble_html}</div>
</div>

<div class="section">
  <div class="section-title">📋 Full Universe Ranking Table</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th>Symbol</th>
          <th>Timeframe</th>
          <th>Score</th>
          <th>Return %</th>
          <th>Net PnL ($)</th>
          <th>Trades</th>
          <th>Win Rate</th>
          <th>Profit Factor</th>
          <th>Max DD %</th>
          <th>Sharpe</th>
        </tr>
      </thead>
      <tbody>
        {table_rows_html}
      </tbody>
    </table>
  </div>
</div>

</body>
</html>
"""

    out_file = out_dir / "ema_crossover_ranking_report.html"
    out_file.write_text(html_content, encoding="utf-8")
    return out_file, ranked

def main():
    parser = argparse.ArgumentParser(description="EMA Crossover Strategy Universe Backtest & Coin Ranking")
    parser.add_argument("--data-root", type=str, default=DEFAULT_DATA_ROOT, help="Futures data root directory")
    parser.add_argument("--timeframes", nargs="+", default=DEFAULT_TIMEFRAMES, help="Timeframes to test (e.g. 1h 4h)")
    parser.add_argument("--candle-type", type=str, choices=["standard", "heikin_ashi"], default="standard", help="Candle type")
    parser.add_argument("--capital", type=float, default=DEFAULT_WALLET, help="Starting wallet capital")
    parser.add_argument("--top-n", type=int, default=20, help="Number of top coins to display and feature")
    parser.add_argument("--symbol", type=str, default=None, help="Filter to a specific symbol")

    args = parser.parse_args()

    import logging
    setup_logging(log_level="WARNING")
    logging.getLogger("strategies.ema_crossover_strategy").setLevel(logging.WARNING)
    logging.getLogger("backtest").setLevel(logging.WARNING)
    logging.getLogger("core").setLevel(logging.WARNING)
    logging.getLogger("strategies").setLevel(logging.WARNING)
    logger = get_logger(__name__)

    data_root = Path(args.data_root)
    if not data_root.exists():
        logger.error(f"Data root {data_root} does not exist.")
        sys.exit(1)

    # Discover all symbols from the first available timeframe folder
    subfolder = TF_TO_SUBFOLDER.get(args.timeframes[0], "delta_crypto_data_1H")
    source_dir = data_root / subfolder
    if not source_dir.exists():
        source_dir = data_root

    csv_files = sorted(list(source_dir.glob("*.csv")))
    symbols = []
    for f in csv_files:
        stem = f.stem
        sym = stem.split("_")[0]
        if sym not in symbols:
            symbols.append(sym)

    if args.symbol:
        symbols = [s for s in symbols if args.symbol.upper() in s.upper()]

    if not symbols:
        logger.error("No matching symbols found.")
        sys.exit(1)

    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    total_combos = len(symbols) * len(args.timeframes)
    print(f"\n{'='*80}")
    print(f"  EMA Crossover Strategy — Universe Backtest Scanner")
    print(f"  Symbols: {len(symbols)} | Timeframes: {args.timeframes} | Candle Type: {args.candle_type}")
    print(f"  Wallet: ${args.capital:,.0f} | Total Combinations: {total_combos}")
    print(f"{'='*80}\n")

    all_results = []
    done = 0
    skipped = 0

    for sym in symbols:
        for tf in args.timeframes:
            res = backtest_one(
                symbol=sym,
                timeframe=tf,
                data_root=str(data_root),
                wallet=args.capital,
                candle_type=args.candle_type,
                logger=logger,
            )
            done += 1
            if res:
                all_results.append(res)
            else:
                skipped += 1

        if done % 20 == 0 or done == total_combos:
            pct = done / total_combos * 100
            valid_syms = len({r["Symbol"] for r in all_results})
            best_info = ""
            if all_results:
                top_now = max(all_results, key=lambda x: x["Score"])
                best_info = f" | Best so far: {top_now['Symbol']} ({top_now['Timeframe']}) Score={top_now['Score']:.2f}"
            print(f"  Progress: [{pct:5.1f}%] {done}/{total_combos} | Valid results: {len(all_results)} ({valid_syms} coins){best_info}")

    if not all_results:
        print("\nNo valid backtest results generated (all filtered out by min_trades or min_bars).")
        sys.exit(0)

    # Generate HTML Report
    out_file, ranked = generate_html_report(all_results, args.top_n, args.capital, out_dir, args.candle_type)

    # Print Clean Terminal Summary
    print(f"\n{'='*120}")
    print(f"  {'TOP COINS RANKING — EMA CROSSOVER STRATEGY':^116}")
    print(f"  {'Ranked by Composite Score (Sharpe 30%, PF 25%, Return 20%, WinRate 15%, MaxDD -10%)':^116}")
    print(f"{'='*120}")
    header = f"  {'#':<4} {'Symbol':<15} {'TF':<5} {'Score':>7} {'Return %':>10} {'Net PnL':>11} {'Trades':>7} {'WinRate':>8} {'PF':>7} {'MaxDD':>8} {'Sharpe':>7}"
    print(header)
    print(f"  {'-'*116}")

    for i, r in enumerate(ranked[:args.top_n], 1):
        pf_val = r.get("Profit Factor", 0)
        pf_str = "  inf" if pf_val == float("inf") else f"{pf_val:6.2f}"
        row = (
            f"  {i:<4} {r['Symbol']:<15} {r['Timeframe']:<5} {r['Score']:>7.3f} "
            f"{r.get('Total Return %', 0):>+9.2f}% ${r.get('Net PnL $', 0):>+9,.2f} "
            f"{r.get('Number of Trades', 0):>7} {r.get('Win Rate %', 0):>7.1f}% "
            f"{pf_str} {r.get('Max Drawdown %', 0):>7.1f}% {r.get('Sharpe Ratio', 0):>7.2f}"
        )
        print(row)

    print(f"{'='*120}\n")
    print(f"  Report saved to: {out_file.resolve()}\n")

if __name__ == "__main__":
    main()
