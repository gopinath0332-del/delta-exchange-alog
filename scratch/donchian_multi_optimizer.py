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
DATA_DIR = Path(r"D:\Workspace\crypto-backtest-data")
SETTINGS_PATH = Path(r"d:\Workspace\delta-exchange-alog\config\settings.yaml")
PYTHON_EXE = "python"

# Shortlisted Candidates from Screening
# Format: (Symbol, FullSymbol, TF)
CANDIDATES = [
    ('RIVER', 'RIVERUSD', '1h'),
    ('PIPPIN', 'PIPPINUSD', '1h'),
    ('TSLAX', 'TSLAXUSD', '1h'),
    ('COINX', 'COINXUSD', '1h'),
    ('GOOGLX', 'GOOGLXUSD', '2h'),
    ('DOT', 'DOTUSD', '1h'),
    ('BEAT', 'BEATUSD', '1h'),
    ('ARC', 'ARCUSD', '1h'),
    ('METAX', 'METAXUSD', '1h'),
    ('BTC', 'BTCUSD', '2h'),
    ('ETH', 'ETHUSD', '2h'),
    ('BIO', 'BIOUSD', '2h'),
    ('BERA', 'BERAUSD', '1h'),
    ('PAXG', 'PAXGUSD', '2h'),
    ('SUI', 'SUIUSD', '1h'),
    ('XRP', 'XRPUSD', '1h'),
    ('SOL', 'SOLUSD', '1h'),
    ('EVAA', 'EVAAUSD', '1h'),
    ('ETC', 'ETCUSD', '1h'),
    ('DOGE', 'DOGEUSD', '1h')
]

# Parameter Grid (Fixed Exit=10, sweeping Enter/Risk)
GRID = {
    'enter_period': [15, 20, 25, 30],
    'risk_pct': [0.01, 0.02, 0.03, 0.04, 0.05]
}

def update_settings(params):
    with open(SETTINGS_PATH, 'r') as f:
        config = yaml.safe_load(f)
    
    dc_cfg = config['strategies']['donchian_channel']
    dc_cfg['enter_period'] = params['enter_period']
    dc_cfg['exit_period'] = 10 # Fixed as requested
    
    rm_cfg = config['risk_management']
    rm_cfg['risk_pct_per_trade'] = params['risk_pct']
    
    config['backtesting']['use_compounding'] = True

    with open(SETTINGS_PATH, 'w') as f:
        yaml.safe_dump(config, f)

def parse_output(output):
    try:
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', ''))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        pf = float(re.search(r'Profit Factor:\s+([0-9,.-]+)', output).group(1))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        return {
            'Sharpe': sharpe, 
            'Return %': return_pct, 
            'MaxDD %': max_dd,
            'PF': pf,
            'Trades': trades
        }
    except:
        return None

def run_backtest(symbol, full_symbol, tf):
    data_path = DATA_DIR / f"delta_crypto_data_{tf.upper()}" / f"{full_symbol}_{tf.lower()}.csv"
    if not data_path.exists():
        return None

    cmd = [
        PYTHON_EXE, "run_backtest.py", 
        "--strategy", "donchian-channel",
        "--symbol", full_symbol, 
        "--file", str(data_path), 
        "--candle-type", "heikin_ashi"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return parse_output(result.stdout)
    except:
        pass
    return None

def main():
    if not os.path.exists("scratch/batch_backtests"):
        os.makedirs("scratch/batch_backtests")

    # Generate all setting combinations
    keys = GRID.keys()
    combos = [dict(zip(keys, v)) for v in product(*GRID.values())]
    
    # Final results list
    champion_list = []
    
    # Backup original settings
    with open(SETTINGS_PATH, 'r') as f:
        original_settings = f.read()

    print(f"Starting Depth Optimization for {len(CANDIDATES)} candidates.")

    try:
        for symbol, full_symbol, tf in tqdm(CANDIDATES, desc="Iterating Candidates"):
            best_sharpe = -1
            best_config = None
            
            # Sub-sweep for THIS coin
            for params in combos:
                update_settings(params)
                res = run_backtest(symbol, full_symbol, tf)
                
                if res:
                    # Apply 20% drawdown constraint
                    if res['MaxDD %'] <= 20.0:
                        if res['Sharpe'] > best_sharpe:
                            best_sharpe = res['Sharpe']
                            best_config = {
                                'Symbol': symbol,
                                'TF': tf,
                                'Opt Enter': params['enter_period'],
                                'Opt Risk': params['risk_pct'],
                                'Sharpe': res['Sharpe'],
                                'Return %': res['Return %'],
                                'MaxDD %': res['MaxDD %'],
                                'PF': res['PF'],
                                'Trades': res['Trades']
                            }
            
            if best_config:
                champion_list.append(best_config)
                # Periodic save
                pd.DataFrame(champion_list).to_csv("scratch/batch_backtests/depth_champion_results.csv", index=False)

    finally:
        # Restore original settings
        with open(SETTINGS_PATH, 'w') as f:
            f.write(original_settings)

    if champion_list:
        df = pd.DataFrame(champion_list)
        df = df.sort_values(by='Sharpe', ascending=False)
        df.to_csv("scratch/batch_backtests/donchian_final_leaderboard.csv", index=False)
        
        print("\n" + "="*100)
        print(f"{'FINAL CHAMPION LEADERBOARD (Optimized Risk & Period, Max Sharpe, DD < 20%)':^100}")
        print("="*100)
        print(df.to_string(index=False))
        print("="*100)
    else:
        print("No optimized combinations found within drawdown constraints.")

if __name__ == "__main__":
    main()
