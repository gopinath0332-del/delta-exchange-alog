import os
import subprocess
import re
import pandas as pd
import yaml
import concurrent.futures
from tqdm import tqdm
from itertools import product

# Configuration
DATA_DIR = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H"
SETTINGS_PATH = r"d:\Workspace\delta-exchange-alog\config\settings.yaml"
PYTHON_EXE = r"venv\Scripts\python.exe"

BENCHMARK_COINS = ["PIPPIN", "BCH", "VIRTUAL", "ETH", "BTC", "NEIRO"]
BENCHMARK_FILES = {
    coin: os.path.join(DATA_DIR, f"{coin}USD_1h.csv") 
    for coin in BENCHMARK_COINS
}

# Parameter Grid
GRID = {
    'bb_length': [14, 20, 25],
    'bb_mult': [1.5, 2.0, 2.5],
    'stop_loss_pct': [0.15, 0.20, 0.25],
    'rvol_min': [1.0, 1.5, 2.0],
    'htf_multiplier': [4, 6]
}

def update_settings(params):
    """Update settings.yaml with specific parameters."""
    with open(SETTINGS_PATH, 'r') as f:
        config = yaml.safe_load(f)
    
    # Target the bb_breakout strategy
    bb_cfg = config['strategies']['bb_breakout']
    bb_cfg['bb_length'] = params['bb_length']
    bb_cfg['bb_mult'] = params['bb_mult']
    bb_cfg['stop_loss_pct'] = params['stop_loss_pct']
    bb_cfg['rvol_min'] = params['rvol_min']
    bb_cfg['htf_multiplier'] = params['htf_multiplier']
    
    # Ensure volume filter is enabled if rvol_min > 1.0
    bb_cfg['use_volume'] = True if params['rvol_min'] > 1.0 else False

    with open(SETTINGS_PATH, 'w') as f:
        yaml.safe_dump(config, f)

def parse_output(output, symbol):
    try:
        pf = float(re.search(r'Profit Factor:\s+([0-9,.-]+)', output).group(1))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', ''))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        return {'pf': pf, 'return': return_pct, 'trades': trades, 'max_dd': max_dd}
    except:
        return None

def run_single_backtest(coin, filepath):
    cmd = [
        PYTHON_EXE, "run_backtest.py", 
        "--strategy", "bb-breakout",
        "--symbol", coin, 
        "--file", filepath, 
        "--candle-type", "heikin_ashi"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return parse_output(result.stdout, coin)
    except:
        pass
    return None

def main():
    if not os.path.exists("scratch/batch_backtests"):
        os.makedirs("scratch/batch_backtests")

    # Generate all combinations
    keys = GRID.keys()
    combos = [dict(zip(keys, v)) for v in product(*GRID.values())]
    print(f"Starting optimization with {len(combos)} combinations across {len(BENCHMARK_COINS)} coins.")

    results = []
    
    # We'll back up original settings first
    with open(SETTINGS_PATH, 'r') as f:
        original_settings = f.read()

    try:
        for i, params in enumerate(tqdm(combos, desc="Optimizing Grid")):
            # 1. Update settings
            update_settings(params)
            
            # 2. Run backtests for all benchmark coins in parallel for THIS config
            current_combo_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(BENCHMARK_COINS)) as executor:
                futures = {
                    executor.submit(run_single_backtest, coin, path): coin 
                    for coin, path in BENCHMARK_FILES.items()
                }
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res:
                        current_combo_results.append(res)
            
            # 3. Aggregate metrics for this combo
            if current_combo_results:
                avg_pf = sum(r['pf'] for r in current_combo_results) / len(current_combo_results)
                avg_return = sum(r['return'] for r in current_combo_results) / len(current_combo_results)
                total_trades = sum(r['trades'] for r in current_combo_results)
                max_max_dd = max(r['max_dd'] for r in current_combo_results)
                
                result_entry = params.copy()
                result_entry.update({
                    'Avg PF': avg_pf,
                    'Avg Return (%)': avg_return,
                    'Total Trades': total_trades,
                    'Max MaxDD (%)': max_max_dd
                })
                results.append(result_entry)

    finally:
        # Restore original settings
        with open(SETTINGS_PATH, 'w') as f:
            f.write(original_settings)

    # Save and display results
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values(by='Avg PF', ascending=False)
        df.to_csv("scratch/batch_backtests/bb_optimization_results.csv", index=False)
        
        print("\n" + "="*50)
        print(f"{'TOP 10 OPTIMIZED SETTINGS':^50}")
        print("="*50)
        print(df.head(10).to_string(index=False))
        print("="*50)
    else:
        print("No valid results found.")

if __name__ == "__main__":
    main()
