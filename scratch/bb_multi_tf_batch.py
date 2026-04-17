import os
import subprocess
import pandas as pd
import yaml
from tqdm import tqdm

# Constants
BASE_DATA_DIR = r"D:\Workspace\crypto-backtest-data"
TIMEFRAMES = ["1H", "2H", "4H"]
PYTHON_EXE = r"venv\Scripts\python.exe"
BATCH_SCRIPT = r"scratch\bb_backtest_batch.py"

def run_tf_batch(tf):
    data_dir = os.path.join(BASE_DATA_DIR, f"delta_crypto_data_{tf}")
    print(f"\n>>> Starting Full Batch Backtest for Timeframe: {tf}")
    
    if not os.path.exists(data_dir):
        print(f"Error: Data directory {data_dir} not found.")
        return None

    # We need to temporarily modify DATA_DIR in bb_backtest_batch.py 
    # OR we can just call run_backtest.py directly in a loop here. 
    # Let's call run_backtest.py directly for better control.
    
    files = [os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith('.csv')]
    print(f"Found {len(files)} coins for {tf}.")
    
    # We use the same parsing logic as bb_backtest_batch.py
    import re
    def parse(output, symbol):
        try:
            return {
                'Symbol': symbol,
                'Return (%)': float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', '')),
                'Profit Factor': float(re.search(r'Profit Factor:\s+([0-9,.-]+)', output).group(1)),
                'Sharpe': float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1)),
                'Sortino': float(re.search(r'Sortino Ratio:\s+([0-9,.-]+)', output).group(1)),
                'Max DD (%)': float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1)),
                'Trades': int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1)),
                'Win Rate (%)': float(re.search(r'Win Rate:\s+([0-9,.]+)%', output).group(1))
            }
        except: return None

    results = []
    
    import concurrent.futures
    def run_one(f):
        symbol = os.path.basename(f).split('_')[0]
        cmd = [PYTHON_EXE, "run_backtest.py", "--strategy", "bb-breakout", "--symbol", symbol, "--file", f, "--candle-type", "heikin_ashi"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return parse(res.stdout, symbol)
        except: return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(run_one, f): f for f in files}
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(files), desc=f"BB {tf}"):
            r = future.result()
            if r: results.append(r)
    
    if results:
        df = pd.DataFrame(results)
        out_path = f"scratch/batch_backtests/bb_results_{tf}_final.csv"
        df.sort_values(by='Profit Factor', ascending=False).to_csv(out_path, index=False)
        return df
    return None

def main():
    if not os.path.exists("scratch/batch_backtests"):
        os.makedirs("scratch/batch_backtests")

    comparison = []
    for tf in TIMEFRAMES:
        df = run_tf_batch(tf)
        if df is not None:
            comparison.append({
                'Timeframe': tf,
                'Avg PF': df['Profit Factor'].mean(),
                'Avg Return %': df['Return (%)'].mean(),
                'Avg Sharpe': df['Sharpe'].mean(),
                'Global Max DD %': df['Max DD (%)'].max(),
                'Profitable/Total': f"{len(df[df['Profit Factor'] > 1.0])}/{len(df)}",
                'Total Trades': df['Trades'].sum()
            })
    
    if comparison:
        comp_df = pd.DataFrame(comparison)
        print("\n" + "="*80)
        print(f"{'MULTI-TIMEFRAME PERFORMANCE COMPARISON':^80}")
        print("="*80)
        print(comp_df.to_string(index=False))
        print("="*80)
        comp_df.to_csv("scratch/batch_backtests/bb_multi_tf_comparison.csv", index=False)

if __name__ == "__main__":
    main()
