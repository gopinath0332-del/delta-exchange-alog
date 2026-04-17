import os
import subprocess
import re
import pandas as pd
import concurrent.futures
from tqdm import tqdm

DATA_DIR = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H"
# We'll use the relative path for the python executable since we're in the project root
PYTHON_EXE = r"venv\Scripts\python.exe"

def parse_output(output, symbol):
    try:
        # Regex to extract metrics from the print_summary output in run_backtest.py
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', ''))
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        sortino = float(re.search(r'Sortino Ratio:\s+([0-9,.-]+)', output).group(1))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        win_rate = float(re.search(r'Win Rate:\s+([0-9,.]+)%', output).group(1))
        profit_factor = float(re.search(r'Profit Factor:\s+([0-9,.-]+)', output).group(1))
        
        return {
            'Symbol': symbol, 
            'Return (%)': return_pct, 
            'Profit Factor': profit_factor,
            'Sharpe': sharpe, 
            'Sortino': sortino, 
            'Max DD (%)': max_dd, 
            'Trades': trades, 
            'Win Rate (%)': win_rate
        }
    except Exception as e:
        # print(f"Error parsing output for {symbol}: {e}")
        return None

def run_backtest(file_path, candle_type):
    filename = os.path.basename(file_path)
    symbol = filename.split('_')[0]
    cmd = [
        PYTHON_EXE, "run_backtest.py", 
        "--strategy", "bb-breakout",
        "--symbol", symbol, 
        "--file", file_path, 
        "--candle-type", candle_type
    ]
    try:
        # Increased timeout to 60s as BB strategy calculation with HA might be slower
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            metrics = parse_output(result.stdout, symbol)
            if metrics:
                metrics['Candle Type'] = candle_type
            return metrics
    except Exception as e:
        # print(f"Error running backtest for {symbol}: {e}")
        pass
    return None

def main():
    if not os.path.exists("scratch/batch_backtests"):
        os.makedirs("scratch/batch_backtests")
        
    files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    print(f"Found {len(files)} data files. Starting batch backtests...")

    for candle in ['standard', 'heikin_ashi']:
        out_file = f"scratch/batch_backtests/bb_results_1h_{candle}.csv"
        results = []
        
        # Use high concurrency for faster execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_file = {executor.submit(run_backtest, f, candle): f for f in files}
            
            for future in tqdm(concurrent.futures.as_completed(future_to_file), total=len(files), desc=f"BB 1H ({candle})"):
                res = future.result()
                if res: 
                    results.append(res)
        
        if results:
            df = pd.DataFrame(results)
            # Sort by Profit Factor descending
            df = df.sort_values(by='Profit Factor', ascending=False)
            df.to_csv(out_file, index=False)
            print(f"Saved {len(results)} results for {candle} to {out_file}")
        else:
            print(f"No results generated for {candle}.")

if __name__ == "__main__":
    main()
