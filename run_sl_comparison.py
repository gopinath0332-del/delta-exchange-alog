#!/usr/bin/env python3
"""
SL Mode Comparison Backtest
============================
Runs the Donchian Channel portfolio backtest twice — once with intra-bar
trailing stop logic and once with candle-close trailing stop logic — then
generates a side-by-side comparison HTML dashboard.

Usage:
    python run_sl_comparison.py --data-folder D:/Workspace/crypto-backtest-data
    python run_sl_comparison.py  # uses default data folder
"""

import argparse
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import numpy as np

# Force UTC timezone for consistent backtest reporting
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

from core.logger import setup_logging, get_logger
from core.config import get_config
from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.candle_transform import apply_heikin_ashi

# ─── Portfolio definition (mirrors multi_coin.donchian_channel in settings.yaml)
PORTFOLIO = [
    {"symbol": "PIPPINUSD",  "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "BANKUSD",    "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "SKYAIUSD",   "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "HUSD",        "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "EVAAUSD",    "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "ZECUSD",      "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "PIUSD",      "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "VELVETUSD",   "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "DEEPUSD",    "timeframe": "4h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "EIGENUSD",   "timeframe": "6h", "candle_type": "heikin-ashi", "leverage": 5},
]

STRATEGY_NAME = "donchian_channel"
INITIAL_PORTFOLIO_CAPITAL = 1000.0

TF_TO_SUBFOLDER = {
    "1h": "delta_crypto_data_1H",
    "2h": "delta_crypto_data_2H",
    "4h": "delta_crypto_data_4H",
    "6h": "delta_crypto_data_6H",
}


def find_csv(data_root: str, symbol: str, timeframe: str) -> Path | None:
    """Locate a symbol's CSV file across timeframe subfolders."""
    subfolder = TF_TO_SUBFOLDER.get(timeframe)
    if subfolder:
        p = Path(data_root) / subfolder / f"{symbol}_{timeframe}.csv"
        if p.exists():
            return p
    p = Path(data_root) / f"{symbol}_{timeframe}.csv"
    return p if p.exists() else None


def run_single_coin(
    coin_cfg: dict,
    data_root: str,
    per_coin_capital: float,
    trailing_stop_mode: str,
) -> dict | None:
    """Run backtest for one coin with a specific trailing stop mode."""
    logger = get_logger(__name__)
    symbol = coin_cfg["symbol"]
    timeframe = coin_cfg["timeframe"]
    candle_type_str = coin_cfg.get("candle_type", "standard")
    leverage = coin_cfg.get("leverage", 5)

    internal_candle = "heikin_ashi" if "heikin" in candle_type_str.lower() else "standard"

    filepath = find_csv(data_root, symbol, timeframe)
    if filepath is None:
        logger.error(f"[{symbol}] CSV not found for {symbol}_{timeframe} in {data_root}")
        return None

    loader = DataLoader(str(filepath.parent))
    df = loader.load_data(filepath)
    if df.empty:
        logger.warning(f"[{symbol}] No data loaded from {filepath}")
        return None

    # Filter to past 1 year
    now_ts = int(time.time())
    one_year_ago_ts = now_ts - (365 * 24 * 3600)
    df = df[df["time"] >= one_year_ago_ts].reset_index(drop=True)
    if df.empty:
        logger.warning(f"[{symbol}] No data within the past 1 year")
        return None

    # Apply Heikin Ashi transform
    if internal_candle == "heikin_ashi":
        df = apply_heikin_ashi(df)

    # Load strategy with the specified trailing stop mode
    from strategies.donchian_strategy import DonchianChannelStrategy
    strategy = DonchianChannelStrategy(trailing_stop_mode=trailing_stop_mode)
    strategy.timeframe = timeframe
    if hasattr(strategy, "_update_bars_per_day"):
        strategy._update_bars_per_day(timeframe)
    strategy.leverage = leverage

    # Live-accurate sizing: every coin references the FULL shared wallet
    cfg = get_config()
    original_capital = cfg.backtesting.initial_capital
    cfg.backtesting.initial_capital = per_coin_capital

    engine = BacktestEngine(strategy, symbol, timeframe, STRATEGY_NAME, leverage=leverage)
    engine.initial_capital = per_coin_capital
    engine.equity = per_coin_capital

    trades, equity_df = engine.run(df)

    # Restore config capital
    cfg.backtesting.initial_capital = original_capital

    metrics = calculate_metrics(
        strategy_name=f"{STRATEGY_NAME} ({symbol})",
        initial_capital=per_coin_capital,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df,
        data_df=df,
    )
    metrics["Symbol"] = symbol
    metrics["Timeframe"] = timeframe
    metrics["Candle Type"] = "Heikin Ashi" if internal_candle == "heikin_ashi" else "Standard"
    metrics["Leverage"] = leverage
    metrics["SL Mode"] = trailing_stop_mode

    return metrics


def generate_comparison_dashboard(
    intra_metrics: list[dict],
    close_metrics: list[dict],
    reports_dir: Path,
    wallet: float = 1000.0,
) -> Path:
    """Generate a side-by-side comparison HTML dashboard."""
    import plotly.graph_objects as go

    # Build lookup: symbol -> metrics for each mode
    intra_by_sym = {m["Symbol"]: m for m in intra_metrics}
    close_by_sym = {m["Symbol"]: m for m in close_metrics}
    all_symbols = list(dict.fromkeys(m["Symbol"] for m in intra_metrics))

    # Portfolio totals
    intra_pnl = sum(m["Final Capital"] - m["Initial Capital"] for m in intra_metrics)
    close_pnl = sum(m["Final Capital"] - m["Initial Capital"] for m in close_metrics)
    intra_return = (intra_pnl / wallet * 100) if wallet > 0 else 0
    close_return = (close_pnl / wallet * 100) if wallet > 0 else 0

    # ── Chart 1: Grouped bar — per-coin return comparison
    intra_returns = [intra_by_sym.get(s, {}).get("Total Return %", 0) for s in all_symbols]
    close_returns = [close_by_sym.get(s, {}).get("Total Return %", 0) for s in all_symbols]

    fig_returns = go.Figure()
    fig_returns.add_trace(go.Bar(
        name="Intra-Bar SL",
        x=all_symbols, y=intra_returns,
        marker_color="#6366f1",
        text=[f"{r:+.1f}%" for r in intra_returns],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Intra-Bar: %{y:+.2f}%<extra></extra>",
    ))
    fig_returns.add_trace(go.Bar(
        name="Candle-Close SL",
        x=all_symbols, y=close_returns,
        marker_color="#f59e0b",
        text=[f"{r:+.1f}%" for r in close_returns],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Candle-Close: %{y:+.2f}%<extra></extra>",
    ))
    fig_returns.update_layout(
        barmode="group",
        title="Per-Coin Return % — Intra-Bar vs Candle-Close SL",
        height=440,
        plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Return %", zeroline=True, zerolinecolor="#475569", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    returns_html = fig_returns.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 2: Delta bar chart (intra - close)
    deltas = [i - c for i, c in zip(intra_returns, close_returns)]
    delta_colors = ["#22c55e" if d >= 0 else "#ef4444" for d in deltas]

    fig_delta = go.Figure(go.Bar(
        x=all_symbols, y=deltas,
        marker_color=delta_colors,
        text=[f"{d:+.1f}%" for d in deltas],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Δ Return: %{y:+.2f}%<extra></extra>",
    ))
    fig_delta.update_layout(
        title="Return Difference (Intra-Bar − Candle-Close)",
        height=380,
        plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Δ Return %", zeroline=True, zerolinecolor="#475569", gridcolor="#1e293b"),
    )
    delta_html = fig_delta.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 3: Profit Factor comparison
    intra_pfs = [min(intra_by_sym.get(s, {}).get("Profit Factor", 0), 10) for s in all_symbols]
    close_pfs = [min(close_by_sym.get(s, {}).get("Profit Factor", 0), 10) for s in all_symbols]

    fig_pf = go.Figure()
    fig_pf.add_trace(go.Bar(
        name="Intra-Bar SL", x=all_symbols, y=intra_pfs,
        marker_color="#6366f1",
        hovertemplate="<b>%{x}</b><br>PF: %{y:.2f}<extra></extra>",
    ))
    fig_pf.add_trace(go.Bar(
        name="Candle-Close SL", x=all_symbols, y=close_pfs,
        marker_color="#f59e0b",
        hovertemplate="<b>%{x}</b><br>PF: %{y:.2f}<extra></extra>",
    ))
    fig_pf.add_hline(y=1.0, line_dash="dash", line_color="#64748b",
                      annotation_text="PF = 1.0 (break-even)")
    fig_pf.update_layout(
        barmode="group",
        title="Profit Factor — Intra-Bar vs Candle-Close SL",
        height=380,
        plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Profit Factor", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    pf_html = fig_pf.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 4: Win Rate comparison
    intra_wrs = [intra_by_sym.get(s, {}).get("Win Rate %", 0) for s in all_symbols]
    close_wrs = [close_by_sym.get(s, {}).get("Win Rate %", 0) for s in all_symbols]

    fig_wr = go.Figure()
    fig_wr.add_trace(go.Bar(
        name="Intra-Bar SL", x=all_symbols, y=intra_wrs,
        marker_color="#6366f1",
        hovertemplate="<b>%{x}</b><br>WR: %{y:.1f}%<extra></extra>",
    ))
    fig_wr.add_trace(go.Bar(
        name="Candle-Close SL", x=all_symbols, y=close_wrs,
        marker_color="#f59e0b",
        hovertemplate="<b>%{x}</b><br>WR: %{y:.1f}%<extra></extra>",
    ))
    fig_wr.update_layout(
        barmode="group",
        title="Win Rate % — Intra-Bar vs Candle-Close SL",
        height=380,
        plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Win Rate %", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    wr_html = fig_wr.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Summary table rows
    table_rows = ""
    for sym in all_symbols:
        im = intra_by_sym.get(sym, {})
        cm = close_by_sym.get(sym, {})
        tf = im.get("Timeframe", cm.get("Timeframe", ""))

        i_ret = im.get("Total Return %", 0)
        c_ret = cm.get("Total Return %", 0)
        d_ret = i_ret - c_ret

        i_pnl = im.get("Final Capital", 0) - im.get("Initial Capital", 0)
        c_pnl = cm.get("Final Capital", 0) - cm.get("Initial Capital", 0)

        i_pf = im.get("Profit Factor", 0)
        c_pf = cm.get("Profit Factor", 0)

        i_wr = im.get("Win Rate %", 0)
        c_wr = cm.get("Win Rate %", 0)

        i_dd = im.get("Max Drawdown %", 0)
        c_dd = cm.get("Max Drawdown %", 0)

        i_n = im.get("Number of Trades", 0)
        c_n = cm.get("Number of Trades", 0)

        i_pf_disp = "inf" if i_pf == float("inf") else f"{i_pf:.2f}"
        c_pf_disp = "inf" if c_pf == float("inf") else f"{c_pf:.2f}"

        d_class = "pos" if d_ret >= 0 else "neg"
        i_ret_class = "pos" if i_ret >= 0 else "neg"
        c_ret_class = "pos" if c_ret >= 0 else "neg"

        table_rows += f"""
        <tr>
            <td class="symbol">{sym}</td>
            <td>{tf}</td>
            <td class="{i_ret_class}">{i_ret:+.2f}%</td>
            <td>${i_pnl:+,.2f}</td>
            <td>{i_n}</td>
            <td>{i_wr:.1f}%</td>
            <td>{i_pf_disp}</td>
            <td>{i_dd:.1f}%</td>
            <td class="col-sep {c_ret_class}">{c_ret:+.2f}%</td>
            <td>${c_pnl:+,.2f}</td>
            <td>{c_n}</td>
            <td>{c_wr:.1f}%</td>
            <td>{c_pf_disp}</td>
            <td>{c_dd:.1f}%</td>
            <td class="col-sep {d_class}">{d_ret:+.2f}%</td>
        </tr>"""

    # Portfolio totals
    i_total_trades = sum(m.get("Number of Trades", 0) for m in intra_metrics)
    c_total_trades = sum(m.get("Number of Trades", 0) for m in close_metrics)
    i_avg_wr = sum(m.get("Win Rate %", 0) for m in intra_metrics) / len(intra_metrics) if intra_metrics else 0
    c_avg_wr = sum(m.get("Win Rate %", 0) for m in close_metrics) / len(close_metrics) if close_metrics else 0
    i_max_dd = max((m.get("Max Drawdown %", 0) for m in intra_metrics), default=0)
    c_max_dd = max((m.get("Max Drawdown %", 0) for m in close_metrics), default=0)

    delta_portfolio = intra_return - close_return
    port_delta_class = "pos" if delta_portfolio >= 0 else "neg"
    i_port_class = "pos" if intra_return >= 0 else "neg"
    c_port_class = "pos" if close_return >= 0 else "neg"

    # Winner determination
    intra_wins = sum(1 for s in all_symbols
                     if intra_by_sym.get(s, {}).get("Total Return %", 0) > close_by_sym.get(s, {}).get("Total Return %", 0))
    close_wins = len(all_symbols) - intra_wins

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SL Mode Comparison — Intra-Bar vs Candle-Close</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:       #0a0f1e;
    --surface:  #111827;
    --border:   #1e293b;
    --accent:   #6366f1;
    --accent2:  #f59e0b;
    --text:     #e2e8f0;
    --muted:    #94a3b8;
    --pos:      #22c55e;
    --neg:      #ef4444;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }}
  .hero {{
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 40px 60px 32px;
    position: relative;
    overflow: hidden;
  }}
  .hero::before {{
    content: '';
    position: absolute;
    top: -80px; right: -80px;
    width: 320px; height: 320px;
    border-radius: 50%;
    background: radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%);
  }}
  .hero-badge {{
    display: inline-block;
    background: rgba(99,102,241,0.15);
    border: 1px solid rgba(99,102,241,0.4);
    border-radius: 20px;
    padding: 4px 14px;
    font-size: 0.75rem;
    color: #a5b4fc;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 16px;
  }}
  .hero h1 {{
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #e2e8f0, #a5b4fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
  }}
  .hero-meta {{
    color: var(--muted);
    font-size: 0.875rem;
    display: flex;
    gap: 24px;
    flex-wrap: wrap;
    margin-top: 16px;
  }}
  .hero-meta span {{ display: flex; align-items: center; gap: 6px; }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    padding: 32px 60px;
  }}
  .kpi-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
  }}
  .kpi-card:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
  .kpi-card::after {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    border-radius: 12px 12px 0 0;
  }}
  .kpi-card.intra::after  {{ background: var(--accent); }}
  .kpi-card.close::after  {{ background: var(--accent2); }}
  .kpi-card.delta-pos::after {{ background: var(--pos); }}
  .kpi-card.delta-neg::after {{ background: var(--neg); }}
  .kpi-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }}
  .kpi-value {{ font-size: 1.6rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
  .kpi-value.pos {{ color: var(--pos); }}
  .kpi-value.neg {{ color: var(--neg); }}
  .kpi-value.neutral {{ color: var(--text); }}
  .kpi-value.intra {{ color: var(--accent); }}
  .kpi-value.close {{ color: var(--accent2); }}
  .kpi-sub {{ font-size: 0.78rem; color: var(--muted); margin-top: 4px; }}
  .section {{
    padding: 0 60px 40px;
  }}
  .section-title {{
    font-size: 1.1rem;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .section-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }}
  .chart-grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }}
  .chart-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 4px;
    overflow: hidden;
  }}
  .chart-box.full {{ grid-column: 1 / -1; }}
  .table-wrapper {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }}
  thead tr {{
    border-bottom: 2px solid var(--border);
  }}
  thead th {{
    padding: 12px 10px;
    text-align: left;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    white-space: nowrap;
  }}
  thead th.intra-header {{ color: var(--accent); }}
  thead th.close-header {{ color: var(--accent2); }}
  thead th.delta-header {{ color: var(--text); font-weight: 700; }}
  tbody tr {{
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
  }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(99,102,241,0.05); }}
  tbody td {{ padding: 11px 10px; white-space: nowrap; }}
  .symbol {{ font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; }}
  .pos {{ color: var(--pos); font-weight: 500; }}
  .neg {{ color: var(--neg); font-weight: 500; }}
  .tfoot-row td {{
    padding: 14px 10px;
    font-weight: 700;
    background: rgba(99,102,241,0.08);
    border-top: 2px solid var(--accent);
    color: var(--text);
  }}
  footer {{
    text-align: center;
    padding: 24px;
    color: var(--muted);
    font-size: 0.75rem;
    border-top: 1px solid var(--border);
  }}
  .col-sep {{ border-left: 2px solid var(--border); }}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-badge">⚡ SL Mode Comparison Backtest</div>
  <h1>Intra-Bar vs Candle-Close Trailing Stop</h1>
  <div class="hero-meta">
    <span>Generated: {run_date}</span>
    <span>Shared wallet: ${wallet:,.0f}</span>
    <span>Strategy: donchian_channel (Heikin Ashi) | Coins: {len(all_symbols)}</span>
    <span>Risk/trade: 1.5% = ${wallet*0.015:,.0f} | Margin cap: 7% = ${wallet*0.07:,.0f}</span>
  </div>
</div>

<div class="kpi-grid">
  <div class="kpi-card intra">
    <div class="kpi-label">Intra-Bar SL Return</div>
    <div class="kpi-value {'pos' if intra_return >= 0 else 'neg'}">{intra_return:+.2f}%</div>
    <div class="kpi-sub">${intra_pnl:+,.2f} net P&L</div>
  </div>
  <div class="kpi-card close">
    <div class="kpi-label">Candle-Close SL Return</div>
    <div class="kpi-value {'pos' if close_return >= 0 else 'neg'}">{close_return:+.2f}%</div>
    <div class="kpi-sub">${close_pnl:+,.2f} net P&L</div>
  </div>
  <div class="kpi-card {'delta-pos' if delta_portfolio >= 0 else 'delta-neg'}">
    <div class="kpi-label">Δ Portfolio Return</div>
    <div class="kpi-value {'pos' if delta_portfolio >= 0 else 'neg'}">{delta_portfolio:+.2f}%</div>
    <div class="kpi-sub">Intra-bar {'outperforms' if delta_portfolio >= 0 else 'underperforms'}</div>
  </div>
  <div class="kpi-card intra">
    <div class="kpi-label">Per-Coin Wins</div>
    <div class="kpi-value neutral">{intra_wins} vs {close_wins}</div>
    <div class="kpi-sub">Intra-Bar vs Candle-Close</div>
  </div>
  <div class="kpi-card intra">
    <div class="kpi-label">Intra-Bar Trades</div>
    <div class="kpi-value neutral">{i_total_trades}</div>
    <div class="kpi-sub">Avg WR: {i_avg_wr:.1f}%</div>
  </div>
  <div class="kpi-card close">
    <div class="kpi-label">Candle-Close Trades</div>
    <div class="kpi-value neutral">{c_total_trades}</div>
    <div class="kpi-sub">Avg WR: {c_avg_wr:.1f}%</div>
  </div>
</div>

<div class="section">
  <div class="section-title">📊 Performance Comparison</div>
  <div class="chart-grid-2">
    <div class="chart-box full">{returns_html}</div>
    <div class="chart-box full">{delta_html}</div>
    <div class="chart-box">{pf_html}</div>
    <div class="chart-box">{wr_html}</div>
  </div>
</div>

<div class="section">
  <div class="section-title">📋 Detailed Results Table</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th rowspan="2">Symbol</th>
          <th rowspan="2">TF</th>
          <th colspan="6" class="intra-header" style="text-align:center; border-bottom: 2px solid var(--accent);">Intra-Bar SL</th>
          <th colspan="6" class="close-header col-sep" style="text-align:center; border-bottom: 2px solid var(--accent2);">Candle-Close SL</th>
          <th rowspan="2" class="delta-header col-sep">Δ Ret</th>
        </tr>
        <tr>
          <th class="intra-header">Return</th>
          <th class="intra-header">P&L</th>
          <th class="intra-header">Trades</th>
          <th class="intra-header">WR</th>
          <th class="intra-header">PF</th>
          <th class="intra-header">MaxDD</th>
          <th class="close-header col-sep">Return</th>
          <th class="close-header">P&L</th>
          <th class="close-header">Trades</th>
          <th class="close-header">WR</th>
          <th class="close-header">PF</th>
          <th class="close-header">MaxDD</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
      <tfoot>
        <tr class="tfoot-row">
          <td>PORTFOLIO</td>
          <td>{len(all_symbols)} coins</td>
          <td class="{i_port_class}">{intra_return:+.2f}%</td>
          <td>${intra_pnl:+,.2f}</td>
          <td>{i_total_trades}</td>
          <td>{i_avg_wr:.1f}%</td>
          <td>—</td>
          <td>{i_max_dd:.1f}%</td>
          <td class="col-sep {c_port_class}">{close_return:+.2f}%</td>
          <td>${close_pnl:+,.2f}</td>
          <td>{c_total_trades}</td>
          <td>{c_avg_wr:.1f}%</td>
          <td>—</td>
          <td>{c_max_dd:.1f}%</td>
          <td class="col-sep {port_delta_class}">{delta_portfolio:+.2f}%</td>
        </tr>
      </tfoot>
    </table>
  </div>
</div>

<div class="section">
  <div class="section-title">💡 Key Takeaways</div>
  <div style="background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; font-size: 0.9rem; line-height: 1.8;">
    <p><strong>Intra-Bar SL</strong> checks if the candle's wick touches the stop level and fills at the exact stop price — an optimistic assumption that may not reflect real execution.</p>
    <p style="margin-top: 12px;"><strong>Candle-Close SL</strong> only triggers when the candle <em>closes</em> beyond the stop level and exits at the close price — matching the live bot's actual behavior where stops are only evaluated at candle close.</p>
    <p style="margin-top: 12px;">A <strong>positive Δ</strong> means intra-bar SL shows better results, suggesting the live bot (candle-close) is leaving money on the table by not checking stops intra-bar.</p>
    <p style="margin-top: 12px;">A <strong>negative Δ</strong> means candle-close SL actually performs better for that coin, likely because wicks cause premature stop-outs that later reverse.</p>
  </div>
</div>

<footer>
  Delta Exchange Algo · SL Mode Comparison Backtest · {run_date}
</footer>
</body>
</html>"""

    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / "sl_comparison_dashboard.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="SL Mode Comparison — Intra-Bar vs Candle-Close")
    parser.add_argument("--data-folder", type=str, default=None,
                        help="Root folder containing delta_crypto_data_XH subdirectories")
    parser.add_argument("--capital", type=float, default=INITIAL_PORTFOLIO_CAPITAL,
                        help=f"Total portfolio capital in USD (default: {INITIAL_PORTFOLIO_CAPITAL})")
    parser.add_argument("--reports-dir", type=str, default="reports/sl_comparison",
                        help="Output directory for HTML report (default: reports/sl_comparison)")
    args = parser.parse_args()

    setup_logging(log_level="INFO")
    logger = get_logger(__name__)

    # ── Metadata (best-effort)
    meta_path = Path("data/historical/product_metadata.json")
    if not meta_path.exists():
        try:
            from scripts.fetch_metadata import fetch_and_save_metadata
            logger.info("Fetching product metadata for accurate position sizing…")
            fetch_and_save_metadata(str(meta_path))
        except Exception as e:
            logger.warning(f"Could not fetch metadata ({e}). Using hardcoded defaults.")

    data_root = args.data_folder or r"D:\Workspace\crypto-backtest-data"
    total_capital = args.capital
    per_coin_capital = total_capital  # shared wallet reference

    logger.info(f"SL Comparison: {len(PORTFOLIO)} coins | Wallet: ${total_capital:,.0f}")

    modes = ["intra_bar", "candle_close"]
    results = {}

    for mode in modes:
        logger.info(f"\n{'='*80}")
        logger.info(f"  Running backtest with trailing_stop_mode = '{mode}'")
        logger.info(f"{'='*80}")

        mode_metrics = []
        for i, coin_cfg in enumerate(PORTFOLIO, 1):
            sym = coin_cfg["symbol"]
            tf  = coin_cfg["timeframe"]
            logger.info(f"  [{mode}] [{i}/{len(PORTFOLIO)}] {sym} ({tf})...")
            try:
                metrics = run_single_coin(
                    coin_cfg=coin_cfg,
                    data_root=data_root,
                    per_coin_capital=per_coin_capital,
                    trailing_stop_mode=mode,
                )
                if metrics:
                    mode_metrics.append(metrics)
            except Exception as e:
                logger.error(f"  [{sym}] Backtest failed: {e}", exc_info=True)

        results[mode] = mode_metrics
        pnl = sum(m["Final Capital"] - m["Initial Capital"] for m in mode_metrics)
        ret = (pnl / total_capital * 100) if total_capital > 0 else 0
        logger.info(f"  [{mode}] Portfolio Return: {ret:+.2f}% | Net P&L: ${pnl:+,.2f}")

    intra_metrics = results.get("intra_bar", [])
    close_metrics = results.get("candle_close", [])

    if not intra_metrics or not close_metrics:
        logger.error("One or both modes produced no results. Cannot generate comparison.")
        sys.exit(1)

    # Generate comparison dashboard
    reports_dir = Path(args.reports_dir)
    logger.info("Generating comparison dashboard...")
    dash_path = generate_comparison_dashboard(intra_metrics, close_metrics, reports_dir, wallet=total_capital)
    logger.info(f"Dashboard: {dash_path.resolve()}")

    # ── Terminal summary
    intra_by_sym = {m["Symbol"]: m for m in intra_metrics}
    close_by_sym = {m["Symbol"]: m for m in close_metrics}
    all_symbols = list(dict.fromkeys(m["Symbol"] for m in intra_metrics))

    intra_pnl = sum(m["Final Capital"] - m["Initial Capital"] for m in intra_metrics)
    close_pnl = sum(m["Final Capital"] - m["Initial Capital"] for m in close_metrics)
    intra_ret = (intra_pnl / total_capital * 100) if total_capital > 0 else 0
    close_ret = (close_pnl / total_capital * 100) if total_capital > 0 else 0

    print("\n" + "=" * 130)
    print(f"  {'SL MODE COMPARISON -- Intra-Bar vs Candle-Close Trailing Stop':^126}")
    print(f"  {'Donchian Channel | Shared $1,000 Wallet | Heikin Ashi':^126}")
    print("=" * 130)
    print(f"  {'Symbol':<14} {'TF':<5} {'IntraRet':>10} {'CloseRet':>10} {'Delta':>10} {'I-Trades':>9} {'C-Trades':>9} {'I-WR%':>7} {'C-WR%':>7} {'I-PF':>7} {'C-PF':>7}")
    print("-" * 130)

    for sym in all_symbols:
        im = intra_by_sym.get(sym, {})
        cm = close_by_sym.get(sym, {})
        tf = im.get("Timeframe", "")
        i_ret = im.get("Total Return %", 0)
        c_ret = cm.get("Total Return %", 0)
        d_ret = i_ret - c_ret
        i_n = im.get("Number of Trades", 0)
        c_n = cm.get("Number of Trades", 0)
        i_wr = im.get("Win Rate %", 0)
        c_wr = cm.get("Win Rate %", 0)
        i_pf = im.get("Profit Factor", 0)
        c_pf = cm.get("Profit Factor", 0)
        i_pf_d = "  inf" if i_pf == float("inf") else f"{i_pf:7.2f}"
        c_pf_d = "  inf" if c_pf == float("inf") else f"{c_pf:7.2f}"
        print(f"  {sym:<14} {tf:<5} {i_ret:+10.2f}% {c_ret:+10.2f}% {d_ret:+10.2f}% {i_n:>9} {c_n:>9} {i_wr:>6.1f}% {c_wr:>6.1f}% {i_pf_d} {c_pf_d}")

    print("-" * 130)
    delta = intra_ret - close_ret
    sign = "+" if delta >= 0 else ""
    print(f"  {'PORTFOLIO':<14} {'':5} {intra_ret:+10.2f}% {close_ret:+10.2f}% {sign}{delta:.2f}%")
    print("=" * 130)
    print(f"\n  Dashboard: {dash_path.resolve()}")
    print()


if __name__ == "__main__":
    main()
