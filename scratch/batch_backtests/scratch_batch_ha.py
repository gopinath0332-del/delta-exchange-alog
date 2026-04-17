import os
import subprocess
import re
import pandas as pd
import concurrent.futures
from pathlib import Path
import time
import sys

DATA_DIR = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H"
SETTINGS_PATH = r"D:\Workspace\delta-exchange-alog\config\settings.yaml"

def modify_settings(pct):
    with open(SETTINGS_PATH, 'r') as f:
        content = f.read()
    
    # Regex to find and replace stop_loss_pct under donchian_channel
    new_content = re.sub(
        r'(stop_loss_pct:\s*)[0-9.]+',
        rf'\g<1>{pct}',
        content
    )
    with open(SETTINGS_PATH, 'w') as f:
        f.write(new_content)
    print(f"Updated settings.yaml with stop_loss_pct: {pct}")

def parse_output(output, symbol):
    try:
        final_capital = float(re.search(r'Final Capital:\s+\$([0-9,.]+)', output).group(1).replace(',', ''))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1))
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        sortino = float(re.search(r'Sortino Ratio:\s+([0-9,.-]+)', output).group(1))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        win_rate = float(re.search(r'Win Rate:\s+([0-9,.]+)%', output).group(1))
        profit_factor = float(re.search(r'Profit Factor:\s+([0-9,.]+)', output).group(1))
        return {
            'Symbol': symbol,
            'Final Capital': final_capital,
            'Return (%)': return_pct,
            'Sharpe': sharpe,
            'Sortino': sortino,
            'Max DD (%)': max_dd,
            'Trades': trades,
            'Win Rate (%)': win_rate,
            'Profit Factor': profit_factor
        }
    except Exception as e:
        print(f"Failed to parse for {symbol}: {e}")
        return None

def run_backtest(file_path):
    filename = os.path.basename(file_path)
    symbol = filename.split('_')[0]
    
    cmd = [
        r"venv\Scripts\python.exe",
        "run_backtest.py",
        "--strategy", "donchian_channel",
        "--symbol", symbol,
        "--file", file_path,
        "--candle-type", "heikin_ashi"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        return parse_output(result.stdout, symbol)
    except Exception as e:
        print(f"Error running {symbol}: {e}")
        return None

def main():
    files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    print(f"Found {len(files)} files to process.")
    
    scenarios = [('0.20', 'results_ha_0.20.csv'), ('0.25', 'results_ha_0.25.csv')]
    
    for pct, out_file in scenarios:
        modify_settings(pct)
        print(f"Running scenario {pct}...")
        
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_file = {executor.submit(run_backtest, f): f for f in files}
            for i, future in enumerate(concurrent.futures.as_completed(future_to_file)):
                res = future.result()
                if res:
                    results.append(res)
                if (i + 1) % 20 == 0:
                    print(f"Processed {i + 1}/{len(files)}")
                    
        df = pd.DataFrame(results)
        df.to_csv(out_file, index=False)
        print(f"Saved {len(df)} results to {out_file}")

    # Restore setting
    modify_settings('0.20') # We changed the default to 0.20 based on previous analysis

if __name__ == "__main__":
    main()
