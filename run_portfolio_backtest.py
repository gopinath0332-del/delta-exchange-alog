#!/usr/bin/env python3
"""
Portfolio Backtest Runner
=========================
Runs backtests for all coins defined in multi_coin.donchian_channel
in settings.yaml and generates individual + combined portfolio reports.

Usage:
    python run_portfolio_backtest.py --data-folder D:/Workspace/crypto-backtest-data
    python run_portfolio_backtest.py  # uses default data folder from config
"""

import argparse
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

# Force UTC timezone for consistent backtest reporting
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

from core.logger import setup_logging, get_logger
from core.config import get_config
from core.trading import get_trade_config
from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.reporter import Reporter
from backtest.candle_transform import apply_heikin_ashi


# ─── Portfolio definition ────────────────────────────────────────────────────
# Mirrors multi_coin.donchian_channel in settings.yaml
PORTFOLIO = [
    {"symbol": "PIPPINUSD",  "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
    {"symbol": "PENGUUSD",   "timeframe": "1h", "candle_type": "heikin-ashi", "leverage": 5},
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
INITIAL_PORTFOLIO_CAPITAL = 1000.0  # Total portfolio budget in USD

# Subfolder name for this portfolio run's data files  
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
    # Fallback: flat directory
    p = Path(data_root) / f"{symbol}_{timeframe}.csv"
    return p if p.exists() else None


def run_single_coin(
    coin_cfg: dict,
    data_root: str,
    reporter: Reporter,
    per_coin_capital: float,
) -> dict | None:
    """Run backtest for one coin and return its metrics dict."""
    logger = get_logger(__name__)
    symbol = coin_cfg["symbol"]
    timeframe = coin_cfg["timeframe"]
    candle_type_str = coin_cfg.get("candle_type", "standard")
    leverage = coin_cfg.get("leverage", 5)

    # Normalize candle type for internal use
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

    logger.info(f"[{symbol}] {len(df)} bars | {timeframe} | {internal_candle} candles")

    # Apply Heikin Ashi transform
    if internal_candle == "heikin_ashi":
        df = apply_heikin_ashi(df)

    # Load strategy
    from strategies.donchian_strategy import DonchianChannelStrategy
    strategy = DonchianChannelStrategy()
    strategy.timeframe = timeframe
    if hasattr(strategy, "_update_bars_per_day"):
        strategy._update_bars_per_day(timeframe)
    strategy.leverage = leverage

    # Live-accurate sizing: every coin references the FULL shared wallet.
    # fractional sizing → risk = 1.5% × $1,000 = $15/trade,
    # margin cap        → 7%  × $1,000 = $70/trade  (matches live bot)
    from core.config import get_config as _gc
    cfg = _gc()
    original_capital = cfg.backtesting.initial_capital
    cfg.backtesting.initial_capital = per_coin_capital   # per_coin_capital == total wallet ($1,000)

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
    # Attach raw data so portfolio dashboard can build equity curve + monthly heatmap
    metrics["_equity_df"] = equity_df
    metrics["_trades"]    = trades

    # Per-coin HTML report
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        csv_path = reporter.reports_dir / f"{symbol}_{timeframe}_trades.csv"
        trades_df.to_csv(csv_path, index=False)

    reporter.generate_report(
        symbol=symbol,
        timeframe=timeframe,
        metrics=metrics,
        trades=trades,
        equity_df=equity_df,
        candle_type=internal_candle,
    )

    logger.info(
        f"[{symbol}] Done | Return: {metrics['Total Return %']:+.2f}% | "
        f"PF: {metrics['Profit Factor']:.2f} | "
        f"WR: {metrics['Win Rate %']:.1f}% | "
        f"Trades: {metrics['Number of Trades']}"
    )
    return metrics


def generate_portfolio_dashboard(all_metrics: list[dict], reports_dir: Path, wallet: float = 1000.0):
    """Generate a rich, self-contained portfolio HTML dashboard.

    Live-accurate model:
      - All coins share a single wallet (wallet=$1,000)
      - Each coin is sized with fractional risk against the FULL wallet
      - Portfolio P&L  = sum of individual coin P&Ls
      - Portfolio return = total P&L / wallet × 100
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import plotly.express as px

    # Each coin's initial_capital == wallet (sizing reference), NOT a split
    # Portfolio level: single wallet + all coins' net PnLs
    coin_pnls = [m["Final Capital"] - m["Initial Capital"] for m in all_metrics]
    total_pnl = sum(coin_pnls)
    total_initial = wallet
    total_final   = wallet + total_pnl
    total_return_pct = (total_pnl / wallet * 100) if wallet > 0 else 0

    # ── Sort by Total Return %
    sorted_metrics = sorted(all_metrics, key=lambda x: x.get("Total Return %", 0), reverse=True)

    # ── Chart 1: Per-coin return bar chart
    symbols   = [m["Symbol"] for m in sorted_metrics]
    returns   = [m.get("Total Return %", 0) for m in sorted_metrics]
    colors_bar = ["#27ae60" if r >= 0 else "#e74c3c" for r in returns]

    fig_returns = go.Figure(go.Bar(
        x=symbols, y=returns,
        marker_color=colors_bar,
        text=[f"{r:+.1f}%" for r in returns],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Return: %{y:.2f}%<extra></extra>",
    ))
    fig_returns.update_layout(
        title="Per-Coin Total Return %",
        height=380,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=50, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(zeroline=True, zerolinecolor="#475569", gridcolor="#1e293b"),
    )
    returns_html = fig_returns.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 2: Win rate vs Profit Factor scatter
    fig_scatter = go.Figure(go.Scatter(
        x=[m.get("Win Rate %", 0) for m in all_metrics],
        y=[min(m.get("Profit Factor", 0), 10) for m in all_metrics],  # cap at 10 for display
        mode="markers+text",
        text=[m["Symbol"] for m in all_metrics],
        textposition="top center",
        marker=dict(
            size=14,
            color=[m.get("Total Return %", 0) for m in all_metrics],
            colorscale="RdYlGn",
            showscale=True,
            colorbar=dict(title="Return %"),
            line=dict(width=1, color="#334155"),
        ),
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Win Rate: %{x:.1f}%<br>"
            "Profit Factor: %{y:.2f}<extra></extra>"
        ),
    ))
    fig_scatter.add_hline(y=1.0, line_dash="dash", line_color="#64748b",
                          annotation_text="PF = 1.0 (break-even)")
    fig_scatter.update_layout(
        title="Win Rate vs Profit Factor (color = Return%)",
        height=380,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(title="Win Rate %", gridcolor="#1e293b"),
        yaxis=dict(title="Profit Factor", gridcolor="#1e293b"),
        margin=dict(l=60, r=30, t=50, b=60),
    )
    scatter_html = fig_scatter.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 3: PnL Contribution pie (live-accurate — shared wallet)
    # Show which coin contributed what % of total portfolio P&L.
    # Negative contributors are shown as 0 in the pie but labelled separately.
    pnl_per_coin = {m["Symbol"]: m["Final Capital"] - m["Initial Capital"] for m in all_metrics}
    positive_pnl = {k: max(v, 0) for k, v in pnl_per_coin.items()}
    total_pos = sum(positive_pnl.values()) or 1

    fig_alloc = go.Figure(go.Pie(
        labels=list(pnl_per_coin.keys()),
        values=[max(v, 0) for v in pnl_per_coin.values()],
        hole=0.55,
        marker=dict(colors=px.colors.qualitative.Vivid),
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>P&L: $%{customdata:+.2f}<extra></extra>",
        customdata=[pnl_per_coin[m["Symbol"]] for m in all_metrics],
    ))
    fig_alloc.add_annotation(
        text=f"<b>${total_pnl:+,.0f}</b><br><span style='font-size:11px'>Total P&amp;L</span>",
        x=0.5, y=0.5, xref="paper", yref="paper",
        showarrow=False, font=dict(size=17, color="#e2e8f0"),
    )
    fig_alloc.update_layout(
        title="P&L Contribution per Coin (shared $1,000 wallet)",
        height=350,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(font=dict(size=10)),
    )
    alloc_html = fig_alloc.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 4: Max drawdown bar chart
    fig_dd = go.Figure(go.Bar(
        x=[m["Symbol"] for m in sorted_metrics],
        y=[-m.get("Max Drawdown %", 0) for m in sorted_metrics],
        marker_color="#e74c3c",
        text=[f"-{m.get('Max Drawdown %', 0):.1f}%" for m in sorted_metrics],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Max Drawdown: %{y:.2f}%<extra></extra>",
    ))
    fig_dd.update_layout(
        title="Max Drawdown % per Coin",
        height=350,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=50, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Drawdown %", gridcolor="#1e293b"),
    )
    dd_html = fig_dd.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 5: Trade count stacked bar (wins vs losses)
    win_counts  = []
    loss_counts = []
    symbols_tc  = []
    for m in sorted_metrics:
        n = m.get("Number of Trades", 0)
        wr = m.get("Win Rate %", 0)
        wins = round(n * wr / 100)
        losses = n - wins
        win_counts.append(wins)
        loss_counts.append(losses)
        symbols_tc.append(m["Symbol"])

    fig_trades = go.Figure()
    fig_trades.add_trace(go.Bar(
        name="Wins", x=symbols_tc, y=win_counts,
        marker_color="#27ae60",
        hovertemplate="<b>%{x}</b><br>Wins: %{y}<extra></extra>",
    ))
    fig_trades.add_trace(go.Bar(
        name="Losses", x=symbols_tc, y=loss_counts,
        marker_color="#e74c3c",
        hovertemplate="<b>%{x}</b><br>Losses: %{y}<extra></extra>",
    ))
    fig_trades.update_layout(
        barmode="stack",
        title="Trade Count — Wins vs Losses",
        height=350,
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        margin=dict(l=50, r=30, t=50, b=80),
        xaxis=dict(tickangle=-30),
        yaxis=dict(title="Trade Count", gridcolor="#1e293b"),
        legend=dict(orientation="h", y=1.05, x=0.5, xanchor="center"),
    )
    trades_html = fig_trades.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 6: Combined Portfolio Equity Curve
    coin_pnl_series = []
    coin_eq_traces  = []
    _vivid = px.colors.qualitative.Vivid
    for _i, _m in enumerate(all_metrics):
        _eq = _m.get("_equity_df")
        if _eq is None or _eq.empty:
            continue
        _eq = _eq.copy()
        if not pd.api.types.is_datetime64_any_dtype(_eq["time"]):
            _eq["time"] = pd.to_datetime(_eq["time"], errors="coerce")
        _eq = _eq.dropna(subset=["time"]).set_index("time")
        _daily = _eq["equity"].resample("D").last().ffill()
        coin_pnl_series.append(_daily - wallet)          # per-coin daily PnL contribution
        coin_eq_traces.append((_m["Symbol"], _daily, _vivid[_i % len(_vivid)]))

    equity_curve_html = ""
    if coin_pnl_series:
        _combined   = pd.concat(coin_pnl_series, axis=1, sort=True).ffill().fillna(0)
        _port_eq    = wallet + _combined.sum(axis=1)

        fig_eq = go.Figure()
        # Faded per-coin lines first
        for _sym, _daily, _col in coin_eq_traces:
            fig_eq.add_trace(go.Scatter(
                x=_daily.index, y=_daily.values,
                mode="lines", name=_sym,
                line=dict(color=_col, width=1, dash="dot"),
                opacity=0.45,
            ))
        # Bold portfolio line on top
        fig_eq.add_trace(go.Scatter(
            x=_port_eq.index, y=_port_eq.values,
            mode="lines", name="Portfolio",
            line=dict(color="#6366f1", width=3),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.07)",
        ))
        fig_eq.add_hline(
            y=wallet, line_dash="dash", line_color="#64748b",
            annotation_text=f"Starting Wallet: ${wallet:,.0f}",
            annotation_position="bottom right",
        )
        fig_eq.update_layout(
            title="Portfolio Equity Curve — Shared $1,000 Wallet (per-coin dotted)",
            height=460,
            plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
            font=dict(color="#e2e8f0"),
            xaxis=dict(title="Date", gridcolor="#1e293b"),
            yaxis=dict(title="Equity ($)", gridcolor="#1e293b"),
            margin=dict(l=70, r=30, t=55, b=60),
            legend=dict(orientation="h", y=-0.18, font=dict(size=10), traceorder="reversed"),
            hovermode="x unified",
        )
        equity_curve_html = fig_eq.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 7: Monthly Returns Heatmap
    _monthly_data = {}
    for _m in all_metrics:
        _sym  = _m["Symbol"]
        _mpnl = {}
        for _t in (_m.get("_trades") or []):
            _exit_str = (_t.get("Exit Time") or "").split(" (")[0].strip()
            _pnl = _t.get("Profit/Loss", 0)
            try:
                _edt = pd.to_datetime(_exit_str, format="%d-%m-%y %H:%M", errors="coerce")
                if pd.isna(_edt):
                    continue
                _mk = _edt.strftime("%Y-%m")
                _mpnl[_mk] = _mpnl.get(_mk, 0) + _pnl
            except Exception:
                continue
        _monthly_data[_sym] = _mpnl

    _all_months = sorted({mk for d in _monthly_data.values() for mk in d})
    _syms_hm    = [_m["Symbol"] for _m in all_metrics]
    _z, _txt    = [], []
    for _sym in _syms_hm:
        _row = [_monthly_data.get(_sym, {}).get(mk, 0) / wallet * 100 for mk in _all_months]
        _z.append(_row)
        _txt.append([f"{v:+.1f}%" if v != 0 else "" for v in _row])
    # Portfolio totals row
    _port_row = [sum(_monthly_data.get(_s, {}).get(mk, 0) for _s in _syms_hm) / wallet * 100 for mk in _all_months]
    _z.append(_port_row)
    _txt.append([f"{v:+.1f}%" if v != 0 else "" for v in _port_row])
    _syms_hm_full = _syms_hm + ["PORTFOLIO"]
    _month_labels = [pd.to_datetime(mk + "-01").strftime("%b '%y") for mk in _all_months]

    heatmap_html = ""
    if _all_months:
        fig_hm = go.Figure(go.Heatmap(
            z=_z,
            x=_month_labels,
            y=_syms_hm_full,
            colorscale="RdYlGn",
            zmid=0,
            text=_txt,
            texttemplate="%{text}",
            textfont=dict(size=10),
            colorbar=dict(title="% wallet", ticksuffix="%", len=0.85, thickness=14),
            hovertemplate="<b>%{y}</b> | %{x}<br>Return: %{z:+.2f}% of wallet<extra></extra>",
        ))
        fig_hm.update_layout(
            title="Monthly Returns Heatmap (% of $1,000 Wallet)",
            height=max(380, len(_syms_hm_full) * 40 + 130),
            plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
            font=dict(color="#e2e8f0"),
            xaxis=dict(tickangle=-30, side="top", gridcolor="#1e293b"),
            yaxis=dict(autorange="reversed"),
            margin=dict(l=110, r=90, t=90, b=30),
        )
        heatmap_html = fig_hm.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Summary table rows
    table_rows = ""
    for m in sorted_metrics:
        ret = m.get("Total Return %", 0)
        pf  = m.get("Profit Factor", 0)
        wr  = m.get("Win Rate %", 0)
        dd  = m.get("Max Drawdown %", 0)
        sh  = m.get("Sharpe Ratio", 0)
        n   = m.get("Number of Trades", 0)
        tf  = m.get("Timeframe", "")
        ct  = m.get("Candle Type", "")
        init_cap = m.get("Initial Capital", 0)  # == wallet ($1,000) — sizing reference
        fin_cap  = m.get("Final Capital", 0)
        pnl_usd  = fin_cap - init_cap            # coin's absolute P&L contribution
        # Wallet-contribution %: how much this coin moved the $1,000 wallet
        wallet_contrib_pct = (pnl_usd / wallet * 100) if wallet > 0 else 0

        ret_class    = "pos" if ret >= 0 else "neg"
        pnl_class    = "pos" if pnl_usd >= 0 else "neg"
        pf_class     = "pos" if pf >= 1 else "neg"
        contrib_class = "pos" if wallet_contrib_pct >= 0 else "neg"
        link = f'<a href="{m["Symbol"]}_{tf}_report.html" target="_blank">&#128202;</a>'

        pf_disp = "inf" if pf == float("inf") else f"{pf:.2f}"

        table_rows += f"""
        <tr>
            <td class="symbol">{m['Symbol']} {link}</td>
            <td>{tf} | {ct}</td>
            <td class="{ret_class}">{ret:+.2f}%</td>
            <td class="{pnl_class}">${pnl_usd:+,.2f}</td>
            <td class="{contrib_class}">{wallet_contrib_pct:+.2f}%</td>
            <td>{n}</td>
            <td>{wr:.1f}%</td>
            <td class="{pf_class}">{pf_disp}</td>
            <td>{dd:.1f}%</td>
            <td>{sh:.2f}</td>
        </tr>"""

    # Overall portfolio row
    all_pf_vals = [m.get("Profit Factor", 0) for m in all_metrics if m.get("Profit Factor", 0) != float("inf")]
    avg_pf = sum(all_pf_vals) / len(all_pf_vals) if all_pf_vals else 0
    avg_wr = sum(m.get("Win Rate %", 0) for m in all_metrics) / len(all_metrics)
    max_dd = max(m.get("Max Drawdown %", 0) for m in all_metrics)
    total_trades = sum(m.get("Number of Trades", 0) for m in all_metrics)

    portfolio_ret_class = "pos" if total_return_pct >= 0 else "neg"
    pnl_total = total_pnl  # sum of all coin P&Ls

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    data_start = min(m.get("Start Date", "N/A") for m in all_metrics)
    data_end   = max(m.get("End Date",   "N/A") for m in all_metrics)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Backtest Dashboard — Donchian Channel Strategy</title>
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
  /* ── Hero Header */
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
  /* ── KPI Cards */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
  .kpi-card.accent::after  {{ background: var(--accent); }}
  .kpi-card.pos::after     {{ background: var(--pos); }}
  .kpi-card.neg::after     {{ background: var(--neg); }}
  .kpi-card.warn::after    {{ background: var(--warn); }}
  .kpi-card.cyan::after    {{ background: var(--accent2); }}
  .kpi-label {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }}
  .kpi-value {{ font-size: 1.75rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
  .kpi-value.pos {{ color: var(--pos); }}
  .kpi-value.neg {{ color: var(--neg); }}
  .kpi-value.neutral {{ color: var(--text); }}
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
  /* ── Charts grid */
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
  /* ── Table */
  .table-wrapper {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }}
  thead tr {{
    border-bottom: 2px solid var(--border);
  }}
  thead th {{
    padding: 14px 16px;
    text-align: left;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    white-space: nowrap;
  }}
  tbody tr {{
    border-bottom: 1px solid var(--border);
    transition: background 0.15s;
  }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(99,102,241,0.05); }}
  tbody td {{ padding: 13px 16px; white-space: nowrap; }}
  .symbol {{ font-weight: 600; font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; }}
  .pos {{ color: var(--pos); font-weight: 500; }}
  .neg {{ color: var(--neg); font-weight: 500; }}
  .tfoot-row td {{
    padding: 14px 16px;
    font-weight: 700;
    background: rgba(99,102,241,0.08);
    border-top: 2px solid var(--accent);
    color: var(--text);
  }}
  a {{ color: var(--accent2); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  /* ── Insight cards */
  .insight-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 40px;
  }}
  .insight-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }}
  .insight-card h3 {{
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .insight-item {{
    display: flex;
    justify-content: space-between;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.875rem;
  }}
  .insight-item:last-child {{ border-bottom: none; }}
  .insight-val {{ font-family: 'JetBrains Mono', monospace; font-size: 0.82rem; }}
  /* ── Footer */
  footer {{
    text-align: center;
    padding: 24px;
    color: var(--muted);
    font-size: 0.75rem;
    border-top: 1px solid var(--border);
  }}
</style>
</head>
<body>

<!-- Hero -->
<div class="hero">
  <div class="hero-badge">🏦 Portfolio Backtest Report</div>
  <h1>Donchian Channel Strategy — Multi-Coin Portfolio</h1>
  <div class="hero-meta">
    <span>Generated: {run_date}</span>
    <span>Data period: {data_start} to {data_end}</span>
    <span>Shared wallet: ${wallet:,.0f}</span>
    <span>Risk/trade: 1.5% = ${wallet*0.015:,.0f} | Margin cap: 7% = ${wallet*0.07:,.0f}</span>
    <span>Strategy: donchian_channel (Heikin Ashi) | Coins: {len(all_metrics)}</span>
  </div>
</div>

<!-- KPI Cards -->
<div class="kpi-grid">
  <div class="kpi-card {'pos' if total_return_pct >= 0 else 'neg'}">
    <div class="kpi-label">Portfolio Return</div>
    <div class="kpi-value {'pos' if total_return_pct >= 0 else 'neg'}">{total_return_pct:+.2f}%</div>
    <div class="kpi-sub">${pnl_total:+,.2f} net P&L</div>
  </div>
  <div class="kpi-card {'pos' if total_final > wallet else 'neg'}">
    <div class="kpi-label">Final Portfolio Value</div>
    <div class="kpi-value neutral">${total_final:,.2f}</div>
    <div class="kpi-sub">Shared wallet started at ${wallet:,.0f}</div>
  </div>
  <div class="kpi-card accent">
    <div class="kpi-label">Total Trades</div>
    <div class="kpi-value neutral">{total_trades}</div>
    <div class="kpi-sub">Across {len(all_metrics)} coins</div>
  </div>
  <div class="kpi-card cyan">
    <div class="kpi-label">Avg Win Rate</div>
    <div class="kpi-value neutral">{avg_wr:.1f}%</div>
    <div class="kpi-sub">Portfolio average</div>
  </div>
  <div class="kpi-card warn">
    <div class="kpi-label">Avg Profit Factor</div>
    <div class="kpi-value neutral">{avg_pf:.2f}</div>
    <div class="kpi-sub">Portfolio average</div>
  </div>
  <div class="kpi-card neg">
    <div class="kpi-label">Worst Max Drawdown</div>
    <div class="kpi-value neg">-{max_dd:.1f}%</div>
    <div class="kpi-sub">Single-coin worst case</div>
  </div>
</div>

<!-- Charts row 1 -->
<div class="section">
  <div class="section-title">📊 Performance Overview</div>
  <div class="chart-grid-2">
    <div class="chart-box full">{equity_curve_html}</div>
    <div class="chart-box full">{heatmap_html}</div>
    <div class="chart-box full">{returns_html}</div>
    <div class="chart-box">{scatter_html}</div>
    <div class="chart-box">{alloc_html}</div>
    <div class="chart-box">{dd_html}</div>
    <div class="chart-box">{trades_html}</div>
  </div>
</div>

<!-- Insight cards -->
<div class="section">
  <div class="section-title">💡 Portfolio Insights</div>
  <div class="insight-grid">"""

    # Best / worst coin
    best  = sorted_metrics[0]
    worst = sorted_metrics[-1]
    most_trades  = max(all_metrics, key=lambda x: x.get("Number of Trades", 0))
    fewest_trades = min(all_metrics, key=lambda x: x.get("Number of Trades", 0))
    highest_pf = max(all_metrics, key=lambda x: min(x.get("Profit Factor", 0), 100))
    lowest_dd  = min(all_metrics, key=lambda x: x.get("Max Drawdown %", 0))
    highest_wr = max(all_metrics, key=lambda x: x.get("Win Rate %", 0))

    html += f"""
    <div class="insight-card">
      <h3>🏆 Best vs Worst</h3>
      <div class="insight-item"><span>Best Return</span> <span class="insight-val pos">{best['Symbol']} {best.get('Total Return %', 0):+.1f}%</span></div>
      <div class="insight-item"><span>Worst Return</span> <span class="insight-val neg">{worst['Symbol']} {worst.get('Total Return %', 0):+.1f}%</span></div>
      <div class="insight-item"><span>Highest Win Rate</span> <span class="insight-val pos">{highest_wr['Symbol']} {highest_wr.get('Win Rate %', 0):.1f}%</span></div>
      <div class="insight-item"><span>Lowest Drawdown</span> <span class="insight-val pos">{lowest_dd['Symbol']} -{lowest_dd.get('Max Drawdown %', 0):.1f}%</span></div>
    </div>
    <div class="insight-card">
      <h3>📈 Trading Activity</h3>
      <div class="insight-item"><span>Most Active</span> <span class="insight-val">{most_trades['Symbol']} ({most_trades.get('Number of Trades', 0)} trades)</span></div>
      <div class="insight-item"><span>Least Active</span> <span class="insight-val">{fewest_trades['Symbol']} ({fewest_trades.get('Number of Trades', 0)} trades)</span></div>
      <div class="insight-item"><span>Avg trades/coin</span> <span class="insight-val">{total_trades // len(all_metrics)}</span></div>
      <div class="insight-item"><span>Total signals fired</span> <span class="insight-val">{total_trades}</span></div>
    </div>
    <div class="insight-card">
      <h3>💎 Quality Metrics</h3>
      <div class="insight-item"><span>Best Profit Factor</span> <span class="insight-val pos">{highest_pf['Symbol']} {min(highest_pf.get('Profit Factor', 0), 100):.2f}</span></div>
      <div class="insight-item"><span>Avg Profit Factor</span> <span class="insight-val">{avg_pf:.2f}</span></div>
      <div class="insight-item"><span>Profitable coins</span> <span class="insight-val pos">{sum(1 for m in all_metrics if m.get('Total Return %', 0) > 0)}/{len(all_metrics)}</span></div>
      <div class="insight-item"><span>Avg Hold per Trade</span> <span class="insight-val">—</span></div>
    </div>
  </div>
</div>

<!-- Summary Table -->
<div class="section">
  <div class="section-title">📋 Detailed Results Table</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>Symbol</th>
          <th>TF / Candles</th>
          <th title="Return on coin-level equity (fractional sizing with $1,000 wallet)">Coin Return %</th>
          <th title="Absolute P&amp;L this coin contributed to the shared wallet">Net P&amp;L ($)</th>
          <th title="% of shared $1,000 wallet moved by this coin">Wallet Impact %</th>
          <th>Trades</th>
          <th>Win Rate</th>
          <th>Profit Factor</th>
          <th>Max DD</th>
          <th>Sharpe</th>
        </tr>
      </thead>
      <tbody>{table_rows}</tbody>
      <tfoot>
        <tr class="tfoot-row">
          <td>PORTFOLIO TOTAL</td>
          <td>{len(all_metrics)} coins | $1,000 wallet</td>
          <td>—</td>
          <td class="{'pos' if pnl_total >= 0 else 'neg'}">${pnl_total:+,.2f}</td>
          <td class="{'pos' if total_return_pct >= 0 else 'neg'}">{total_return_pct:+.2f}%</td>
          <td>{total_trades}</td>
          <td>{avg_wr:.1f}%</td>
          <td>{avg_pf:.2f}</td>
          <td>-{max_dd:.1f}%</td>
          <td>—</td>
        </tr>
      </tfoot>
    </table>
  </div>
</div>

<footer>
  Delta Exchange Algo · Donchian Channel Portfolio Backtest · {run_date}
</footer>
</body>
</html>"""

    out_path = reports_dir / "portfolio_dashboard.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Portfolio Backtest — multi_coin donchian_channel")
    parser.add_argument("--data-folder", type=str, default=None,
                        help="Root folder containing delta_crypto_data_XH subdirectories")
    parser.add_argument("--capital", type=float, default=INITIAL_PORTFOLIO_CAPITAL,
                        help=f"Total portfolio capital in USD (default: {INITIAL_PORTFOLIO_CAPITAL})")
    parser.add_argument("--reports-dir", type=str, default="reports/portfolio",
                        help="Output directory for HTML reports (default: reports/portfolio)")
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

    config = get_config()
    data_root = args.data_folder or r"D:\Workspace\crypto-backtest-data"

    total_capital = args.capital
    # LIVE-ACCURATE: every coin sizes against the FULL wallet, not a split.
    # risk/trade = 1.5% x $1,000 = $15  |  margin cap = 7% x $1,000 = $70
    per_coin_capital = total_capital  # <-- shared wallet reference
    logger.info(
        f"Portfolio: {len(PORTFOLIO)} coins | Shared wallet: ${total_capital:,.0f} | "
        f"Risk/trade: ${total_capital * 0.015:,.2f} (1.5%) | "
        f"Margin cap/trade: ${total_capital * 0.07:,.2f} (7%)"
    )

    reporter = Reporter(reports_dir=args.reports_dir)
    all_metrics = []

    for i, coin_cfg in enumerate(PORTFOLIO, 1):
        sym = coin_cfg["symbol"]
        tf  = coin_cfg["timeframe"]
        logger.info(f"[{i}/{len(PORTFOLIO)}] Backtesting {sym} ({tf})...")
        try:
            metrics = run_single_coin(
                coin_cfg=coin_cfg,
                data_root=data_root,
                reporter=reporter,
                per_coin_capital=per_coin_capital,
            )
            if metrics:
                all_metrics.append(metrics)
        except Exception as e:
            logger.error(f"[{sym}] Backtest failed: {e}", exc_info=True)

    if not all_metrics:
        logger.error("No successful backtests. Exiting.")
        sys.exit(1)

    logger.info("Generating portfolio dashboard...")
    dash_path = generate_portfolio_dashboard(all_metrics, reporter.reports_dir, wallet=total_capital)
    logger.info(f"Portfolio dashboard: {dash_path.resolve()}")

    # -- Terminal summary (live-accurate: shared wallet model)
    sorted_metrics = sorted(all_metrics, key=lambda x: x.get("Total Return %", 0), reverse=True)
    coin_pnls      = [m["Final Capital"] - m["Initial Capital"] for m in all_metrics]
    total_pnl      = sum(coin_pnls)
    total_initial  = total_capital           # single shared wallet
    total_final    = total_capital + total_pnl
    total_return_pct = (total_pnl / total_capital * 100) if total_capital > 0 else 0

    print("\n" + "=" * 120)
    print(f"  {'LIVE-ACCURATE PORTFOLIO BACKTEST - Donchian Channel | Shared $1,000 Wallet':^116}")
    print(f"  {'Risk/trade: 1.5% = $15  |  Margin cap: 7% = $70  |  Leverage: 5x  |  Heikin Ashi':^116}")
    print("=" * 120)
    print(f"  {'Symbol':<14} {'TF':<5} {'CoinReturn'::>11} {'Net P&L'::>10} {'WalletImpact'::>13} {'Trades':>7} {'Win%':>7} {'PF':>7} {'MaxDD':>8} {'Sharpe':>7}")
    print("-" * 120)
    for m in sorted_metrics:
        sym = m["Symbol"]
        tf  = m.get("Timeframe", "")
        fc  = m.get("Final Capital", 0)
        ic  = m.get("Initial Capital", 0)
        pnl = fc - ic
        wallet_impact = pnl / total_capital * 100
        ret = m.get("Total Return %", 0)
        n   = m.get("Number of Trades", 0)
        wr  = m.get("Win Rate %", 0)
        pf  = m.get("Profit Factor", 0)
        dd  = m.get("Max Drawdown %", 0)
        sh  = m.get("Sharpe Ratio", 0)
        pf_disp = "  inf" if pf == float("inf") else f"{pf:7.2f}"
        print(f"  {sym:<14} {tf:<5} {ret:+11.2f}%  ${pnl:+9,.2f}  {wallet_impact:+12.2f}%  {n:>7} {wr:>6.1f}% {pf_disp} {dd:>7.1f}% {sh:>7.2f}")
    print("-" * 120)
    sign = "+" if total_return_pct >= 0 else ""
    print(f"  {'WALLET: $1,000 -> $'+f'{total_final:,.2f}':<55} Net P&L: ${total_pnl:+,.2f}  Portfolio Return: {sign}{total_return_pct:.2f}%")
    print("=" * 120)
    print(f"\n  [Folder] Individual reports : {Path(args.reports_dir).resolve()}")
    print(f"  [Chart] Portfolio dashboard: {dash_path.resolve()}")
    print()


if __name__ == "__main__":
    main()
