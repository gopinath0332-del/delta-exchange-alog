import os
import subprocess
import re
import pandas as pd
import yaml
import concurrent.futures
from tqdm import tqdm
from pathlib import Path

# Configuration
ROOT_DATA_DIR = Path(r"D:\Workspace\crypto-backtest-data")
TIME_FRAMES = ["1H", "2H", "4H"]
SETTINGS_PATH = Path(r"d:\Workspace\delta-exchange-alog\config\settings.yaml")
PYTHON_EXE = "python"

PRIORITY_COINS = ["PIPPIN", "BIO", "ARC", "RIVER", "BERA", "PAXG", "BTC", "ETH", "XRP", "BEAT", "SOL", "SUI"]

def get_all_test_files():
    files = []
    for tf in TIME_FRAMES:
        tf_dir = ROOT_DATA_DIR / f"delta_crypto_data_{tf}"
        if tf_dir.exists():
            for csv in tf_dir.glob("*.csv"):
                symbol = csv.name.split('_')[0].replace("USD", "")
                files.append({
                    'symbol': symbol,
                    'full_symbol': csv.name.split('_')[0],
                    'tf': tf.lower(),
                    'path': str(csv),
                    'priority': 1 if symbol in PRIORITY_COINS else 0
                })
    # Sort so priority coins run first
    return sorted(files, key=lambda x: x['priority'], reverse=True)

def update_settings_standard():
    """Set standard parameters for screening baseline."""
    with open(SETTINGS_PATH, 'r') as f:
        config = yaml.safe_load(f)
    
    dc_cfg = config['strategies']['donchian_channel']
    dc_cfg['enter_period'] = 20
    dc_cfg['exit_period'] = 10
    
    rm_cfg = config['risk_management']
    rm_cfg['risk_pct_per_trade'] = 0.01
    rm_cfg['sizing_method'] = "fractional"
    
    config['backtesting']['use_compounding'] = True

    with open(SETTINGS_PATH, 'w') as f:
        yaml.safe_dump(config, f)

def parse_output(output):
    try:
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', ''))
        pf = float(re.search(r'Profit Factor:\s+([0-9,.-]+)', output).group(1))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        return {
            'Sharpe': sharpe, 
            'Return %': return_pct, 
            'PF': pf,
            'MaxDD %': max_dd,
            'Trades': trades
        }
    except:
        return None

def run_backtest(file_info):
    cmd = [
        PYTHON_EXE, "run_backtest.py", 
        "--strategy", "donchian-channel",
        "--symbol", file_info['full_symbol'], 
        "--file", file_info['path'], 
        "--candle-type", "heikin_ashi"
    ]
    try:
        # We run standard settings first, so settings.yaml must not change DURING the backtest process
        # Since we are screening with FIXED parameters, we only need to set settings.yaml ONCE at the start.
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            res = parse_output(result.stdout)
            if res:
                res.update({
                    'Symbol': file_info['symbol'],
                    'TF': file_info['tf']
                })
                return res
    except:
        pass
    return None

def main():
    if not os.path.exists("scratch/batch_backtests"):
        os.makedirs("scratch/batch_backtests")

    test_files = get_all_test_files()
    print(f"Starting Multi-Coin Screener for {len(test_files)} datasets.")

    # Set standard parameters once
    update_settings_standard()
    
    results = []
    
    # Run in parallel since settings.yaml remains unchanged for screening
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(run_backtest, f): f for f in test_files}
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(test_files), desc="Screening Coins"):
            res = future.result()
            if res:
                results.append(res)
                # Periodic save
                if len(results) % 50 == 0:
                    pd.DataFrame(results).to_csv("scratch/batch_backtests/screening_partial.csv", index=False)

    if results:
        df = pd.DataFrame(results)
        df = df.sort_values(by='Sharpe', ascending=False)
        df.to_csv("scratch/batch_backtests/donchian_screening_results.csv", index=False)
        
        print("\n" + "="*80)
        print(f"{'SCREENING LEADERBOARD (Top 20 by Sharpe Ratio)':^80}")
        print("="*80)
        print(df.head(20).to_string(index=False))
        print("="*80)
    else:
        print("No results found.")

if __name__ == "__main__":
    main()
