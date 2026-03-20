import os
from pathlib import Path
from typing import List, Dict, Any
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.logger import get_logger

logger = get_logger(__name__)

class Reporter:
    """Generates HTML reports for backtest results."""
    
    def __init__(self, reports_dir: str = "reports"):
        """Initialize Reporter with output directory."""
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        # Clear existing reports
        for file in self.reports_dir.glob("*"):
            if file.is_file() and file.suffix in [".html", ".csv"]:
                try:
                    file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete old report file {file}: {e}")
        
        # Create a simple default template if one doesn't exist
        self.templates_dir = Path("backtest/templates")
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_template_exists()
        
        self.env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )
        
    def _ensure_template_exists(self):
        """Create a default Jinja2 template if it doesn't exist."""
        template_path = self.templates_dir / "report_template.html"
        if not template_path.exists():
            default_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report - {{ symbol }}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 20px; color: #333; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1, h2 { color: #2c3e50; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 30px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #f8f9fa; font-weight: 600; }
        tr:hover { background-color: #f1f1f1; }
        .chart-container { margin-bottom: 40px; }
        .success { color: #28a745; }
        .danger { color: #dc3545; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid #007bff; }
        .stat-title { font-size: 0.9em; color: #6c757d; margin-bottom: 5px; text-transform: uppercase; }
        .stat-value { font-size: 1.4em; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Backtest Report: {{ symbol }} ({{ timeframe }})</h1>
        
        <h2>Performance Summary</h2>
        <div class="summary-grid">
            {% for key, value in metrics.items() %}
            <div class="stat-card">
                <div class="stat-title">{{ key }}</div>
                <div class="stat-value">
                    {% if value is number %}
                        {% if 'Ratio' in key or 'Factor' in key %}
                            {{ "%.2f"|format(value) }}
                        {% elif '%' in key %}
                            <span class="{{ 'success' if value > 0 else 'danger' if value < 0 else '' }}">{{ "%.2f"|format(value) }}%</span>
                        {% elif 'Capital' in key or 'Win' in key or 'Loss' in key %}
                            {{ "%.2f"|format(value) }}
                        {% else %}
                            {{ value }}
                        {% endif %}
                    {% else %}
                        {{ value }}
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        
        <h2>Charts</h2>
        <div class="chart-container">
            {{ chart_html | safe }}
        </div>
        
        <h2>Trade List</h2>
        <table>
            <thead>
                <tr>
                    <th>Entry Time</th>
                    <th>Exit Time</th>
                    <th>Type</th>
                    <th>Exit Type</th>
                    <th>Size</th>
                    <th>Entry Price</th>
                    <th>Exit Price</th>
                    <th>PnL</th>
                    <th>Return %</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in trades %}
                <tr>
                    <td>{{ trade['Entry Time'] }}</td>
                    <td>{{ trade['Exit Time'] }}</td>
                    <td>{{ trade['Position Type'] }}</td>
                    <td>{{ trade['Exit Type'] }}</td>
                    <td>{{ "%.4f"|format(trade['Position Size']) }}</td>
                    <td>{{ "%.4f"|format(trade['Entry Price']) }}</td>
                    <td>{{ "%.4f"|format(trade['Exit Price']) }}</td>
                    <td class="{{ 'success' if trade['Profit/Loss'] > 0 else 'danger' }}">{{ "%.2f"|format(trade['Profit/Loss']) }}</td>
                    <td class="{{ 'success' if trade['Return %'] > 0 else 'danger' }}">{{ "%.2f"|format(trade['Return %']) }}%</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
            """
            with open(template_path, "w") as f:
                f.write(default_template)
                
    def _create_charts(self, equity_df: pd.DataFrame) -> str:
        """Create Plotly charts and return as HTML string."""
        if equity_df.empty or len(equity_df) < 2:
            return "<p>Not enough data points to generate charts.</p>"
            
        # Drawdown calculation
        equity_df['cummax'] = equity_df['equity'].cummax()
        equity_df['drawdown'] = (equity_df['equity'] - equity_df['cummax']) / equity_df['cummax'] * 100
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.05, row_heights=[0.7, 0.3])
                            
        # Equity Curve
        fig.add_trace(go.Scatter(
            x=equity_df['time'], y=equity_df['equity'],
            name="Equity", line=dict(color="#007bff", width=2),
            fill='tozeroy', fillcolor='rgba(0,123,255,0.1)'
        ), row=1, col=1)
        
        # Drawdown Curve
        fig.add_trace(go.Scatter(
            x=equity_df['time'], y=equity_df['drawdown'],
            name="Drawdown %", line=dict(color="#dc3545", width=1.5),
            fill='tozeroy', fillcolor='rgba(220,53,69,0.2)'
        ), row=2, col=1)
        
        fig.update_layout(
            title_text="Equity and Drawdown Curves",
            height=600,
            showlegend=False,
            margin=dict(l=40, r=40, t=40, b=40),
            hovermode="x unified"
        )
        
        fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)
        
        # Include plotly.js inline for standalone HTML
        return fig.to_html(full_html=False, include_plotlyjs='cdn')
        
    def _create_trades_analysis_charts(self, trades: List[Dict[str, Any]]) -> str:
        """Create P&L Distribution and Win/Loss ratio charts as HTML string."""
        if not trades:
            return ""
            
        import numpy as np
        
        # 1. Prepare data for P&L Distribution
        # Extract percentage returns, keeping sign
        returns = [t.get('Return %', 0) for t in trades]
        profits = [r for r in returns if r > 0]
        losses = [r for r in returns if r < 0]
        
        avg_profit = np.mean(profits) if profits else 0
        avg_loss = np.mean(losses) if losses else 0
        
        # 2. Prepare data for Win/Loss ratio
        win_count = len(profits)
        loss_count = len(losses)
        breakeven_count = len(returns) - win_count - loss_count
        
        total_trades = len(trades)
        
        # Setup subplot layout
        fig = make_subplots(
            rows=1, cols=2, 
            specs=[[{"type": "xy"}, {"type": "domain"}]],
            column_widths=[0.6, 0.4],
            subplot_titles=("P&L Distribution", "Win/loss ratio")
        )
        
        # Chart 1: P&L Distribution (Histogram)
        # We process manually to color positives green, negatives red
        if returns:
            # Create a histogram using a combined array to get universal bins
            counts, bins = np.histogram(returns, bins=10)
            bin_centers = 0.5 * (bins[:-1] + bins[1:])
            
            # Split into colors
            colors = ['#dc3545' if c < 0 else '#28a745' for c in bin_centers]
            
            fig.add_trace(go.Bar(
                x=bin_centers,
                y=counts,
                marker_color=colors,
                name="Trades",
                hovertemplate="Return: %{x:.2f}%<br>Count: %{y}<extra></extra>"
            ), row=1, col=1)
            
            # Add average lines
            if avg_loss < 0:
                fig.add_vline(x=avg_loss, line_dash="dash", line_color="#dc3545",
                            annotation_text=f" Avg loss {avg_loss:.2f}%", 
                            annotation_position="bottom left",
                            annotation=dict(font_size=10, font_color="#dc3545"),
                            row=1, col=1)
            if avg_profit > 0:
                fig.add_vline(x=avg_profit, line_dash="dash", line_color="#28a745",
                            annotation_text=f" Avg profit {avg_profit:.2f}%", 
                            annotation_position="bottom right",
                            annotation=dict(font_size=10, font_color="#28a745"),
                            row=1, col=1)
        
        # Chart 2: Win/Loss Ratio (Doughnut)
        labels = ['Wins', 'Losses', 'Break even']
        values = [win_count, loss_count, breakeven_count]
        pie_colors = ['#28a745', '#dc3545', '#ffc107']
        
        # Remove empty categories
        labels_f = [l for l, v in zip(labels, values) if v > 0]
        colors_f = [c for c, v in zip(pie_colors, values) if v > 0]
        values_f = [v for v in values if v > 0]
        
        fig.add_trace(go.Pie(
            labels=labels_f,
            values=values_f,
            hole=0.6,
            marker_colors=colors_f,
            textinfo="none",
            hoverinfo="label+value+percent"
        ), row=1, col=2)
        
        # Center text for donut
        fig.add_annotation(
            text=f"<b>{total_trades}</b><br><span style='font-size:12px'>Total trades</span>",
            x=0.825, y=0.5, # True center relative to the 0.6 to 1.0 paper domain space
            xref="paper", yref="paper",
            font_size=20,
            showarrow=False,
            font_color="#333"
        )

        fig.update_layout(
            height=350,
            showlegend=True,
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=40, r=40, t=40, b=40),
            legend=dict(
                orientation="v",
                yanchor="middle",
                y=0.5,
                xanchor="left",
                x=1.0
            )
        )
        
        fig.update_xaxes(title_text="Return %", row=1, col=1, gridcolor='#f8f9fa', zerolinecolor='#ddd')
        fig.update_yaxes(title_text="Number of trades", row=1, col=1, gridcolor='#f8f9fa')
        
        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_mae_mfe_chart(self, trades: List[Dict[str, Any]]) -> str:
        """
        Create a MAE vs MFE scatter plot for all trades.

        Classic interpretation:
          - X-axis = MFE % (how far price moved IN FAVOUR at best — bigger is better)
          - Y-axis = MAE % (how far price moved AGAINST at worst — smaller is better)
          - Green dots = winning trades, Red dots = losing trades
          - A diagonal reference line (MFE == MAE) separates trades that "got lucky"
            from those where the setup had genuine follow-through.

        Returns the Plotly chart as an HTML string, or empty string if not enough data.
        """
        if not trades:
            return ""

        # Filter trades that have non-zero MAE/MFE data attached
        valid = [t for t in trades if t.get('MAE %', 0) > 0 or t.get('MFE %', 0) > 0]
        if not valid:
            return ""

        # Separate winners and losers for colour coding
        winners = [t for t in valid if t.get('Profit/Loss', 0) > 0]
        losers  = [t for t in valid if t.get('Profit/Loss', 0) <= 0]

        fig = go.Figure()

        # Winning trades — green
        if winners:
            fig.add_trace(go.Scatter(
                x=[t.get('MFE %', 0) for t in winners],
                y=[t.get('MAE %', 0) for t in winners],
                mode='markers',
                marker=dict(color='#28a745', size=8, opacity=0.75, line=dict(width=1, color='#145a24')),
                name='Winners',
                customdata=[[
                    t.get('Entry Time', ''),
                    t.get('Position Type', ''),
                    t.get('Profit/Loss', 0),
                    t.get('Return %', 0),
                ] for t in winners],
                hovertemplate=(
                    "<b>%{customdata[1]}</b> | %{customdata[0]}<br>"
                    "MFE: %{x:.2f}% &nbsp; MAE: %{y:.2f}%<br>"
                    "PnL: %{customdata[2]:.2f} USD (%{customdata[3]:.2f}%)"
                    "<extra>Winner</extra>"
                )
            ))

        # Losing trades — red
        if losers:
            fig.add_trace(go.Scatter(
                x=[t.get('MFE %', 0) for t in losers],
                y=[t.get('MAE %', 0) for t in losers],
                mode='markers',
                marker=dict(color='#dc3545', size=8, opacity=0.75, line=dict(width=1, color='#7b1c27')),
                name='Losers',
                customdata=[[
                    t.get('Entry Time', ''),
                    t.get('Position Type', ''),
                    t.get('Profit/Loss', 0),
                    t.get('Return %', 0),
                ] for t in losers],
                hovertemplate=(
                    "<b>%{customdata[1]}</b> | %{customdata[0]}<br>"
                    "MFE: %{x:.2f}% &nbsp; MAE: %{y:.2f}%<br>"
                    "PnL: %{customdata[2]:.2f} USD (%{customdata[3]:.2f}%)"
                    "<extra>Loser</extra>"
                )
            ))

        # Reference diagonal line where MFE == MAE (trades exited exactly at worst/best)
        all_mfe = [t.get('MFE %', 0) for t in valid]
        all_mae = [t.get('MAE %', 0) for t in valid]
        axis_max = max(max(all_mfe, default=1), max(all_mae, default=1)) * 1.1
        fig.add_trace(go.Scatter(
            x=[0, axis_max], y=[0, axis_max],
            mode='lines',
            line=dict(color='rgba(100,100,100,0.35)', dash='dash', width=1),
            name='MFE = MAE',
            hoverinfo='skip',
            showlegend=True
        ))

        fig.update_layout(
            title_text="MAE / MFE Scatter Plot",
            height=420,
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=60, r=40, t=50, b=60),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode='closest',
        )
        fig.update_xaxes(
            title_text="MFE % (best unrealised profit during trade)",
            gridcolor='#f0f0f0',
            zerolinecolor='#cccccc',
            range=[0, axis_max],
        )
        fig.update_yaxes(
            title_text="MAE % (worst adverse move during trade)",
            gridcolor='#f0f0f0',
            zerolinecolor='#cccccc',
            range=[0, axis_max],
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    # ===========================================================================
    # IMPROVEMENT #11 — Richer HTML Report Charts
    # ===========================================================================

    def _create_monthly_returns_heatmap(self, trades: List[Dict[str, Any]]) -> str:
        """
        Build a calendar heatmap of monthly returns.

        Each cell = sum of PnL / (sum of trade_capital) * 100 for that month.
        Colour scale: green = profitable, red = losing. Cells show the % return.

        Returns empty string if fewer than 2 months of trades exist.
        """
        if not trades:
            return ""

        rows = []
        for t in trades:
            exit_time = t.get('Exit Time', '')
            pnl       = t.get('Profit/Loss', 0.0)
            pos_size  = t.get('Position Size', 0.0)
            entry_price = t.get('Entry Price', 0.0)
            leverage    = t.get('Leverage', 1)

            if not exit_time or exit_time == 'N/A':
                continue
            try:
                # Accept both 'dd-mm-yy HH:MM' and ISO formats from the engine
                try:
                    dt = pd.to_datetime(exit_time, format='%d-%m-%y %H:%M')
                except Exception:
                    dt = pd.to_datetime(exit_time)
                # Approximate trade capital: notional / leverage
                trade_capital = (pos_size * entry_price / max(leverage, 1)) if pos_size and entry_price else 1.0
                rows.append({'year': dt.year, 'month': dt.month, 'pnl': pnl, 'capital': trade_capital})
            except Exception:
                continue

        if not rows:
            return ""

        df = pd.DataFrame(rows)
        grouped = df.groupby(['year', 'month']).agg(pnl=('pnl', 'sum'), capital=('capital', 'sum')).reset_index()
        grouped['ret_pct'] = (grouped['pnl'] / grouped['capital'].clip(lower=1)) * 100

        years  = sorted(grouped['year'].unique())
        months = list(range(1, 13))
        month_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Build z-matrix (rows = years, cols = months) and annotation text
        z_matrix    = []
        text_matrix = []
        for yr in years:
            z_row   = []
            txt_row = []
            for mo in months:
                row = grouped[(grouped['year'] == yr) & (grouped['month'] == mo)]
                if row.empty:
                    z_row.append(None)
                    txt_row.append('')
                else:
                    val = round(float(row['ret_pct'].iloc[0]), 2)
                    z_row.append(val)
                    txt_row.append(f"{val:+.1f}%")
            z_matrix.append(z_row)
            text_matrix.append(txt_row)

        # Symmetric colour scale centred at zero
        abs_max = max((abs(v) for row in z_matrix for v in row if v is not None), default=1)

        fig = go.Figure(go.Heatmap(
            z=z_matrix,
            x=month_labels,
            y=[str(yr) for yr in years],
            text=text_matrix,
            texttemplate='%{text}',
            textfont=dict(size=12, color='white'),
            colorscale=[
                [0.0,  '#c0392b'],   # deep red
                [0.45, '#e74c3c'],   # red
                [0.50, '#2c3e50'],   # neutral dark
                [0.55, '#27ae60'],   # green
                [1.0,  '#1a5c36'],   # deep green
            ],
            zmin=-abs_max,
            zmax=abs_max,
            hovertemplate='%{y} %{x}: %{text}<extra></extra>',
            showscale=True,
            colorbar=dict(title='Return %', thickness=12),
        ))

        fig.update_layout(
            title_text='Monthly Returns Heatmap',
            height=max(200, 80 * len(years) + 80),
            plot_bgcolor='#1a1a2e',
            paper_bgcolor='white',
            margin=dict(l=60, r=60, t=50, b=40),
            xaxis=dict(side='top'),
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def _create_candlestick_chart(
        self,
        equity_df: pd.DataFrame,
        trades: List[Dict[str, Any]]
    ) -> str:
        """
        Resample the equity curve into weekly OHLC bars displayed as a
        candlestick chart, with entry (▲) and exit (✕) markers overlaid
        as scatter traces.

        This gives an at-a-glance view of which weeks saw entries/exits,
        and how the equity moved in that context.

        Returns empty string if equity_df is too short (<4 bars).
        """
        if equity_df is None or equity_df.empty or len(equity_df) < 4:
            return ""

        try:
            edf = equity_df.copy()
            # Ensure 'time' is datetime for resampling
            if not pd.api.types.is_datetime64_any_dtype(edf['time']):
                edf['time'] = pd.to_datetime(edf['time'], errors='coerce')
            edf = edf.dropna(subset=['time'])
            edf = edf.set_index('time').sort_index()

            # Resample equity to weekly OHLC
            weekly = edf['equity'].resample('W').ohlc().dropna()
            if weekly.empty or len(weekly) < 2:
                return ""

            fig = go.Figure()

            # Candlestick bars
            fig.add_trace(go.Candlestick(
                x=weekly.index,
                open=weekly['open'],
                high=weekly['high'],
                low=weekly['low'],
                close=weekly['close'],
                name='Weekly Equity',
                increasing_line_color='#27ae60',
                decreasing_line_color='#e74c3c',
                increasing_fillcolor='rgba(39,174,96,0.4)',
                decreasing_fillcolor='rgba(231,76,60,0.4)',
            ))

            # Overlay entry and exit markers from trades if timestamps parseable
            entry_times, entry_equities, entry_labels = [], [], []
            exit_times,  exit_equities,  exit_labels  = [], [], []

            equity_series = edf['equity']

            for t in trades:
                for time_key, equity_list, labels_list in [
                    ('Entry Time', entry_times, entry_labels),
                    ('Exit Time',  exit_times,  exit_labels),
                ]:
                    ts_str = t.get(time_key, '')
                    pnl    = t.get('Profit/Loss', 0.0)
                    try:
                        try:
                            dt = pd.to_datetime(ts_str, format='%d-%m-%y %H:%M')
                        except Exception:
                            dt = pd.to_datetime(ts_str)

                        # Find nearest equity bar to place the marker
                        idx = equity_series.index.asof(dt)
                        eq  = float(equity_series.get(idx, equity_series.iloc[-1]))
                        equity_list.append(dt)
                        labels_list.append(f"{t.get('Position Type','')}: PnL {pnl:+.2f}")
                    except Exception:
                        continue

            # Entry markers — green/red triangles based on direction
            if entry_times:
                fig.add_trace(go.Scatter(
                    x=entry_times, y=entry_equities,
                    mode='markers',
                    marker=dict(symbol='triangle-up', size=9, color='#3498db',
                                line=dict(width=1, color='#1a5276')),
                    name='Entry',
                    text=entry_labels,
                    hovertemplate='<b>ENTRY</b><br>%{text}<extra></extra>',
                ))

            if exit_times:
                fig.add_trace(go.Scatter(
                    x=exit_times, y=exit_equities,
                    mode='markers',
                    marker=dict(symbol='x', size=9, color='#e67e22',
                                line=dict(width=2, color='#935116')),
                    name='Exit',
                    text=exit_labels,
                    hovertemplate='<b>EXIT</b><br>%{text}<extra></extra>',
                ))

            fig.update_layout(
                title_text='Equity Curve — Weekly Candlestick with Trade Markers',
                height=450,
                plot_bgcolor='white',
                paper_bgcolor='white',
                margin=dict(l=60, r=40, t=50, b=60),
                xaxis_rangeslider_visible=False,
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                hovermode='x unified',
            )
            fig.update_xaxes(gridcolor='#f0f0f0', zerolinecolor='#ddd')
            fig.update_yaxes(title_text='Equity ($)', gridcolor='#f0f0f0', zerolinecolor='#ddd')

            return fig.to_html(full_html=False, include_plotlyjs='cdn')

        except Exception as exc:
            logger.warning(f"Could not generate candlestick chart: {exc}")
            return ""

    def _create_streak_chart(self, trades: List[Dict[str, Any]]) -> str:
        """
        Visualise consecutive win/loss runs as a horizontal bar chart.

        Each bar represents one streak: green = winning run, red = losing run.
        The bar length = number of consecutive trades in that streak.
        Bars are ordered chronologically (top-to-bottom = oldest-to-newest).

        Helps identify clustering of good / bad trades and reveals whether
        losses are isolated events or tend to come in groups.

        Returns empty string if fewer than 3 completed trades exist.
        """
        closed = [t for t in trades if t.get('Profit/Loss') is not None]
        if len(closed) < 3:
            return ""

        # Build streak list: each entry = (streak_length, is_win, label, start_idx)
        streaks: List[Dict[str, Any]] = []
        i = 0
        streak_num = 1
        while i < len(closed):
            is_win = closed[i].get('Profit/Loss', 0.0) > 0
            j = i
            while j < len(closed) and (closed[j].get('Profit/Loss', 0.0) > 0) == is_win:
                j += 1
            length = j - i
            label = f"{'W' * length if is_win else 'L' * length}  ({length} {'win' if is_win else 'loss'}{'s' if length > 1 else ''})"
            streaks.append({'length': length, 'is_win': is_win, 'label': label, 'num': streak_num})
            streak_num += 1
            i = j

        if not streaks:
            return ""

        # Lay out chart (oldest at top, newest at bottom)
        y_labels = [f"Streak #{s['num']}" for s in streaks]
        x_vals   = [s['length'] for s in streaks]
        colours  = ['#27ae60' if s['is_win'] else '#e74c3c' for s in streaks]
        texts    = [s['label'] for s in streaks]

        fig = go.Figure(go.Bar(
            x=x_vals,
            y=y_labels,
            orientation='h',
            marker_color=colours,
            text=texts,
            textposition='inside',
            insidetextanchor='start',
            textfont=dict(color='white', size=11),
            hovertemplate='%{y}: %{text}<extra></extra>',
            name='',
        ))

        fig.update_layout(
            title_text='Win / Loss Streaks (chronological)',
            height=max(300, 30 * len(streaks) + 100),
            plot_bgcolor='white',
            paper_bgcolor='white',
            margin=dict(l=90, r=40, t=50, b=40),
            showlegend=False,
            bargap=0.25,
        )
        fig.update_xaxes(
            title_text='Consecutive trades',
            gridcolor='#f0f0f0',
            dtick=1,
        )
        fig.update_yaxes(
            autorange='reversed',   # oldest streak at top
            gridcolor='#f0f0f0',
        )

        return fig.to_html(full_html=False, include_plotlyjs='cdn')

    def generate_report(self, symbol: str, timeframe: str, metrics: Dict[str, Any],
                        trades: List[Dict[str, Any]], equity_df: pd.DataFrame,
                        filepath: str = None) -> str:
        """
        Generate the HTML report.
        
        Returns:
            String path to the generated HTML file.
        """
        template = self.env.get_template("report_template.html")
        chart_html           = self._create_charts(equity_df)
        trades_analysis_html = self._create_trades_analysis_charts(trades)
        mae_mfe_chart_html   = self._create_mae_mfe_chart(trades)

        # Improvement #11 — three additional overview charts
        monthly_heatmap_html  = self._create_monthly_returns_heatmap(trades)
        candlestick_html      = self._create_candlestick_chart(equity_df, trades)
        streak_chart_html     = self._create_streak_chart(trades)

        html_out = template.render(
            symbol=symbol,
            timeframe=timeframe,
            metrics=metrics,
            trades=trades,
            chart_html=chart_html,
            trades_analysis_html=trades_analysis_html,
            mae_mfe_chart_html=mae_mfe_chart_html,
            # Improvement #11
            monthly_heatmap_html=monthly_heatmap_html,
            candlestick_html=candlestick_html,
            streak_chart_html=streak_chart_html,
        )

        
        if filepath is None:
            filepath = self.reports_dir / f"{symbol}_{timeframe}_report.html"
        else:
            filepath = Path(filepath)
            
        with open(filepath, "w") as f:
            f.write(html_out)
            
        logger.info(f"Report generated successfully: {filepath}")
        return str(filepath)
