import os
import subprocess
import re
import pandas as pd
import yaml
from tqdm import tqdm

# Configuration
DATA_DIR = r"D:\Workspace\crypto-backtest-data"
SETTINGS_PATH = r"d:\Workspace\delta-exchange-alog\config\settings.yaml"
PYTHON_EXE = "python" # Assumes venv is active

# Specific Coin/TF from settings.yaml multi_coin donchian_channel
COINS = [
    {"symbol": "BIO", "full_symbol": "BIOUSD", "tf": "4h", "path": os.path.join(DATA_DIR, "delta_crypto_data_4H", "BIOUSD_4h.csv")},
    {"symbol": "PIPPIN", "full_symbol": "PIPPINUSD", "tf": "1h", "path": os.path.join(DATA_DIR, "delta_crypto_data_1H", "PIPPINUSD_1h.csv")},
    {"symbol": "BEAT", "full_symbol": "BEATUSD", "tf": "2h", "path": os.path.join(DATA_DIR, "delta_crypto_data_2H", "BEATUSD_2h.csv")}
]

RISK_LEVELS = [0.01, 0.02, 0.04, 0.05]

def update_risk(risk_pct):
    with open(SETTINGS_PATH, 'r') as f:
        config = yaml.safe_load(f)
    
    config['risk_management']['risk_pct_per_trade'] = risk_pct
    config['backtesting']['use_compounding'] = True
    config['risk_management']['sizing_method'] = "fractional"

    with open(SETTINGS_PATH, 'w') as f:
        yaml.safe_dump(config, f)

def parse_output(output):
    try:
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1).replace(',', ''))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        return {'sharpe': sharpe, 'return': return_pct, 'max_dd': max_dd}
    except:
        return None

def run_backtest(coin):
    cmd = [
        PYTHON_EXE, "run_backtest.py", 
        "--strategy", "donchian-channel",
        "--symbol", coin['full_symbol'], 
        "--file", coin['path'], 
        "--candle-type", "heikin_ashi" if coin['symbol'] != "BIO" else "standard"
    ]
    # Note: BIO uses "standard" in the multi_coin config in settings.yaml
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return parse_output(result.stdout)
    except:
        pass
    return None

def main():
    results = []
    
    # Backup settings
    with open(SETTINGS_PATH, 'r') as f:
        original_settings = f.read()

    try:
        for risk in RISK_LEVELS:
            print(f"\nTesting Risk: {risk*100}%")
            update_risk(risk)
            
            for coin in COINS:
                print(f"  Analysing {coin['symbol']} ({coin['tf']})...")
                res = run_backtest(coin)
                if res:
                    results.append({
                        'Coin': coin['symbol'],
                        'TF': coin['tf'],
                        'Risk %': risk * 100,
                        'Return %': res['return'],
                        'MaxDD %': res['max_dd'],
                        'Sharpe': res['sharpe']
                    })
    finally:
        # Restore
        with open(SETTINGS_PATH, 'w') as f:
            f.write(original_settings)

    if results:
        df = pd.DataFrame(results)
        df.to_csv("scratch/multi_risk_comparison.csv", index=False)
        print("\n" + "="*60)
        print(f"{'MULTI-COIN RISK COMPARISON':^60}")
        print("="*60)
        print(df.to_string(index=False))
        print("="*60)
    else:
        print("No results found.")

if __name__ == "__main__":
    main()
