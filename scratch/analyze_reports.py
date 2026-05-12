import os
import re
from pathlib import Path

def extract_metrics(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        with open(file_path, 'r', encoding='latin-1') as f:
            content = f.read()
    
    # Extract Symbol from Title
    symbol_match = re.search(r'<title>Backtest Report - (.*?) \(', content)
    symbol = symbol_match.group(1).strip() if symbol_match else file_path.name.split('_')[0]
    
    # Extract metrics using regex
    def get_val(label):
        # Look for the label in a stat-title, then get the following stat-value
        pattern = rf'<div class="stat-title">{label}</div>\s*<div class="stat-value.*?">(.*?)</div>'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            # Clean up percentage signs and dollar signs
            val = val.replace('%', '').replace('$', '').replace(',', '')
            try:
                return float(val)
            except ValueError:
                return 0.0
        return 0.0

    profit_factor = get_val('Profit Factor')
    total_return = get_val('Total Return')
    max_drawdown = get_val('Max Drawdown')
    trades = get_val('Total Trades')
    win_rate = get_val('Win Rate')

    return {
        'Symbol': symbol,
        'Profit Factor': profit_factor,
        'Total Return %': total_return,
        'Max Drawdown %': max_drawdown,
        'Trades': int(trades),
        'Win Rate %': win_rate
    }

def main():
    reports_dir = Path('reports')
    all_metrics = []
    
    for file in reports_dir.glob('*_2h_report.html'):
        try:
            metrics = extract_metrics(file)
            if metrics['Trades'] > 5: # Filter out low trade count
                all_metrics.append(metrics)
        except Exception as e:
            print(f"Error processing {file}: {e}")

    # Sort by Profit Factor
    sorted_metrics = sorted(all_metrics, key=lambda x: x['Profit Factor'], reverse=True)
    
    print(f"{'Symbol':<15} | {'Return %':<10} | {'Drawdown %':<12} | {'Trades':<8} | {'Win %':<8} | {'PF':<8}")
    print("-" * 75)
    for m in sorted_metrics[:20]:
        print(f"{m['Symbol']:<15} | {m['Total Return %']:>9.2f}% | {m['Max Drawdown %']:>11.2f}% | {m['Trades']:>8} | {m['Win Rate %']:>7.2f}% | {m['Profit Factor']:>8.2f}")

if __name__ == "__main__":
    main()
