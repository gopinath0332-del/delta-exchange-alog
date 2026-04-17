import os
import subprocess
import pandas as pd
import yaml
from tqdm import tqdm

SETTINGS_PATH = r"d:\Workspace\delta-exchange-alog\config\settings.yaml"
PYTHON_EXE = r"venv\Scripts\python.exe"
BATCH_SCRIPT = r"scratch\bb_backtest_batch.py" # Already has the logic for 181 coins

def run_scenario(sl_value):
    print(f"\n>>> Running Scenario: Stop Loss = {sl_value*100}%")
    
    # 1. Update settings.yaml
    with open(SETTINGS_PATH, 'r') as f:
        config = yaml.safe_load(f)
    config['strategies']['bb_breakout']['stop_loss_pct'] = sl_value
    with open(SETTINGS_PATH, 'w') as f:
        yaml.safe_dump(config, f)
    
    # 2. Run batch backtest (only HA for this comparison as it's the winner)
    # We'll modify the batch script temporarily to ONLY run heikin_ashi and save to a specific name
    cmd = [PYTHON_EXE, BATCH_SCRIPT]
    subprocess.run(cmd, capture_output=True, text=True) # Result is saved to scratch/batch_backtests/bb_results_1h_heikin_ashi.csv
    
    # 3. Rename result for this scenario
    final_name = f"scratch/batch_backtests/bb_results_sl_{int(sl_value*100)}.csv"
    if os.path.exists("scratch/batch_backtests/bb_results_1h_heikin_ashi.csv"):
        os.replace("scratch/batch_backtests/bb_results_1h_heikin_ashi.csv", final_name)
    return final_name

def analyze_scenarios(files):
    summary = []
    for sl, file in files.items():
        df = pd.read_csv(file)
        # Global metrics
        avg_pf = df['Profit Factor'].mean()
        avg_return = df['Return (%)'].mean()
        avg_sharpe = df['Sharpe'].mean()
        max_dd = df['Max DD (%)'].max()
        profitable_coins = len(df[df['Profit Factor'] > 1.0])
        total_trades = df['Trades'].sum()
        
        summary.append({
            'SL %': sl,
            'Avg PF': avg_pf,
            'Avg Return %': avg_return,
            'Avg Sharpe': avg_sharpe,
            'Global Max DD %': max_dd,
            'Profitable Coins': f"{profitable_coins}/181",
            'Total Trades': total_trades
        })
    
    summary_df = pd.DataFrame(summary)
    print("\n" + "="*80)
    print(f"{'STOP LOSS SCENARIO COMPARISON (Global Strategy Performance)':^80}")
    print("="*80)
    print(summary_df.to_string(index=False))
    print("="*80)
    summary_df.to_csv("scratch/batch_backtests/sl_comparison_summary.csv", index=False)

def main():
    # Backup
    with open(SETTINGS_PATH, 'r') as f:
        original = f.read()
    
    try:
        scenarios = {
            "15%": 0.15,
            "20%": 0.20,
            "25%": 0.25
        }
        files = {}
        for label, val in scenarios.items():
            files[label] = run_scenario(val)
        
        analyze_scenarios(files)
        
    finally:
        with open(SETTINGS_PATH, 'w') as f:
            f.write(original)

if __name__ == "__main__":
    main()
