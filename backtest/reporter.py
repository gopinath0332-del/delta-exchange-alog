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
        
    def generate_report(self, symbol: str, timeframe: str, metrics: Dict[str, Any], 
                        trades: List[Dict[str, Any]], equity_df: pd.DataFrame, 
                        filepath: str = None) -> str:
        """
        Generate the HTML report.
        
        Returns:
            String path to the generated HTML file.
        """
        template = self.env.get_template("report_template.html")
        chart_html = self._create_charts(equity_df)
        
        # Render HTML
        html_out = template.render(
            symbol=symbol,
            timeframe=timeframe,
            metrics=metrics,
            trades=trades,
            chart_html=chart_html
        )
        
        if filepath is None:
            filepath = self.reports_dir / f"{symbol}_{timeframe}_report.html"
        else:
            filepath = Path(filepath)
            
        with open(filepath, "w") as f:
            f.write(html_out)
            
        logger.info(f"Report generated successfully: {filepath}")
        return str(filepath)
