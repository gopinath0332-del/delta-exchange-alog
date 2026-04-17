import os
import subprocess
import re
import pandas as pd
import concurrent.futures

DATA_DIR = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_1H"
SETTINGS_PATH = r"D:\Workspace\delta-exchange-alog\config\settings.yaml"

def modify_settings(pct):
    with open(SETTINGS_PATH, 'r') as f:
        content = f.read()
    
    new_content = re.sub(
        r'(stop_loss_pct:\s*)[0-9.]+',
        rf'\g<1>{pct}',
        content
    )
    with open(SETTINGS_PATH, 'w') as f:
        f.write(new_content)

def parse_output(output, symbol):
    try:
        final_capital = float(re.search(r'Final Capital:\s+\$([0-9,.]+)', output).group(1).replace(',', ''))
        return_pct = float(re.search(r'Total Return:\s+([+-]?[0-9,.]+)%', output).group(1))
        sharpe = float(re.search(r'Sharpe Ratio:\s+([0-9,.-]+)', output).group(1))
        sortino = float(re.search(r'Sortino Ratio:\s+([0-9,.-]+)', output).group(1))
        max_dd = float(re.search(r'Max Drawdown:\s+([0-9,.]+)%', output).group(1))
        trades = int(re.search(r'Total Trades:\s+([0-9]+)', output).group(1))
        win_rate = float(re.search(r'Win Rate:\s+([0-9,.]+)%', output).group(1))
        return {
            'Symbol': symbol, 'Return (%)': return_pct, 'Sharpe': sharpe, 
            'Sortino': sortino, 'Max DD (%)': max_dd, 'Trades': trades, 'Win Rate (%)': win_rate
        }
    except:
        return None

def run_backtest(file_path, candle_type):
    filename = os.path.basename(file_path)
    symbol = filename.split('_')[0]
    cmd = [
        r"venv\Scripts\python.exe", "run_backtest.py", "--strategy", "donchian_channel",
        "--symbol", symbol, "--file", file_path, "--candle-type", candle_type
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return parse_output(result.stdout, symbol)
    except:
        pass
    return None

def main():
    files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    modify_settings("0.20")
    for candle in ['standard', 'heikin_ashi']:
        out_file = f"scratch/batch_backtests/results_1h_{candle}_0.20.csv"
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            future_to_file = {executor.submit(run_backtest, f, candle): f for f in files}
            for future in concurrent.futures.as_completed(future_to_file):
                res = future.result()
                if res: results.append(res)
        pd.DataFrame(results).to_csv(out_file, index=False)
        print(f"Saved 1H {candle} to {out_file}")

if __name__ == "__main__":
    main()
