import os
import subprocess
import re
import pandas as pd
import yaml
import concurrent.futures
from tqdm import tqdm
from itertools import product
from pathlib import Path

# Configuration
DATA_DIR = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H"
SETTINGS_PATH = r"d:\Workspace\delta-exchange-alog\config\settings.yaml"
PYTHON_EXE = "python" # Assumes python is in path or venv is active

PIPPIN_FILE = os.path.join(DATA_DIR, "PIPPINUSD_1h.csv")

# Parameter Grid
GRID = {
    'enter_period': [15, 20, 25, 30],
    'exit_period': [5, 10, 15],
    'risk_pct': [0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05]
}

def update_settings(params):
    """Update settings.yaml with specific parameters."""
    with open(SETTINGS_PATH, 'r') as f:
        config = yaml.safe_load(f)
    
    # Target the donchian_channel strategy
    dc_cfg = config['strategies']['donchian_channel']
    dc_cfg['enter_period'] = params['enter_period']
    dc_cfg['exit_period'] = params['exit_period']
    
    # Update risk management
    rm_cfg = config['risk_management']
    rm_cfg['risk_pct_per_trade'] = params['risk_pct']
    rm_cfg['sizing_method'] = "fractional"
    
    # Ensure compounding is enabled for growth assessment
    config['backtesting']['use_compounding'] = True

    with open(SETTINGS_PATH, 'w') as f:
        yaml.safe_dump(config, f)

def parse_output(output):
    try:
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', ''))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        pf = float(re.search(r'Profit Factor:\s+([0-9,.-]+)', output).group(1))
        return {
            'sharpe': sharpe, 
            'return': return_pct, 
            'trades': trades, 
            'max_dd': max_dd,
            'pf': pf
        }
    except Exception as e:
        # print(f"Error parsing: {e}")
        return None

def run_backtest():
    cmd = [
        PYTHON_EXE, "run_backtest.py", 
        "--strategy", "donchian-channel",
        "--symbol", "PIPPINUSD", 
        "--file", PIPPIN_FILE, 
        "--candle-type", "heikin_ashi"
    ]
    try:
        # Use shell=True on Windows if 'python' refers to a script or alias
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return parse_output(result.stdout)
        else:
            # print(f"Error running: {result.stderr}")
            pass
    except Exception as e:
        # print(f"Process error: {e}")
        pass
    return None

def main():
    if not os.path.exists("scratch/batch_backtests"):
        os.makedirs("scratch/batch_backtests")

    # Generate all combinations
    keys = GRID.keys()
    combos = [dict(zip(keys, v)) for v in product(*GRID.values())]
    print(f"Starting PIPPIN optimization with {len(combos)} combinations.")

    results = []
    
    # Backup original settings
    with open(SETTINGS_PATH, 'r') as f:
        original_settings = f.read()

    try:
        # We run sequentially because run_backtest.py isn't thread-safe regarding settings.yaml
        for params in tqdm(combos, desc="Optimizing PIPPIN"):
            update_settings(params)
            res = run_backtest()
            if res:
                # Apply 20% Drawdown Constraint
                if res['max_dd'] <= 20.0:
                    entry = params.copy()
                    entry.update({
                        'Sharpe': res['sharpe'],
                        'Return %': res['return'],
                        'MaxDD %': res['max_dd'],
                        'Profit Factor': res['pf'],
                        'Trades': res['trades']
                    })
                    results.append(entry)

    finally:
        # Restore original settings
        with open(SETTINGS_PATH, 'w') as f:
            f.write(original_settings)

    # Save and display results
    if results:
        df = pd.DataFrame(results)
        # Prioritize Sharpe Ratio
        df = df.sort_values(by='Sharpe', ascending=False)
        df.to_csv("scratch/batch_backtests/pippin_optimization_results.csv", index=False)
        
        print("\n" + "="*80)
        print(f"{'TOP 10 OPTIMIZED SETTINGS FOR PIPPIN (Max Sharpe, DD < 20%)':^80}")
        print("="*80)
        print(df.head(10).to_string(index=False))
        print("="*80)
        
        best = df.iloc[0]
        print(f"\nCHAMPION CONFIGURATION:")
        print(f"Risk: {best['risk_pct']*100}% | Lookback: {best['enter_period']}/{best['exit_period']}")
        print(f"Sharpe: {best['Sharpe']:.2f} | Return: {best['Return %']:.2f}% | MaxDD: {best['MaxDD %']:.2f}%")
    else:
        print("No valid results found within drawdown constraints.")

if __name__ == "__main__":
    main()
