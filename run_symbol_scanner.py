"""
Full-Universe Symbol Scanner — Donchian Channel Strategy
=========================================================
Tests every symbol × timeframe in the data folder (past 1 year).
Uses the SAME live-accurate sizing as run_portfolio_backtest.py:
  • Shared $1,000 wallet
  • Fractional sizing: risk = 1.5% × $1,000 = $15/trade
  • Margin cap = 7% × $1,000 = $70/trade

Ranks by Composite Score and produces a recommendation report.

Usage:
    python run_symbol_scanner.py
    python run_symbol_scanner.py --capital 1000 --top-n 20
"""

import argparse
import sys
import time
import warnings
from pathlib import Path
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

import pandas as pd

# ── Project root on path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import get_config
from core.logger import setup_logging, get_logger
from backtest.engine import BacktestEngine
from backtest.data_loader import DataLoader
from backtest.metrics import calculate_metrics
from strategies.donchian_strategy import DonchianChannelStrategy

# ─────────────────────────────────────────────────────────────
STRATEGY_NAME   = "donchian_channel"
DATA_ROOT       = r"D:\Workspace\crypto-backtest-data"
WALLET          = 1000.0       # shared portfolio wallet ($)
LEVERAGE        = 5
CANDLE_TYPE     = "heikin_ashi"
TIMEFRAMES      = ["1h", "2h", "4h", "6h"]
MIN_TRADES      = 20           # discard symbols with too few trades
MIN_BARS        = 500          # discard datasets shorter than this after 1-yr filter
HEIKIN_TFS      = ["1h", "2h", "4h", "6h"]   # all use Heikin Ashi

TF_TO_SUBFOLDER = {
    "1h": "delta_crypto_data_1H",
    "2h": "delta_crypto_data_2H",
    "4h": "delta_crypto_data_4H",
    "6h": "delta_crypto_data_6H",
}

# Composite score weights (higher = better symbol)
SCORE_WEIGHTS = {
    "sharpe":      0.30,   # risk-adjusted return
    "profit_factor": 0.25, # profit vs loss ratio
    "win_rate":    0.15,   # % of trades profitable
    "return":      0.20,   # raw return on wallet
    "drawdown":   -0.10,   # penalise drawdown
}

# ─────────────────────────────────────────────────────────────
# Current portfolio (for comparison table)
CURRENT_PORTFOLIO = [
    ("PIPPINUSD", "1h"), ("SNDKBUSD", "1h"), ("SKYAIUSD", "1h"), ("RIVERUSD", "1h"), ("BEATUSD", "1h"),
    ("HUSD", "2h"), ("EVAAUSD", "2h"), ("ZECUSD", "2h"), ("PIUSD", "2h"),
    ("DEEPUSD", "4h"),
]

def find_csv(data_root: str, symbol: str, timeframe: str) -> Path | None:
    sub = TF_TO_SUBFOLDER.get(timeframe)
    if sub:
        p = Path(data_root) / sub / f"{symbol}_{timeframe}.csv"
        if p.exists():
            return p
    p = Path(data_root) / f"{symbol}_{timeframe}.csv"
    return p if p.exists() else None


def apply_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    ha = df.copy()
    ha["close"] = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    ha_open = [(df["open"].iloc[0] + df["close"].iloc[0]) / 2]
    for i in range(1, len(df)):
        ha_open.append((ha_open[-1] + ha["close"].iloc[i - 1]) / 2)
    ha["open"]  = ha_open
    ha["high"]  = df[["high", "open", "close"]].max(axis=1)
    ha["low"]   = df[["low",  "open", "close"]].min(axis=1)
    return ha


def compute_score(r: dict) -> float:
    """Composite score — higher is better."""
    sh  = min(r.get("Sharpe Ratio", 0), 10)        # cap at 10
    pf  = min(r.get("Profit Factor", 0), 10)        # cap at 10
    wr  = r.get("Win Rate %", 0) / 100              # 0–1
    ret = r.get("Total Return %", 0) / 100          # normalised
    dd  = r.get("Max Drawdown %", 0) / 100          # 0–1 (penalised)
    score = (
        SCORE_WEIGHTS["sharpe"]        * sh +
        SCORE_WEIGHTS["profit_factor"] * pf +
        SCORE_WEIGHTS["win_rate"]      * wr * 10 +   # scale to ~same range as PF/Sharpe
        SCORE_WEIGHTS["return"]        * ret * 5 +   # scale
        SCORE_WEIGHTS["drawdown"]      * dd * 10     # negative weight
    )
    return round(score, 4)


def backtest_one(symbol: str, timeframe: str, data_root: str,
                 wallet: float, logger) -> dict | None:
    """Backtest a single symbol/timeframe. Returns metrics dict or None."""
    csv_path = find_csv(data_root, symbol, timeframe)
    if csv_path is None:
        return None

    loader = DataLoader(str(csv_path.parent))
    try:
        df = loader.load_data(csv_path)
    except Exception:
        return None

    if df.empty:
        return None

    # Filter to past 1 year
    now_ts = int(time.time())
    df = df[df["time"] >= now_ts - 365 * 24 * 3600].reset_index(drop=True)
    if len(df) < MIN_BARS:
        return None

    # Heikin Ashi
    if timeframe in HEIKIN_TFS:
        df = apply_heikin_ashi(df)

    strategy = DonchianChannelStrategy()
    strategy.timeframe = timeframe
    if hasattr(strategy, "_update_bars_per_day"):
        strategy._update_bars_per_day(timeframe)
    strategy.leverage = LEVERAGE

    # Set engine capital = full wallet (live-accurate fractional sizing)
    cfg = get_config()
    _orig = cfg.backtesting.initial_capital
    cfg.backtesting.initial_capital = wallet
    try:
        engine = BacktestEngine(strategy, symbol, timeframe, STRATEGY_NAME, leverage=LEVERAGE)
        engine.initial_capital = wallet
        engine.equity = wallet
        trades, equity_df = engine.run(df)
    except Exception as e:
        logger.debug(f"[{symbol}/{timeframe}] Engine error: {e}")
        return None
    finally:
        cfg.backtesting.initial_capital = _orig

    if len(trades) < MIN_TRADES:
        return None

    metrics = calculate_metrics(
        strategy_name=STRATEGY_NAME,
        initial_capital=wallet,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df,
        data_df=df,
    )
    metrics["Symbol"]    = symbol
    metrics["Timeframe"] = timeframe
    metrics["Bars"]      = len(df)
    metrics["Score"]     = compute_score(metrics)
    metrics["Wallet PnL $"] = engine.equity - wallet
    metrics["Wallet Impact %"] = (engine.equity - wallet) / wallet * 100
    return metrics


# ─────────────────────────────────────────────────────────────
def generate_report(all_results: list[dict], top_n: int, wallet: float, out_dir: Path):
    """Generate an HTML ranking report."""
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots

    # Best result per symbol (highest score across timeframes)
    best_by_symbol: dict[str, dict] = {}
    for r in all_results:
        sym = r["Symbol"]
        if sym not in best_by_symbol or r["Score"] > best_by_symbol[sym]["Score"]:
            best_by_symbol[sym] = r

    ranked = sorted(best_by_symbol.values(), key=lambda x: x["Score"], reverse=True)
    top    = ranked[:top_n]

    # Current portfolio scores (best TF already in all_results)
    current_syms = {s for s, _ in CURRENT_PORTFOLIO}
    current_rows = [r for r in ranked if r["Symbol"] in current_syms]

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── Chart 1: Top-N Score bar
    fig_score = go.Figure(go.Bar(
        x=[r["Symbol"] for r in top],
        y=[r["Score"] for r in top],
        marker=dict(
            color=[r["Score"] for r in top],
            colorscale="Viridis", showscale=True,
            colorbar=dict(title="Score"),
        ),
        text=[f"{r['Score']:.2f}" for r in top],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Score: %{y:.3f}<extra></extra>",
    ))
    fig_score.update_layout(
        title=f"Top {top_n} Symbols — Composite Score (Donchian Channel, past 1 year)",
        height=420, plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(tickangle=-35, gridcolor="#1e293b"),
        yaxis=dict(gridcolor="#1e293b"),
        margin=dict(l=50, r=30, t=55, b=100),
    )
    score_html = fig_score.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 2: Sharpe vs Profit Factor bubble (size = return)
    fig_bubble = go.Figure(go.Scatter(
        x=[r.get("Win Rate %", 0) for r in top],
        y=[min(r.get("Profit Factor", 0), 10) for r in top],
        mode="markers+text",
        text=[r["Symbol"] for r in top],
        textposition="top center",
        marker=dict(
            size=[max(abs(r.get("Total Return %", 1)), 5) ** 0.5 * 5 for r in top],
            color=[r.get("Sharpe Ratio", 0) for r in top],
            colorscale="RdYlGn", showscale=True,
            colorbar=dict(title="Sharpe"),
            line=dict(width=1, color="#334155"),
        ),
        hovertemplate=(
            "<b>%{text}</b><br>Win Rate: %{x:.1f}%<br>"
            "Profit Factor: %{y:.2f}<extra></extra>"
        ),
    ))
    fig_bubble.add_hline(y=1, line_dash="dash", line_color="#64748b",
                         annotation_text="PF=1 (breakeven)")
    fig_bubble.update_layout(
        title="Win Rate vs Profit Factor (bubble=Return%, color=Sharpe)",
        height=420, plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(title="Win Rate %", gridcolor="#1e293b"),
        yaxis=dict(title="Profit Factor", gridcolor="#1e293b"),
        margin=dict(l=60, r=30, t=55, b=60),
    )
    bubble_html = fig_bubble.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 3: Return % bar (top N)
    fig_ret = go.Figure(go.Bar(
        x=[r["Symbol"] for r in top],
        y=[r.get("Wallet Impact %", 0) for r in top],
        marker_color=["#22c55e" if r.get("Wallet Impact %", 0) >= 0 else "#ef4444" for r in top],
        text=[f"{r.get('Wallet Impact %', 0):+.1f}%" for r in top],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Wallet Impact: %{y:+.2f}%<extra></extra>",
    ))
    fig_ret.update_layout(
        title=f"Wallet P&L Impact % — Top {top_n} (shared $1,000 wallet)",
        height=400, plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(tickangle=-35, gridcolor="#1e293b"),
        yaxis=dict(gridcolor="#1e293b", zeroline=True, zerolinecolor="#475569"),
        margin=dict(l=60, r=30, t=55, b=100),
    )
    ret_html = fig_ret.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Chart 4: Max Drawdown (top N)
    fig_dd = go.Figure(go.Bar(
        x=[r["Symbol"] for r in top],
        y=[-r.get("Max Drawdown %", 0) for r in top],
        marker_color="#e74c3c",
        text=[f"-{r.get('Max Drawdown %', 0):.1f}%" for r in top],
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>Max DD: %{y:.2f}%<extra></extra>",
    ))
    fig_dd.update_layout(
        title="Max Drawdown % — Top Symbols",
        height=400, plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
        font=dict(color="#e2e8f0"),
        xaxis=dict(tickangle=-35, gridcolor="#1e293b"),
        yaxis=dict(gridcolor="#1e293b"),
        margin=dict(l=60, r=30, t=55, b=100),
    )
    dd_html = fig_dd.to_html(full_html=False, include_plotlyjs="cdn")

    # ── Build HTML table rows (full ranked list)
    def row_html(r: dict, rank: int, is_current: bool) -> str:
        sym   = r["Symbol"]
        tf    = r["Timeframe"]
        sc    = r["Score"]
        ret   = r.get("Wallet Impact %", 0)
        pnl   = r.get("Wallet PnL $", 0)
        wr    = r.get("Win Rate %", 0)
        pf    = r.get("Profit Factor", 0)
        dd    = r.get("Max Drawdown %", 0)
        sh    = r.get("Sharpe Ratio", 0)
        n     = r.get("Number of Trades", 0)
        pf_d  = "inf" if pf == float("inf") else f"{pf:.2f}"
        rc    = "pos" if ret >= 0 else "neg"
        curr  = " current" if is_current else ""
        medal = "&#127941;" if rank == 1 else ("&#129352;" if rank == 2 else ("&#129353;" if rank == 3 else ""))
        return f"""
        <tr class="{curr}">
          <td class="rank">{medal} #{rank}</td>
          <td class="symbol">{sym}</td>
          <td>{tf}</td>
          <td class="score">{sc:.3f}</td>
          <td class="{rc}">{ret:+.1f}%</td>
          <td class="{rc}">${pnl:+,.2f}</td>
          <td>{n}</td>
          <td>{wr:.1f}%</td>
          <td class="{'pos' if pf >= 1 else 'neg'}">{pf_d}</td>
          <td>{dd:.1f}%</td>
          <td>{sh:.2f}</td>
        </tr>"""

    full_table = ""
    for i, r in enumerate(ranked[:60], 1):  # show top-60
        is_curr = r["Symbol"] in current_syms
        full_table += row_html(r, i, is_curr)

    # Recommended top-N summary cards
    recommendation_cards = ""
    for i, r in enumerate(top, 1):
        sym = r["Symbol"]
        in_current = sym in current_syms
        badge_html = '<span class="badge-new">NEW</span>' if not in_current else '<span class="badge-keep">IN PORTFOLIO</span>'
        recommendation_cards += f"""
        <div class="rec-card">
          <div class="rec-rank">#{i}</div>
          <div class="rec-sym">{sym} {badge_html}</div>
          <div class="rec-tf">{r['Timeframe']} | Heikin Ashi | Leverage 5×</div>
          <div class="rec-metrics">
            <span class="metric pos">&#9650; {r.get('Wallet Impact %', 0):+.1f}%</span>
            <span class="metric">PF {min(r.get('Profit Factor',0),10):.2f}</span>
            <span class="metric">WR {r.get('Win Rate %',0):.1f}%</span>
            <span class="metric">DD -{r.get('Max Drawdown %',0):.1f}%</span>
            <span class="metric">Sharpe {r.get('Sharpe Ratio',0):.2f}</span>
          </div>
          <div class="rec-score">Score: {r['Score']:.3f}</div>
        </div>"""

    # Stats
    tested_count = len(best_by_symbol)
    pass_count   = len([r for r in ranked if r.get("Wallet Impact %", 0) > 0])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Symbol Scanner — Donchian Channel | {run_date}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0f1e; --surface: #111827; --border: #1e293b;
    --accent: #6366f1; --accent2: #22d3ee;
    --text: #e2e8f0; --muted: #94a3b8;
    --pos: #22c55e; --neg: #ef4444; --warn: #f59e0b;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

  /* Hero */
  .hero {{
    background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 55%, #0f172a 100%);
    border-bottom: 1px solid var(--border);
    padding: 44px 60px 36px; position: relative; overflow: hidden;
  }}
  .hero::before {{
    content: ''; position: absolute; top: -80px; right: -80px;
    width: 340px; height: 340px; border-radius: 50%;
    background: radial-gradient(circle, rgba(99,102,241,0.18) 0%, transparent 70%);
  }}
  .hero-badge {{
    display: inline-block; background: rgba(99,102,241,0.14);
    border: 1px solid rgba(99,102,241,0.4); border-radius: 20px;
    padding: 4px 14px; font-size: 0.72rem; color: #a5b4fc;
    letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 14px;
  }}
  .hero h1 {{
    font-size: 2.1rem; font-weight: 700;
    background: linear-gradient(135deg, #e2e8f0, #a5b4fc);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
  }}
  .hero-meta {{ color: var(--muted); font-size: 0.85rem; display: flex; gap: 24px; flex-wrap: wrap; margin-top: 14px; }}

  /* KPI */
  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 16px; padding: 32px 60px; background: var(--bg);
  }}
  .kpi-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px; position: relative; overflow: hidden;
    transition: transform 0.2s, border-color 0.2s;
  }}
  .kpi-card:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
  .kpi-card::after {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    border-radius: 12px 12px 0 0;
  }}
  .kpi-card.accent::after {{ background: var(--accent); }}
  .kpi-card.pos::after {{ background: var(--pos); }}
  .kpi-card.cyan::after {{ background: var(--accent2); }}
  .kpi-card.warn::after {{ background: var(--warn); }}
  .kpi-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }}
  .kpi-value {{ font-size: 1.65rem; font-weight: 700; font-family: 'JetBrains Mono', monospace; }}
  .kpi-value.pos {{ color: var(--pos); }}
  .kpi-value.neutral {{ color: var(--text); }}
  .kpi-sub {{ font-size: 0.76rem; color: var(--muted); margin-top: 4px; }}

  /* Section */
  .section {{ padding: 0 60px 40px; }}
  .section-title {{
    font-size: 1.05rem; font-weight: 600; color: var(--text);
    margin-bottom: 18px; display: flex; align-items: center; gap: 10px;
  }}
  .section-title::after {{ content: ''; flex: 1; height: 1px; background: var(--border); }}

  /* Charts */
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }}
  .chart-box {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 4px; overflow: hidden;
  }}
  .chart-box.full {{ grid-column: 1 / -1; }}

  /* Recommendation cards */
  .rec-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-bottom: 40px; }}
  .rec-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 20px;
    transition: transform 0.2s, border-color 0.2s;
    position: relative; overflow: hidden;
  }}
  .rec-card:hover {{ transform: translateY(-3px); border-color: var(--accent); }}
  .rec-rank {{ font-size: 1.4rem; font-weight: 700; color: var(--accent); margin-bottom: 4px; }}
  .rec-sym {{ font-size: 1.05rem; font-weight: 600; font-family: 'JetBrains Mono', monospace; margin-bottom: 4px; display: flex; align-items: center; gap: 8px; }}
  .rec-tf {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 12px; }}
  .rec-metrics {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
  .metric {{ font-size: 0.75rem; background: rgba(99,102,241,0.1); border: 1px solid rgba(99,102,241,0.2); border-radius: 6px; padding: 3px 8px; font-family: 'JetBrains Mono', monospace; }}
  .metric.pos {{ color: var(--pos); }}
  .rec-score {{ font-size: 0.8rem; color: var(--muted); }}
  .badge-new {{ background: rgba(34,197,94,0.15); border: 1px solid rgba(34,197,94,0.4); color: var(--pos); border-radius: 10px; padding: 2px 8px; font-size: 0.65rem; font-weight: 600; letter-spacing: 0.06em; }}
  .badge-keep {{ background: rgba(99,102,241,0.15); border: 1px solid rgba(99,102,241,0.4); color: #a5b4fc; border-radius: 10px; padding: 2px 8px; font-size: 0.65rem; font-weight: 600; letter-spacing: 0.06em; }}

  /* Table */
  .table-wrapper {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; }}
  thead tr {{ border-bottom: 2px solid var(--border); }}
  thead th {{ padding: 12px 14px; text-align: left; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); white-space: nowrap; }}
  tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.15s; }}
  tbody tr.current {{ background: rgba(99,102,241,0.06); }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(99,102,241,0.08); }}
  tbody td {{ padding: 11px 14px; white-space: nowrap; }}
  .rank {{ font-weight: 700; font-size: 0.78rem; }}
  .symbol {{ font-weight: 600; font-family: 'JetBrains Mono', monospace; }}
  .score {{ font-weight: 700; color: var(--accent2); font-family: 'JetBrains Mono', monospace; }}
  .pos {{ color: var(--pos); font-weight: 500; }}
  .neg {{ color: var(--neg); font-weight: 500; }}

  footer {{ text-align: center; padding: 24px; color: var(--muted); font-size: 0.72rem; border-top: 1px solid var(--border); }}
  a {{ color: var(--accent2); text-decoration: none; }}
</style>
</head>
<body>

<div class="hero">
  <div class="hero-badge">&#128269; Universe Scanner</div>
  <h1>Donchian Channel — Full Symbol Ranking</h1>
  <div class="hero-meta">
    <span>Generated: {run_date}</span>
    <span>Universe: {tested_count} symbols tested</span>
    <span>Profitable: {pass_count}/{tested_count} symbols</span>
    <span>Wallet: ${wallet:,.0f} | Risk/trade: 1.5% = ${wallet*0.015:,.0f} | Cap: 7% = ${wallet*0.07:,.0f}</span>
    <span>Top {top_n} recommended below (highlighted in table = current portfolio)</span>
  </div>
</div>

<!-- KPI -->
<div class="kpi-grid">
  <div class="kpi-card accent">
    <div class="kpi-label">Symbols Tested</div>
    <div class="kpi-value neutral">{tested_count}</div>
    <div class="kpi-sub">Across 4 timeframes</div>
  </div>
  <div class="kpi-card pos">
    <div class="kpi-label">Profitable Symbols</div>
    <div class="kpi-value pos">{pass_count}</div>
    <div class="kpi-sub">{pass_count/tested_count*100:.1f}% pass rate</div>
  </div>
  <div class="kpi-card cyan">
    <div class="kpi-label">Best Score</div>
    <div class="kpi-value neutral">{ranked[0]['Score']:.3f}</div>
    <div class="kpi-sub">{ranked[0]['Symbol']} ({ranked[0]['Timeframe']})</div>
  </div>
  <div class="kpi-card warn">
    <div class="kpi-label">Best Wallet Impact</div>
    <div class="kpi-value pos">+{max(r.get('Wallet Impact %',0) for r in ranked):.1f}%</div>
    <div class="kpi-sub">{max(ranked, key=lambda x: x.get('Wallet Impact %',0))['Symbol']}</div>
  </div>
  <div class="kpi-card accent">
    <div class="kpi-label">Avg Sharpe (top {top_n})</div>
    <div class="kpi-value neutral">{sum(r.get('Sharpe Ratio',0) for r in top)/len(top):.2f}</div>
    <div class="kpi-sub">Top {top_n} average</div>
  </div>
  <div class="kpi-card cyan">
    <div class="kpi-label">Avg Profit Factor (top {top_n})</div>
    <div class="kpi-value neutral">{sum(min(r.get('Profit Factor',0),10) for r in top)/len(top):.2f}</div>
    <div class="kpi-sub">Top {top_n} average</div>
  </div>
</div>

<!-- Charts -->
<div class="section">
  <div class="section-title">&#128200; Rankings Overview</div>
  <div class="chart-grid">
    <div class="chart-box full">{score_html}</div>
    <div class="chart-box full">{ret_html}</div>
    <div class="chart-box">{bubble_html}</div>
    <div class="chart-box">{dd_html}</div>
  </div>
</div>

<!-- Recommendations -->
<div class="section">
  <div class="section-title">&#11088; Top {top_n} Recommended Portfolio Coins</div>
  <div class="rec-grid">{recommendation_cards}</div>
</div>

<!-- Full Ranking Table -->
<div class="section">
  <div class="section-title">&#128203; Full Ranking Table (top 60 shown | highlighted = current portfolio)</div>
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          <th>Rank</th><th>Symbol</th><th>Best TF</th>
          <th title="Composite score: Sharpe×0.30 + PF×0.25 + WR×0.15 + Return×0.20 - DD×0.10">Score &#9432;</th>
          <th>Wallet Impact</th><th>Net P&amp;L</th>
          <th>Trades</th><th>Win Rate</th>
          <th>Profit Factor</th><th>Max DD</th><th>Sharpe</th>
        </tr>
      </thead>
      <tbody>{full_table}</tbody>
    </table>
  </div>
</div>

<footer>Delta Exchange Algo · Donchian Channel Symbol Scanner · {run_date}</footer>
</body>
</html>"""

    out_path = out_dir / "symbol_scanner_report.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path, ranked


# ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-folder", default=DATA_ROOT)
    parser.add_argument("--capital", type=float, default=WALLET)
    parser.add_argument("--top-n", type=int, default=15)
    parser.add_argument("--out-dir", default="reports/scanner")
    args = parser.parse_args()

    setup_logging(log_level="WARNING")   # quiet — progress via print
    logger = get_logger(__name__)

    wallet   = args.capital
    data_root = args.data_folder
    out_dir  = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Discover all symbols
    symbols_set = set()
    for sub in TF_TO_SUBFOLDER.values():
        sub_path = Path(data_root) / sub
        if sub_path.exists():
            for f in sub_path.iterdir():
                if f.suffix == ".csv":
                    sym = f.stem.rsplit("_", 1)[0]
                    symbols_set.add(sym)
    symbols = sorted(symbols_set)

    total_combos = len(symbols) * len(TIMEFRAMES)
    print(f"\n{'='*72}")
    print(f"  Donchian Channel Symbol Scanner  —  {len(symbols)} symbols × {len(TIMEFRAMES)} TFs = {total_combos} backtests")
    print(f"  Wallet: ${wallet:,.0f} | Risk/trade: ${wallet*0.015:,.2f} | Cap: ${wallet*0.07:,.2f}")
    print(f"{'='*72}")

    all_results = []
    done = 0
    failed = 0
    skipped = 0

    for sym in symbols:
        sym_results = []
        for tf in TIMEFRAMES:
            try:
                r = backtest_one(sym, tf, data_root, wallet, logger)
                if r is None:
                    skipped += 1
                else:
                    sym_results.append(r)
                    all_results.append(r)
            except Exception as e:
                failed += 1
            done += 1

        # Progress every 10 symbols
        if len([s for s in symbols if s <= sym]) % 10 == 0 or sym == symbols[-1]:
            tested_syms = len({r["Symbol"] for r in all_results})
            pct = done / total_combos * 100
            best_so_far = ""
            if all_results:
                _best_by_sym = {}
                for r in all_results:
                    if r["Symbol"] not in _best_by_sym or r["Score"] > _best_by_sym[r["Symbol"]]["Score"]:
                        _best_by_sym[r["Symbol"]] = r
                _top1 = max(_best_by_sym.values(), key=lambda x: x["Score"])
                best_so_far = f"  Best so far: {_top1['Symbol']} ({_top1['Timeframe']}) score={_top1['Score']:.3f}"
            print(f"  [{pct:5.1f}%] {done}/{total_combos} combos | {tested_syms} symbols | skip={skipped} fail={failed}{best_so_far}")

    print(f"\n  Done! {len(all_results)} valid results from {len({r['Symbol'] for r in all_results})} symbols.")
    print(f"  Generating report (top {args.top_n})...")

    out_path, ranked = generate_report(all_results, args.top_n, wallet, out_dir)

    # ── Terminal summary
    best_by_symbol: dict[str, dict] = {}
    for r in all_results:
        sym = r["Symbol"]
        if sym not in best_by_symbol or r["Score"] > best_by_symbol[sym]["Score"]:
            best_by_symbol[sym] = r
    ranked_list = sorted(best_by_symbol.values(), key=lambda x: x["Score"], reverse=True)

    current_syms = {s for s, _ in CURRENT_PORTFOLIO}

    print(f"\n{'='*120}")
    print(f"  {'TOP SYMBOLS — Donchian Channel | Score = Sharpe*0.30 + PF*0.25 + WR*0.15 + Return*0.20 - DD*0.10':^116}")
    print(f"{'='*120}")
    print(f"  {'#':<4} {'Symbol':<16} {'TF':<5} {'Score':>7} {'WalletImpact':>13} {'Net PnL':>10} {'Trades':>7} {'WR%':>6} {'PF':>6} {'MaxDD':>7} {'Sharpe':>7}  Status")
    print(f"  {'-'*116}")
    for i, r in enumerate(ranked_list[:args.top_n], 1):
        sym     = r["Symbol"]
        tf      = r["Timeframe"]
        sc      = r["Score"]
        wi      = r.get("Wallet Impact %", 0)
        pnl     = r.get("Wallet PnL $", 0)
        n       = r.get("Number of Trades", 0)
        wr      = r.get("Win Rate %", 0)
        pf      = r.get("Profit Factor", 0)
        dd      = r.get("Max Drawdown %", 0)
        sh      = r.get("Sharpe Ratio", 0)
        pf_d    = "  inf" if pf == float("inf") else f"{pf:6.2f}"
        status  = "[KEEP]" if sym in current_syms else "[ NEW]"
        print(f"  {i:<4} {sym:<16} {tf:<5} {sc:>7.3f}  {wi:>+12.1f}%  ${pnl:>+8,.2f}  {n:>7} {wr:>5.1f}% {pf_d} {dd:>6.1f}% {sh:>7.2f}  {status}")

    print(f"\n  Current portfolio symbols and their rank:")
    for sym, tf in CURRENT_PORTFOLIO:
        r = best_by_symbol.get(sym)
        if r:
            rank = next((i for i, x in enumerate(ranked_list, 1) if x["Symbol"] == sym), "N/A")
            print(f"    #{rank:>3}  {sym:<16} {r['Timeframe']:<5} score={r['Score']:.3f}  "
                  f"return={r.get('Wallet Impact %',0):+.1f}%  sharpe={r.get('Sharpe Ratio',0):.2f}")
    print(f"{'='*120}")
    print(f"\n  Report: {out_path.resolve()}")
    print()


if __name__ == "__main__":
    main()
