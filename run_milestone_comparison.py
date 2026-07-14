#!/usr/bin/env python3
"""
Milestone Exit Comparison & Optimization Backtest
==================================================
Compares milestone exit configurations and finds the optimal setting.

Scenario A (Current):  milestone @ 50% PnL → exit 30% of position
Scenario B (Proposed): milestone @ 35% PnL → exit 30%, then @ 50% PnL → full exit

Part 2 — Optimization grid search over:
  pnl_trigger: [25, 30, 35, 40, 45, 50, 60, 75, 100]
  exit_pct   : [0.20, 0.25, 0.30, 0.40, 0.50]
  full_exit  : [None, 50, 75, 100, 150]

Usage:
    python run_milestone_comparison.py --data-folder D:/Workspace/crypto-backtest-data/Futures
    python run_milestone_comparison.py  # uses default data folder
    python run_milestone_comparison.py --skip-optimization  # only run A vs B comparison
"""

import argparse
import os
import sys
import time
import itertools
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

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


# ─── Portfolio definition (mirrors multi_coin.donchian_channel in settings.yaml) ─
PORTFOLIO = [
    # ── 1h ──────────────────────────────────────────────────────
    {"symbol": "PIPPINUSD",  "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "PENGUUSD",   "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "SKYAIUSD",   "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "RIVERUSD",   "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "BEATUSD",    "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    # ── 2h ──────────────────────────────────────────────────────
    {"symbol": "HUSD",       "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "EVAAUSD",    "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "ZECUSD",     "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "PIUSD",      "timeframe": "2h", "candle_type": "heikin-ashi", "leverage": 5},
    # ── 4h ──────────────────────────────────────────────────────
    {"symbol": "DEEPUSD",    "timeframe": "4h", "candle_type": "heikin-ashi", "leverage": 5},
]

STRATEGY_NAME    = "donchian_channel"
WALLET           = 1000.0   # Shared portfolio wallet

TF_TO_SUBFOLDER = {
    "1h": "delta_crypto_data_1H",
    "2h": "delta_crypto_data_2H",
    "4h": "delta_crypto_data_4H",
    "6h": "delta_crypto_data_6H",
}

# ─── Optimization grid ───────────────────────────────────────────────────────
OPT_TRIGGERS   = [25, 30, 35, 40, 45, 50, 60, 75, 100]   # milestone 1 trigger %
OPT_EXIT_PCTS  = [0.20, 0.25, 0.30, 0.40, 0.50]           # milestone 1 partial exit fraction
OPT_FULL_EXITS = [None, 50, 75, 100, 150]                  # milestone 2 full-exit trigger % (None = disabled)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def find_csv(data_root: str, symbol: str, timeframe: str) -> Path | None:
    """Locate a symbol's CSV file across timeframe subfolders."""
    subfolder = TF_TO_SUBFOLDER.get(timeframe)
    if subfolder:
        p = Path(data_root) / subfolder / f"{symbol}_{timeframe}.csv"
        if p.exists():
            return p
    p = Path(data_root) / f"{symbol}_{timeframe}.csv"
    return p if p.exists() else None


def _load_df(data_root: str, symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Load + filter to past 1 year and return HA-transformed DataFrame, or None."""
    logger = get_logger(__name__)
    filepath = find_csv(data_root, symbol, timeframe)
    if filepath is None:
        logger.error(f"[{symbol}] CSV not found for {symbol}_{timeframe} in {data_root}")
        return None

    loader = DataLoader(str(filepath.parent))
    df = loader.load_data(filepath)
    if df.empty:
        logger.warning(f"[{symbol}] No data loaded from {filepath}")
        return None

    now_ts = int(time.time())
    one_year_ago_ts = now_ts - (365 * 24 * 3600)
    df = df[df["time"] >= one_year_ago_ts].reset_index(drop=True)
    if df.empty:
        logger.warning(f"[{symbol}] No data within the past 1 year")
        return None

    df = apply_heikin_ashi(df)
    return df


def run_single_coin(
    coin_cfg: dict,
    df: pd.DataFrame,
    milestones: list[dict],
    enable_milestones: bool = True,
) -> dict | None:
    """
    Run a backtest for one coin with the given milestone config.

    `milestones` is a list of dicts like:
        [{"pnl_pct": 50.0, "exit_pct": 0.30}]
        [{"pnl_pct": 35.0, "exit_pct": 0.30}, {"pnl_pct": 50.0, "exit_pct": 1.0}]
    """
    from strategies.donchian_strategy import DonchianChannelStrategy

    symbol   = coin_cfg["symbol"]
    timeframe = coin_cfg["timeframe"]
    leverage  = coin_cfg.get("leverage", 5)

    # Fresh strategy instance — crucial to reset all state between runs
    strategy = DonchianChannelStrategy()
    strategy.timeframe = timeframe
    if hasattr(strategy, "_update_bars_per_day"):
        strategy._update_bars_per_day(timeframe)
    strategy.leverage = leverage

    # ── Inject milestone config directly on the strategy object
    strategy.enable_profit_milestones = enable_milestones
    strategy.profit_milestones = milestones

    # Live-accurate sizing: every coin sizes against the FULL shared wallet
    cfg = get_config()
    original_capital = cfg.backtesting.initial_capital
    cfg.backtesting.initial_capital = WALLET

    engine = BacktestEngine(strategy, symbol, timeframe, STRATEGY_NAME, leverage=leverage)
    engine.initial_capital = WALLET
    engine.equity = WALLET

    trades, equity_df = engine.run(df)

    # Restore config capital
    cfg.backtesting.initial_capital = original_capital

    metrics = calculate_metrics(
        strategy_name=f"{STRATEGY_NAME} ({symbol})",
        initial_capital=WALLET,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df,
        data_df=df,
    )
    metrics["Symbol"]      = symbol
    metrics["Timeframe"]   = timeframe
    metrics["Candle Type"] = "Heikin Ashi"
    metrics["Leverage"]    = leverage
    metrics["_equity_df"]  = equity_df
    metrics["_trades"]     = trades

    return metrics


def portfolio_return(all_metrics: list[dict]) -> float:
    """Portfolio return % for a list of coin metrics (shared wallet model)."""
    total_pnl = sum(m["Final Capital"] - m["Initial Capital"] for m in all_metrics)
    return (total_pnl / WALLET * 100) if WALLET > 0 else 0.0


# ─── Dashboard generation ─────────────────────────────────────────────────────

def generate_comparison_dashboard(
    scenario_a_metrics: list[dict],
    scenario_b_metrics: list[dict],
    opt_results: list[dict],
    reports_dir: Path,
) -> Path:
    """Generate a rich HTML dashboard with side-by-side comparison and optimization results."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px

    # ── Portfolio totals
    a_pnl    = sum(m["Final Capital"] - m["Initial Capital"] for m in scenario_a_metrics)
    b_pnl    = sum(m["Final Capital"] - m["Initial Capital"] for m in scenario_b_metrics)
    a_return = (a_pnl / WALLET * 100)
    b_return = (b_pnl / WALLET * 100)

    a_by_sym = {m["Symbol"]: m for m in scenario_a_metrics}
    b_by_sym = {m["Symbol"]: m for m in scenario_b_metrics}
    all_symbols = [c["symbol"] for c in PORTFOLIO if c["symbol"] in a_by_sym]

    # ── Chart 1: Per-coin grouped return bar
    a_returns = [a_by_sym.get(s, {}).get("Total Return %", 0) for s in all_symbols]
    b_returns = [b_by_sym.get(s, {}).get("Total Return %", 0) for s in all_symbols]

    fig_ret = go.Figure()
    fig_ret.add_trace(go.Bar(
        name="Scenario A (50% trigger)",
        x=all_symbols, y=a_returns,
        marker_color="#6366f1",
        text=[f"{r:+.1f}%" for r in a_returns], textposition="outside",
        hovertemplate="<b>%{x}</b><br>A: %{y:+.2f}%<extra></extra>",
    ))
    fig_ret.add_trace(go.Bar(
        name="Scenario B (35%→50% trigger)",
        x=all_symbols, y=b_returns,
        marker_color="#22d3ee",
        text=[f"{r:+.1f}%" for r in b_returns], textposition="outside",
        hovertemplate="<b>%{x}</b><br>B: %{y:+.2f}%<extra></extra>",
    ))
    fig_ret.update_layout(
        barmode="group",
        title="Per-Coin Return % — Scenario A vs Scenario B",
        height=440,
        plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=90),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Return %", zeroline=True, zerolinecolor="#475569", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    ret_html = fig_ret.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 2: Delta bar (B − A)
    deltas = [b - a for a, b in zip(a_returns, b_returns)]
    delta_colors = ["#22c55e" if d >= 0 else "#ef4444" for d in deltas]
    fig_delta = go.Figure(go.Bar(
        x=all_symbols, y=deltas,
        marker_color=delta_colors,
        text=[f"{d:+.1f}%" for d in deltas], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Δ Return: %{y:+.2f}%<extra></extra>",
    ))
    fig_delta.update_layout(
        title="Return Difference (Scenario B − Scenario A)",
        height=360,
        plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=90),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Δ Return %", zeroline=True, zerolinecolor="#475569", gridcolor="#1e293b"),
    )
    delta_html = fig_delta.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 3: Win Rate comparison
    a_wrs = [a_by_sym.get(s, {}).get("Win Rate %", 0) for s in all_symbols]
    b_wrs = [b_by_sym.get(s, {}).get("Win Rate %", 0) for s in all_symbols]
    fig_wr = go.Figure()
    fig_wr.add_trace(go.Bar(name="Scenario A", x=all_symbols, y=a_wrs,
                            marker_color="#6366f1",
                            hovertemplate="<b>%{x}</b><br>WR: %{y:.1f}%<extra></extra>"))
    fig_wr.add_trace(go.Bar(name="Scenario B", x=all_symbols, y=b_wrs,
                            marker_color="#22d3ee",
                            hovertemplate="<b>%{x}</b><br>WR: %{y:.1f}%<extra></extra>"))
    fig_wr.update_layout(
        barmode="group", title="Win Rate % — Scenario A vs B",
        height=360, plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=90),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Win Rate %", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    wr_html = fig_wr.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 4: Profit Factor comparison
    a_pfs = [min(a_by_sym.get(s, {}).get("Profit Factor", 0), 10) for s in all_symbols]
    b_pfs = [min(b_by_sym.get(s, {}).get("Profit Factor", 0), 10) for s in all_symbols]
    fig_pf = go.Figure()
    fig_pf.add_trace(go.Bar(name="Scenario A", x=all_symbols, y=a_pfs,
                            marker_color="#6366f1",
                            hovertemplate="<b>%{x}</b><br>PF: %{y:.2f}<extra></extra>"))
    fig_pf.add_trace(go.Bar(name="Scenario B", x=all_symbols, y=b_pfs,
                            marker_color="#22d3ee",
                            hovertemplate="<b>%{x}</b><br>PF: %{y:.2f}<extra></extra>"))
    fig_pf.add_hline(y=1.0, line_dash="dash", line_color="#64748b", annotation_text="PF=1.0 break-even")
    fig_pf.update_layout(
        barmode="group", title="Profit Factor — Scenario A vs B",
        height=360, plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=55, b=90),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Profit Factor", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center"),
    )
    pf_html = fig_pf.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 5: Optimization heatmap — trigger vs exit_pct, colored by portfolio return
    # Build pivot table: rows = pnl_trigger, cols = exit_pct (for None full_exit only, as reference)
    opt_html = ""
    heatmap_html_opt = ""
    if opt_results:
        opt_df = pd.DataFrame(opt_results)

        # Heatmap: rows = pnl_trigger, cols = exit_pct_pct, values = portfolio return
        # Filter to no-full-exit configs first for a clean 2D heatmap
        sub_no_fe = opt_df[opt_df["full_exit_pnl"].isna()].copy()
        if not sub_no_fe.empty:
            pivot = sub_no_fe.pivot_table(
                index="pnl_trigger", columns="exit_pct_pct", values="portfolio_return", aggfunc="first"
            )
            z_vals  = pivot.values.tolist()
            x_labels = [f"{int(c)}% exit" for c in pivot.columns.tolist()]
            y_labels = [f"{int(r)}% trigger" for r in pivot.index.tolist()]
            z_text   = [[f"{v:+.1f}%" if not np.isnan(v) else "" for v in row] for row in z_vals]

            fig_hm = go.Figure(go.Heatmap(
                z=z_vals, x=x_labels, y=y_labels,
                colorscale="RdYlGn", zmid=0,
                text=z_text, texttemplate="%{text}",
                textfont=dict(size=10),
                colorbar=dict(title="Return %", ticksuffix="%", len=0.85, thickness=14),
                hovertemplate="<b>%{y}</b> | %{x}<br>Portfolio Return: %{z:+.2f}%<extra></extra>",
            ))
            fig_hm.update_layout(
                title="Optimization Heatmap — Milestone Trigger % vs Partial Exit % (no full-exit gate)",
                height=420,
                plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                font=dict(color="#e2e8f0"),
                xaxis=dict(side="top", gridcolor="#1e293b"),
                yaxis=dict(autorange="reversed"),
                margin=dict(l=110, r=90, t=90, b=30),
            )
            heatmap_html_opt = fig_hm.to_html(full_html=False, include_plotlyjs="cdn")

        # ── Chart 6: Full exit comparison scatter — trigger vs return, colored by full_exit level
        fig_fe = go.Figure()
        color_map = {
            "None": "#94a3b8",
            "50":   "#f59e0b",
            "75":   "#22c55e",
            "100":  "#6366f1",
            "150":  "#ec4899",
        }
        for fe_val, grp in opt_df.groupby(opt_df["full_exit_pnl"].astype(str)):
            label = "No Full Exit" if fe_val == "None" else f"Full Exit @ {fe_val}%"
            fig_fe.add_trace(go.Scatter(
                x=grp["pnl_trigger"], y=grp["portfolio_return"],
                mode="markers",
                name=label,
                marker=dict(
                    size=10,
                    color=color_map.get(fe_val, "#94a3b8"),
                    line=dict(width=1, color="#334155"),
                ),
                hovertemplate=(
                    f"<b>{label}</b><br>"
                    "Trigger: %{x}%<br>"
                    "Portfolio Return: %{y:+.2f}%<extra></extra>"
                ),
            ))
        fig_fe.update_layout(
            title="Portfolio Return vs Milestone Trigger % (grouped by Full-Exit Gate)",
            height=420,
            plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
            font=dict(color="#e2e8f0"),
            xaxis=dict(title="Milestone 1 Trigger %", gridcolor="#1e293b"),
            yaxis=dict(title="Portfolio Return %", zeroline=True, zerolinecolor="#475569", gridcolor="#1e293b"),
            legend=dict(orientation="h", y=-0.2, font=dict(size=10)),
            margin=dict(l=70, r=30, t=55, b=80),
        )
        fe_html = fig_fe.to_html(full_html=False, include_plotlyjs="cdn")

        # ── Top-10 optimization results table
        top10 = opt_df.nlargest(10, "portfolio_return")
        top_rows = ""
        for rank, (_, row) in enumerate(top10.iterrows(), 1):
            fe_str = f"{int(row['full_exit_pnl'])}%" if not pd.isna(row["full_exit_pnl"]) else "—"
            ret = row["portfolio_return"]
            pnl = ret / 100 * WALLET
            ret_class = "pos" if ret >= 0 else "neg"
            stars = "⭐⭐⭐" if rank == 1 else ("⭐⭐" if rank <= 3 else "⭐" if rank <= 5 else "")
            top_rows += f"""
        <tr{"  class='top1-row'" if rank == 1 else ""}>
            <td style="text-align:center;font-weight:700">{rank} {stars}</td>
            <td style="font-family:'JetBrains Mono',monospace">{int(row['pnl_trigger'])}%</td>
            <td style="font-family:'JetBrains Mono',monospace">{int(row['exit_pct_pct'])}%</td>
            <td style="font-family:'JetBrains Mono',monospace">{fe_str}</td>
            <td class="{ret_class}" style="font-family:'JetBrains Mono',monospace">{ret:+.2f}%</td>
            <td class="{ret_class}" style="font-family:'JetBrains Mono',monospace">${pnl:+,.2f}</td>
            <td style="font-family:'JetBrains Mono',monospace">{row['avg_win_rate']:.1f}%</td>
            <td style="font-family:'JetBrains Mono',monospace">{row['total_trades']}</td>
        </tr>"""

        # ── Full sorted optimization table (all configs)
        full_opt_rows = ""
        for _, row in opt_df.sort_values("portfolio_return", ascending=False).iterrows():
            fe_str = f"{int(row['full_exit_pnl'])}%" if not pd.isna(row["full_exit_pnl"]) else "—"
            ret = row["portfolio_return"]
            pnl = ret / 100 * WALLET
            ret_class = "pos" if ret >= 0 else "neg"
            full_opt_rows += f"""
        <tr>
            <td style="font-family:'JetBrains Mono',monospace">{int(row['pnl_trigger'])}%</td>
            <td style="font-family:'JetBrains Mono',monospace">{int(row['exit_pct_pct'])}%</td>
            <td style="font-family:'JetBrains Mono',monospace">{fe_str}</td>
            <td class="{ret_class}" style="font-family:'JetBrains Mono',monospace">{ret:+.2f}%</td>
            <td class="{ret_class}" style="font-family:'JetBrains Mono',monospace">${pnl:+,.2f}</td>
            <td style="font-family:'JetBrains Mono',monospace">{row['avg_win_rate']:.1f}%</td>
            <td style="font-family:'JetBrains Mono',monospace">{row['total_trades']}</td>
        </tr>"""

        opt_html = f"""
<!-- Optimization heatmap -->
<div class="section">
  <div class="section-title">🔥 Optimization Heatmap (No Full-Exit Gate)</div>
  <div class="chart-box full">{heatmap_html_opt}</div>
</div>

<!-- Full exit scatter -->
<div class="section">
  <div class="section-title">🎯 Portfolio Return vs Trigger % by Full-Exit Gate</div>
  <div class="chart-box full">{fe_html}</div>
</div>

<!-- Top-10 table -->
<div class="section">
  <div class="section-title">🏆 Top 10 Optimized Configurations</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>Rank</th>
          <th title="Milestone 1 trigger % of margin PnL">Trigger %</th>
          <th title="Fraction of position to exit at milestone">Partial Exit</th>
          <th title="Full exit gate — close 100% of remaining at this PnL level">Full Exit Gate</th>
          <th>Portfolio Return</th>
          <th>Net P&L ($)</th>
          <th>Avg Win Rate</th>
          <th>Total Trades</th>
        </tr>
      </thead>
      <tbody>{top_rows}</tbody>
    </table>
  </div>
</div>

<!-- Full optimization results table -->
<div class="section">
  <div class="section-title">📊 All Optimization Results (sorted by Portfolio Return)</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>Trigger %</th>
          <th>Partial Exit</th>
          <th>Full Exit Gate</th>
          <th>Portfolio Return</th>
          <th>Net P&L ($)</th>
          <th>Avg Win Rate</th>
          <th>Total Trades</th>
        </tr>
      </thead>
      <tbody>{full_opt_rows}</tbody>
    </table>
  </div>
</div>
"""

    # ── Side-by-side summary table
    table_rows = ""
    for sym in all_symbols:
        am = a_by_sym.get(sym, {})
        bm = b_by_sym.get(sym, {})
        tf = am.get("Timeframe", "")

        a_ret = am.get("Total Return %", 0)
        b_ret = bm.get("Total Return %", 0)
        d_ret = b_ret - a_ret

        a_pnl_v = am.get("Final Capital", WALLET) - WALLET
        b_pnl_v = bm.get("Final Capital", WALLET) - WALLET

        a_pf  = am.get("Profit Factor", 0)
        b_pf  = bm.get("Profit Factor", 0)
        a_wr  = am.get("Win Rate %", 0)
        b_wr  = bm.get("Win Rate %", 0)
        a_dd  = am.get("Max Drawdown %", 0)
        b_dd  = bm.get("Max Drawdown %", 0)
        a_n   = am.get("Number of Trades", 0)
        b_n   = bm.get("Number of Trades", 0)

        a_pf_d = "inf" if a_pf == float("inf") else f"{a_pf:.2f}"
        b_pf_d = "inf" if b_pf == float("inf") else f"{b_pf:.2f}"
        d_cls  = "pos" if d_ret >= 0 else "neg"
        a_cls  = "pos" if a_ret >= 0 else "neg"
        b_cls  = "pos" if b_ret >= 0 else "neg"

        table_rows += f"""
        <tr>
            <td class="symbol">{sym}</td>
            <td>{tf}</td>
            <td class="{a_cls}">{a_ret:+.2f}%</td>
            <td>${a_pnl_v:+,.2f}</td>
            <td>{a_n}</td>
            <td>{a_wr:.1f}%</td>
            <td>{a_pf_d}</td>
            <td>{a_dd:.1f}%</td>
            <td class="col-sep {b_cls}">{b_ret:+.2f}%</td>
            <td>${b_pnl_v:+,.2f}</td>
            <td>{b_n}</td>
            <td>{b_wr:.1f}%</td>
            <td>{b_pf_d}</td>
            <td>{b_dd:.1f}%</td>
            <td class="col-sep {d_cls}">{d_ret:+.2f}%</td>
        </tr>"""

    a_total_trades = sum(m.get("Number of Trades", 0) for m in scenario_a_metrics)
    b_total_trades = sum(m.get("Number of Trades", 0) for m in scenario_b_metrics)
    a_avg_wr = sum(m.get("Win Rate %", 0) for m in scenario_a_metrics) / max(len(scenario_a_metrics), 1)
    b_avg_wr = sum(m.get("Win Rate %", 0) for m in scenario_b_metrics) / max(len(scenario_b_metrics), 1)
    d_port   = b_return - a_return
    port_d_cls = "pos" if d_port >= 0 else "neg"
    a_port_cls = "pos" if a_return >= 0 else "neg"
    b_port_cls = "pos" if b_return >= 0 else "neg"

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    winner   = "🟦 Scenario A" if a_return > b_return else ("🩵 Scenario B" if b_return > a_return else "🟰 Tie")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Milestone Exit Comparison — Donchian Channel Portfolio</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:       #0a0f1e;
    --surface:  #111827;
    --border:   #1e293b;
    --accent:   #6366f1;
    --accent2:  #22d3ee;
    --text:     #e2e8f0;
    --muted:    #94a3b8;
    --pos:      #22c55e;
    --neg:      #ef4444;
    --warn:     #f59e0b;
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
  .scenario-legend {{
    display: flex;
    gap: 24px;
    margin-top: 20px;
    flex-wrap: wrap;
  }}
  .scenario-pill {{
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 16px;
    font-size: 0.82rem;
  }}
  .pill-dot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .pill-a {{ background: #6366f1; }}
  .pill-b {{ background: #22d3ee; }}
  /* ── KPI Cards */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    padding: 32px 60px;
    background: var(--bg);
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
  .kpi-card.a-card::after  {{ background: #6366f1; }}
  .kpi-card.b-card::after  {{ background: #22d3ee; }}
  .kpi-card.pos::after     {{ background: var(--pos); }}
  .kpi-card.neg::after     {{ background: var(--neg); }}
  .kpi-card.winner::after  {{ background: var(--warn); }}
  .kpi-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }}
  .kpi-value {{ font-size: 1.6rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
  .kpi-value.pos {{ color: var(--pos); }}
  .kpi-value.neg {{ color: var(--neg); }}
  .kpi-value.neutral {{ color: var(--text); }}
  .kpi-value.warn {{ color: var(--warn); }}
  .kpi-sub {{ font-size: 0.78rem; color: var(--muted); margin-top: 4px; }}
  /* ── Section */
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
  .chart-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 4px;
    overflow: hidden;
    margin-bottom: 20px;
  }}
  .chart-box.full {{ width: 100%; }}
  .chart-grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }}
  /* ── Table */
  .table-wrapper {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow-x: auto;
    margin-bottom: 24px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}
  thead tr {{ border-bottom: 2px solid var(--border); }}
  thead th {{
    padding: 13px 14px;
    text-align: left;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    white-space: nowrap;
  }}
  thead th.col-sep {{ border-left: 2px solid var(--accent); }}
  tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.15s; }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(99,102,241,0.05); }}
  tbody tr.top1-row {{ background: rgba(245,158,11,0.08); border-left: 3px solid var(--warn); }}
  tbody td {{ padding: 12px 14px; white-space: nowrap; }}
  td.col-sep {{ border-left: 2px solid rgba(99,102,241,0.3); }}
  .symbol {{ font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; }}
  .pos {{ color: var(--pos); font-weight: 500; }}
  .neg {{ color: var(--neg); font-weight: 500; }}
  .tfoot-row td {{
    padding: 13px 14px;
    font-weight: 700;
    background: rgba(99,102,241,0.08);
    border-top: 2px solid var(--accent);
  }}
  .thead-group th {{
    background: rgba(99,102,241,0.06);
    text-align: center;
    padding: 8px 14px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
  }}
  .thead-group th.a-head {{ color: #a5b4fc; border-right: 1px solid var(--border); }}
  .thead-group th.b-head {{ color: #67e8f9; border-right: 1px solid var(--border); }}
  .thead-group th.d-head {{ color: var(--warn); }}
  a {{ color: var(--accent2); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  footer {{
    text-align: center;
    padding: 24px;
    color: var(--muted);
    font-size: 0.75rem;
    border-top: 1px solid var(--border);
  }}
  @media (max-width: 900px) {{
    .hero, .kpi-grid, .section {{ padding-left: 20px; padding-right: 20px; }}
    .chart-grid-2 {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>

<!-- Hero -->
<div class="hero">
  <div class="hero-badge">🎯 Milestone Exit Comparison</div>
  <h1>Donchian Channel — Milestone Exit Optimizer</h1>
  <div class="hero-meta">
    <span>Generated: {run_date}</span>
    <span>Shared wallet: ${WALLET:,.0f}</span>
    <span>Portfolio: {len(all_symbols)} coins | Donchian Channel (Heikin Ashi)</span>
    <span>Data: Past 1 year</span>
  </div>
  <div class="scenario-legend">
    <div class="scenario-pill">
      <div class="pill-dot pill-a"></div>
      <div>
        <strong>Scenario A</strong> (Current)<br>
        <span style="color:var(--muted);font-size:0.78rem">Milestone @ 50% PnL → exit 30%</span>
      </div>
    </div>
    <div class="scenario-pill">
      <div class="pill-dot pill-b"></div>
      <div>
        <strong>Scenario B</strong> (Proposed)<br>
        <span style="color:var(--muted);font-size:0.78rem">Milestone 1 @ 35% PnL → exit 30% | Milestone 2 @ 50% PnL → full exit</span>
      </div>
    </div>
  </div>
</div>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card a-card">
    <div class="kpi-label">Scenario A — Portfolio Return</div>
    <div class="kpi-value {'pos' if a_return >= 0 else 'neg'}">{a_return:+.2f}%</div>
    <div class="kpi-sub">${a_pnl:+,.2f} net P&amp;L</div>
  </div>
  <div class="kpi-card b-card">
    <div class="kpi-label">Scenario B — Portfolio Return</div>
    <div class="kpi-value {'pos' if b_return >= 0 else 'neg'}">{b_return:+.2f}%</div>
    <div class="kpi-sub">${b_pnl:+,.2f} net P&amp;L</div>
  </div>
  <div class="kpi-card {'pos' if d_port >= 0 else 'neg'}">
    <div class="kpi-label">Δ Return (B − A)</div>
    <div class="kpi-value {'pos' if d_port >= 0 else 'neg'}">{d_port:+.2f}%</div>
    <div class="kpi-sub">{'Scenario B wins' if d_port > 0 else ('Scenario A wins' if d_port < 0 else 'Tied')}</div>
  </div>
  <div class="kpi-card winner">
    <div class="kpi-label">Winner</div>
    <div class="kpi-value warn" style="font-size:1.1rem;padding-top:4px">{winner}</div>
    <div class="kpi-sub">By portfolio return</div>
  </div>
  <div class="kpi-card a-card">
    <div class="kpi-label">A — Total Trades</div>
    <div class="kpi-value neutral">{a_total_trades}</div>
    <div class="kpi-sub">Avg WR: {a_avg_wr:.1f}%</div>
  </div>
  <div class="kpi-card b-card">
    <div class="kpi-label">B — Total Trades</div>
    <div class="kpi-value neutral">{b_total_trades}</div>
    <div class="kpi-sub">Avg WR: {b_avg_wr:.1f}%</div>
  </div>
</div>

<!-- Charts -->
<div class="section">
  <div class="section-title">📊 Side-by-Side Performance</div>
  <div class="chart-box full">{ret_html}</div>
  <div class="chart-box full">{delta_html}</div>
  <div class="chart-grid-2">
    <div class="chart-box">{wr_html}</div>
    <div class="chart-box">{pf_html}</div>
  </div>
</div>

<!-- Comparison Table -->
<div class="section">
  <div class="section-title">📋 Detailed Comparison Table</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr class="thead-group">
          <th colspan="2" style="border-right:1px solid var(--border)"></th>
          <th colspan="6" class="a-head">Scenario A — Current (50% trigger)</th>
          <th colspan="6" class="b-head">Scenario B — Proposed (35%→50% trigger)</th>
          <th class="d-head">Δ Return</th>
        </tr>
        <tr>
          <th>Symbol</th>
          <th>TF</th>
          <th>Return %</th>
          <th>Net P&amp;L</th>
          <th>Trades</th>
          <th>Win %</th>
          <th>PF</th>
          <th>Max DD</th>
          <th class="col-sep">Return %</th>
          <th>Net P&amp;L</th>
          <th>Trades</th>
          <th>Win %</th>
          <th>PF</th>
          <th>Max DD</th>
          <th class="col-sep">B − A</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
      <tfoot>
        <tr class="tfoot-row">
          <td>PORTFOLIO</td>
          <td>{len(all_symbols)} coins</td>
          <td class="{a_port_cls}">{a_return:+.2f}%</td>
          <td class="{a_port_cls}">${a_pnl:+,.2f}</td>
          <td>{a_total_trades}</td>
          <td>{a_avg_wr:.1f}%</td>
          <td>—</td>
          <td>—</td>
          <td class="col-sep {b_port_cls}">{b_return:+.2f}%</td>
          <td class="{b_port_cls}">${b_pnl:+,.2f}</td>
          <td>{b_total_trades}</td>
          <td>{b_avg_wr:.1f}%</td>
          <td>—</td>
          <td>—</td>
          <td class="col-sep {port_d_cls}">{d_port:+.2f}%</td>
        </tr>
      </tfoot>
    </table>
  </div>
</div>

{opt_html}

<footer>
  Delta Exchange Algo · Donchian Channel · Milestone Exit Comparison · {run_date}
</footer>
</body>
</html>"""

    out_path = reports_dir / "milestone_comparison.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Milestone Exit Comparison & Optimization Backtest"
    )
    parser.add_argument(
        "--data-folder", type=str,
        default=r"D:\Workspace\crypto-backtest-data\Futures",
        help="Root folder containing delta_crypto_data_XH subdirectories",
    )
    parser.add_argument(
        "--capital", type=float, default=WALLET,
        help=f"Shared portfolio wallet in USD (default: {WALLET})",
    )
    parser.add_argument(
        "--reports-dir", type=str, default="reports/portfolio",
        help="Output directory for HTML reports",
    )
    parser.add_argument(
        "--skip-optimization", action="store_true",
        help="Only run Scenario A vs B comparison (skip grid search)",
    )
    args = parser.parse_args()

    setup_logging(log_level="INFO")
    logger = get_logger(__name__)

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    data_root = args.data_folder

    # ── Scenario definitions
    SCENARIO_A_MILESTONES = [
        {"pnl_pct": 50.0, "exit_pct": 0.30},  # Current: one milestone at 50%
    ]
    SCENARIO_B_MILESTONES = [
        {"pnl_pct": 35.0, "exit_pct": 0.30},  # First exit at 35%
        {"pnl_pct": 50.0, "exit_pct": 1.00},  # Full exit at 50%
    ]

    logger.info("=" * 80)
    logger.info("  MILESTONE EXIT COMPARISON BACKTEST")
    logger.info(f"  Scenario A: milestone @ 50% → exit 30%")
    logger.info(f"  Scenario B: milestone @ 35% → exit 30%  +  @ 50% → full exit")
    logger.info(f"  Portfolio : {len(PORTFOLIO)} coins | Wallet: ${WALLET:,.0f}")
    logger.info("=" * 80)

    # ── Pre-load all DataFrames (avoid re-reading CSVs for each optimization run)
    logger.info("\nPre-loading DataFrames for all coins…")
    coin_dfs: dict[str, pd.DataFrame | None] = {}
    for coin_cfg in PORTFOLIO:
        sym = coin_cfg["symbol"]
        tf  = coin_cfg["timeframe"]
        df  = _load_df(data_root, sym, tf)
        coin_dfs[sym] = df
        status = f"{len(df)} bars" if df is not None else "FAILED"
        logger.info(f"  [{sym}] {status}")

    # ─── PART 1: Scenario A vs B ─────────────────────────────────────────────
    logger.info("\n[Part 1] Running Scenario A (current: 50% trigger)…")
    a_metrics = []
    for i, coin_cfg in enumerate(PORTFOLIO, 1):
        sym = coin_cfg["symbol"]
        df  = coin_dfs.get(sym)
        if df is None:
            continue
        logger.info(f"  [{i}/{len(PORTFOLIO)}] {sym}")
        try:
            m = run_single_coin(coin_cfg, df.copy(), SCENARIO_A_MILESTONES)
            if m:
                a_metrics.append(m)
        except Exception as e:
            logger.error(f"  [{sym}] Scenario A failed: {e}", exc_info=True)

    logger.info("\n[Part 1] Running Scenario B (proposed: 35%→50% trigger)…")
    b_metrics = []
    for i, coin_cfg in enumerate(PORTFOLIO, 1):
        sym = coin_cfg["symbol"]
        df  = coin_dfs.get(sym)
        if df is None:
            continue
        logger.info(f"  [{i}/{len(PORTFOLIO)}] {sym}")
        try:
            m = run_single_coin(coin_cfg, df.copy(), SCENARIO_B_MILESTONES)
            if m:
                b_metrics.append(m)
        except Exception as e:
            logger.error(f"  [{sym}] Scenario B failed: {e}", exc_info=True)

    # ── Print Part 1 summary
    a_ret = portfolio_return(a_metrics)
    b_ret = portfolio_return(b_metrics)
    a_pnl = a_ret / 100 * WALLET
    b_pnl = b_ret / 100 * WALLET

    print("\n" + "=" * 100)
    print(f"  {'SCENARIO A vs B - PART 1 RESULTS':^96}")
    print("=" * 100)
    print(f"  {'Symbol':<14} {'TF':<5} {'A Return':>10}  {'A PnL':>9}  {'A Trades':>8}  {'A WR':>6}  |  {'B Return':>10}  {'B PnL':>9}  {'B Trades':>8}  {'B WR':>6}  {'Delta':>8}")
    print("-" * 100)

    a_by_sym = {m["Symbol"]: m for m in a_metrics}
    b_by_sym = {m["Symbol"]: m for m in b_metrics}
    for coin_cfg in PORTFOLIO:
        sym = coin_cfg["symbol"]
        am  = a_by_sym.get(sym)
        bm  = b_by_sym.get(sym)
        if not am or not bm:
            continue
        ar  = am.get("Total Return %", 0)
        br  = bm.get("Total Return %", 0)
        ap  = am.get("Final Capital", WALLET) - WALLET
        bp  = bm.get("Final Capital", WALLET) - WALLET
        an  = am.get("Number of Trades", 0)
        bn  = bm.get("Number of Trades", 0)
        awr = am.get("Win Rate %", 0)
        bwr = bm.get("Win Rate %", 0)
        d   = br - ar
        d_s = f"{d:+.2f}%" if d != 0 else "n/a"
        print(f"  {sym:<14} {coin_cfg['timeframe']:<5} {ar:+10.2f}%  ${ap:+8,.2f}  {an:>8}  {awr:>5.1f}%  |  {br:+10.2f}%  ${bp:+8,.2f}  {bn:>8}  {bwr:>5.1f}%  {d_s:>8}")

    print("-" * 100)
    winner_str = "SCENARIO B WINS" if b_ret > a_ret else ("SCENARIO A WINS" if a_ret > b_ret else "TIE")
    print(f"  PORTFOLIO TOTAL:  A: {a_ret:+.2f}% (${a_pnl:+,.2f})  |  B: {b_ret:+.2f}% (${b_pnl:+,.2f})  |  Delta = {b_ret - a_ret:+.2f}%  [{winner_str}]")
    print("=" * 100)

    # ─── PART 2: Optimization grid search ────────────────────────────────────
    opt_results = []

    if not args.skip_optimization:
        grid = list(itertools.product(OPT_TRIGGERS, OPT_EXIT_PCTS, OPT_FULL_EXITS))
        total_combos = len(grid)
        logger.info(f"\n[Part 2] Optimization grid search: {total_combos} combinations × {len(PORTFOLIO)} coins…")

        for combo_idx, (pnl_trigger, exit_pct, full_exit) in enumerate(grid, 1):
            # Build milestone list for this combo
            milestones = [{"pnl_pct": float(pnl_trigger), "exit_pct": float(exit_pct)}]
            if full_exit is not None:
                if float(full_exit) > float(pnl_trigger):   # only add if it's a higher level
                    milestones.append({"pnl_pct": float(full_exit), "exit_pct": 1.0})
                else:
                    # Skip invalid combo where full_exit <= trigger
                    continue

            combo_metrics = []
            for coin_cfg in PORTFOLIO:
                sym = coin_cfg["symbol"]
                df  = coin_dfs.get(sym)
                if df is None:
                    continue
                try:
                    m = run_single_coin(coin_cfg, df.copy(), milestones)
                    if m:
                        combo_metrics.append(m)
                except Exception:
                    pass

            if not combo_metrics:
                continue

            port_ret  = portfolio_return(combo_metrics)
            avg_wr    = sum(m.get("Win Rate %", 0) for m in combo_metrics) / len(combo_metrics)
            tot_trades = sum(m.get("Number of Trades", 0) for m in combo_metrics)

            opt_results.append({
                "pnl_trigger":    pnl_trigger,
                "exit_pct":       exit_pct,
                "exit_pct_pct":   round(exit_pct * 100),
                "full_exit_pnl":  float(full_exit) if full_exit is not None else float("nan"),
                "portfolio_return": port_ret,
                "avg_win_rate":   avg_wr,
                "total_trades":   tot_trades,
            })

            if combo_idx % 10 == 0 or combo_idx == total_combos:
                pct_done = combo_idx / total_combos * 100
                logger.info(
                    f"  Optimization: {combo_idx}/{total_combos} ({pct_done:.0f}%)  |  "
                    f"Last: trigger={pnl_trigger}% exit={exit_pct:.0%} full_exit={full_exit}  ->  {port_ret:+.2f}%"
                )

        # Print top-10 results
        if opt_results:
            opt_df = pd.DataFrame(opt_results).sort_values("portfolio_return", ascending=False)
            print("\n" + "=" * 80)
            print(f"  {'TOP 10 OPTIMIZATION RESULTS':^76}")
            print("=" * 80)
            print(f"  {'Rank':<5} {'Trigger':>8} {'PartialExit':>11} {'FullExit':>10} {'PortReturn':>12} {'NetPnL':>10} {'AvgWR':>7} {'Trades':>7}")
            print("-" * 80)
            for rank, (_, row) in enumerate(opt_df.head(10).iterrows(), 1):
                fe_s = f"{int(row['full_exit_pnl'])}%" if not pd.isna(row["full_exit_pnl"]) else "none"
                pnl  = row["portfolio_return"] / 100 * WALLET
                stars = "***" if rank == 1 else ("**" if rank <= 3 else "*" if rank <= 5 else "")
                print(
                    f"  {rank:<3} {stars:<2}  "
                    f"{int(row['pnl_trigger']):>6}%  "
                    f"{int(row['exit_pct_pct']):>9}%  "
                    f"{fe_s:>10}  "
                    f"{row['portfolio_return']:>+11.2f}%  "
                    f"${pnl:>+8,.2f}  "
                    f"{row['avg_win_rate']:>6.1f}%  "
                    f"{int(row['total_trades']):>7}"
                )
            print("=" * 80)
    else:
        logger.info("\n[Part 2] Skipped (--skip-optimization flag set)")

    # ─── Generate Dashboard ───────────────────────────────────────────────────
    logger.info("\nGenerating HTML dashboard...")
    dash_path = generate_comparison_dashboard(
        scenario_a_metrics=a_metrics,
        scenario_b_metrics=b_metrics,
        opt_results=opt_results,
        reports_dir=reports_dir,
    )

    print(f"\n  [OK] Dashboard saved: {dash_path.resolve()}")
    print(f"     Open in browser: file:///{str(dash_path.resolve()).replace(chr(92), '/')}\n")


if __name__ == "__main__":
    main()
