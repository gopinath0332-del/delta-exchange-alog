import os
import subprocess
import re
import pandas as pd
import yaml
from tqdm import tqdm

# Configuration
DATA_DIR = r"D:\Workspace\crypto-backtest-data"
SETTINGS_PATH = r"d:\Workspace\delta-exchange-alog\config\settings.yaml"
PYTHON_EXE = "python"

# Blue Chip Settings
CANDIDATES = [
    ('BTC', 'BTCUSD', '1h'), ('BTC', 'BTCUSD', '2h'), ('BTC', 'BTCUSD', '4h'),
    ('ETH', 'ETHUSD', '1h'), ('ETH', 'ETHUSD', '2h'), ('ETH', 'ETHUSD', '4h'),
    ('SOL', 'SOLUSD', '1h'), ('SOL', 'SOLUSD', '2h'), ('SOL', 'SOLUSD', '4h')
]

RISK_LEVELS = [0.02, 0.05]

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
        return {'Sharpe': sharpe, 'Return %': return_pct, 'MaxDD %': max_dd}
    except:
        return None

def run_backtest(symbol, tf):
    data_path = os.path.join(DATA_DIR, f"delta_crypto_data_{tf.upper()}", f"{symbol}_{tf.lower()}.csv")
    cmd = [PYTHON_EXE, "run_backtest.py", "--strategy", "donchian-channel", "--symbol", symbol, "--file", data_path, "--candle-type", "standard"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return parse_output(result.stdout)
    except:
        pass
    return None

def main():
    results = []
    # Backup
    with open(SETTINGS_PATH, 'r') as f:
        original_settings = f.read()

    try:
        for risk in RISK_LEVELS:
            update_risk(risk)
            for symbol, full_symbol, tf in tqdm(CANDIDATES, desc=f"Risk {risk*100}%"):
                res = run_backtest(full_symbol, tf)
                if res:
                    results.append({
                        'Symbol': symbol,
                        'TF': tf,
                        'Risk %': risk * 100,
                        'Return %': res['Return %'],
                        'MaxDD %': res['MaxDD %'],
                        'Sharpe': res['Sharpe']
                    })

    finally:
        with open(SETTINGS_PATH, 'w') as f:
            f.write(original_settings)

    if results:
        df = pd.DataFrame(results)
        df.to_csv("scratch/bluechip_risk_results.csv", index=False)
        print("\n" + "="*80)
        print(f"{'BLUE CHIP RISK COMPARISON (2% VS 5%)':^80}")
        print("="*80)
        print(df.to_string(index=False))
        print("="*80)

if __name__ == "__main__":
    main()
