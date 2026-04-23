import os
import re
from pathlib import Path

def extract_metrics(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    symbol = os.path.basename(file_path).replace('_1h_report.html', '')
    metrics = {}
    
    def get_stat(title):
        pattern = rf'{title}</div>.*?stat-value.*?>\s*(?:<span.*?>)?(.*?)(?:%?</span>)?\s*(?:</span|</div>)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            val = match.group(1).strip().replace('+', '').replace('%', '').replace(',', '')
            try:
                return float(val)
            except ValueError:
                return 0.0
        return 0.0

    metrics['Total Return %'] = get_stat('Total Return %')
    metrics['Max Drawdown %'] = get_stat('Max Drawdown %')
    metrics['Profit Factor'] = get_stat('Profit Factor')
    metrics['Win Rate %'] = get_stat('Win Rate %')
    metrics['Sharpe Ratio'] = get_stat('Sharpe Ratio')
    
    # Number of Trades is slightly different or in the table
    trades_pattern = r'Number of Trades:</span>\s*<span.*?>(\d+)</span>'
    trades_match = re.search(trades_pattern, content)
    if trades_match:
        metrics['Number of Trades'] = int(trades_match.group(1))
    else:
        metrics['Number of Trades'] = int(get_stat('Number of Trades'))

    return symbol, metrics

def main():
    reports_dir = Path('reports')
    all_results = []
    
    for report_file in reports_dir.glob('*_report.html'):
        try:
            symbol, metrics = extract_metrics(report_file)
            if metrics['Number of Trades'] > 0: # Check any trades
                metrics['Symbol'] = symbol
                all_results.append(metrics)
            else:
                # print(f"Skipping {symbol}: No trades")
                pass
        except Exception as e:
            print(f"Error parsing {report_file}: {e}")
            
    if not all_results:
        print("No results found. Check regex or file paths.")
        return

    # Sort by Profit Factor descending
    sorted_results = sorted(all_results, key=lambda x: x.get('Profit Factor', 0), reverse=True)
    
    print(f"{'Symbol':<15} | {'Return %':<10} | {'Max DD %':<10} | {'PF':<6} | {'Sharpe':<6} | {'Trades':<6}")
    print("-" * 65)
    for m in sorted_results[:20]:
        print(f"{m['Symbol']:<15} | {m['Total Return %']:>10.2f} | {m['Max Drawdown %']:>10.2f} | {m['Profit Factor']:>6.2f} | {m['Sharpe Ratio']:>6.2f} | {m['Number of Trades']:>6}")

if __name__ == "__main__":
    main()
