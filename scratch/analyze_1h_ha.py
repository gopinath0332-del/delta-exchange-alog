import os
import re
from pathlib import Path
import pandas as pd

def extract_metrics(file_path):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    symbol = os.path.basename(file_path).split('_')[0]
    metrics = {'Symbol': symbol}
    
    # 1. Summary Stats (Total Return, Max DD, Win Rate, Trades)
    def get_summary(title):
        # Match title, then skip until stat-value, then match the first number/percentage
        pattern = rf'<div class="stat-title">{title}</div>\s*<div class="stat-value">.*?([0-9,.-]+)%?.*?(?:</div>|</span>)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).replace(',', '')
        return "0"

    metrics['Total Return %'] = float(get_summary('Total Return %'))
    metrics['Max Drawdown %'] = float(get_summary('Max Drawdown %'))
    metrics['Win Rate %'] = float(get_summary('Win Rate %'))
    metrics['Number of Trades'] = int(float(get_summary('Number of Trades')))

    # 2. Detailed Ratios (Profit Factor, Sharpe, Sortino)
    def get_ratio(title):
        # <td>Sharpe ratio</td>\s*<td>\s*<span class="val-neu">6.170</span></td>
        pattern = rf'<td>{title}</td>\s*<td>\s*(?:<span.*?>)?\s*([0-9.-]+)\s*(?:</span>)?\s*</td>'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1)
        return "0"

    metrics['Profit Factor'] = float(get_ratio('Profit factor'))
    metrics['Sharpe Ratio'] = float(get_ratio('Sharpe ratio'))
    metrics['Sortino Ratio'] = float(get_ratio('Sortino ratio'))

    return metrics

def main():
    reports_dir = Path('reports')
    all_results = []
    
    files = list(reports_dir.glob('*_report.html'))
    for report_file in files:
        try:
            metrics = extract_metrics(report_file)
            if metrics['Number of Trades'] > 15: # Filter for significance
                all_results.append(metrics)
        except Exception as e:
            pass
            
    if not all_results:
        print("No results found.")
        return

    df = pd.DataFrame(all_results)
    
    # Sort by Profit Factor
    df_pf = df.sort_values(by='Profit Factor', ascending=False)
    
    print("\n" + "="*95)
    print(f"{'TOP 10 SYMBOLS BY PROFIT FACTOR (2H Heikin-Ashi)':^95}")
    print("="*95)
    cols = ['Symbol', 'Profit Factor', 'Total Return %', 'Sharpe Ratio', 'Max Drawdown %', 'Number of Trades']
    print(df_pf[cols].head(10).to_string(index=False))
    print("="*95)

    # Sort by Sharpe Ratio
    df_sharpe = df.sort_values(by='Sharpe Ratio', ascending=False)
    print("\n" + "="*95)
    print(f"{'TOP 10 SYMBOLS BY SHARPE RATIO (2H Heikin-Ashi)':^95}")
    print("="*95)
    print(df_sharpe[cols].head(10).to_string(index=False))
    print("="*95)

    # Identify High Alpha: High Return + High Sharpe
    high_alpha = df.sort_values(by='Total Return %', ascending=False).iloc[0]
    
    # Identify Steady Growth: High Win Rate + Low MaxDD + Good PF
    # Let's filter for MaxDD < 15 and then sort by PF
    steady = df[df['Max Drawdown %'] < 15].sort_values(by='Profit Factor', ascending=False).iloc[0]

    print(f"\n🚀 HIGH ALPHA SUGGESTION: {high_alpha['Symbol']}")
    print(f"   Return: {high_alpha['Total Return %']:.2f}% | Sharpe: {high_alpha['Sharpe Ratio']:.2f} | PF: {high_alpha['Profit Factor']:.2f}")
    
    print(f"\n📈 STEADY GROWTH SUGGESTION: {steady['Symbol']}")
    print(f"   Max Drawdown: {steady['Max Drawdown %']:.2f}% | Win Rate: {steady['Win Rate %']:.2f}% | PF: {steady['Profit Factor']:.2f}")

if __name__ == "__main__":
    main()
