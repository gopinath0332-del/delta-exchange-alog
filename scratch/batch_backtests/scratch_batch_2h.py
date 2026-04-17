import os
import subprocess
import re
import pandas as pd
import concurrent.futures
import time

DATA_DIR = r"D:\Workspace\crypto-backtest-data\delta_crypto_data_2H"
SETTINGS_PATH = r"D:\Workspace\delta-exchange-alog\config\settings.yaml"

# Global state to track how many files are done per scenario
totals_done = 0

def modify_settings(pct):
    with open(SETTINGS_PATH, 'r') as f:
        content = f.read()
    
    # Regex to find and replace stop_loss_pct under donchian_channel
    if pct is None:
        # None: comment out the stop_loss_pct line using regex lookahead to make sure it's the right block
        # We'll just replace with a `# stop_loss_pct: ...` placeholder
        new_content = re.sub(
            r'([ \t]*)(stop_loss_pct:\s*[0-9.]+\s*#.*)',
            r'\g<1># \g<2>',
            content
        )
    else:
        # First uncomment if commented
        content = re.sub(
            r'([ \t]*)#\s*(stop_loss_pct:\s*[0-9.]+\s*#.*)',
            r'\g<1>\g<2>',
            content
        )
        new_content = re.sub(
            r'(stop_loss_pct:\s*)[0-9.]+',
            rf'\g<1>{pct}',
            content
        )
    with open(SETTINGS_PATH, 'w') as f:
        f.write(new_content)
    print(f"[SETTING] Updated settings.yaml with stop_loss_pct: {pct}")

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
        return None

def run_backtest(file_path, candle_type):
    filename = os.path.basename(file_path)
    symbol = filename.split('_')[0]
    
    cmd = [
        r"venv\Scripts\python.exe",
        "run_backtest.py",
        "--strategy", "donchian_channel",
        "--symbol", symbol,
        "--file", file_path,
        "--timeframe", "2h",
        "--candle-type", candle_type
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return None
        parsed = parse_output(result.stdout, symbol)
        return parsed
    except Exception as e:
        return None

def main():
    files = [os.path.join(DATA_DIR, f) for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    print(f"Found {len(files)} 2H files to process.")
    
    # scenarios
    stop_loss_pcts = ['0.20', '0.25', '0.30', '0.50', None]
    candle_styles = ['standard', 'heikin_ashi']
    
    all_dfs = {}
    
    for candle in candle_styles:
        for pct in stop_loss_pcts:
            modify_settings(pct)
            
            # format naming convention
            pct_str = "None" if pct is None else pct
            scenario_name = f"{candle}_{pct_str}"
            out_file = f"results_2h_{scenario_name}.csv"
            
            print(f"\n--- Running SCENARIO: {scenario_name} ---")
            
            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                future_to_file = {executor.submit(run_backtest, f, candle): f for f in files}
                count = 0
                for future in concurrent.futures.as_completed(future_to_file):
                    res = future.result()
                    if res:
                        results.append(res)
                    count += 1
                    if count % 30 == 0:
                        print(f"[{scenario_name}] Processed {count}/{len(files)}")
                        
            df = pd.DataFrame(results)
            df.to_csv(out_file, index=False)
            print(f"Saved {len(df)} results to {out_file}")
            all_dfs[scenario_name] = df

    # Restore setting
    modify_settings('0.20')

if __name__ == "__main__":
    main()
