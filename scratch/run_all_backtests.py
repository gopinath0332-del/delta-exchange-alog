import subprocess
import os
import shutil
from pathlib import Path

# Paths
WORKSPACE = r"d:\Workspace\delta-exchange-alog"
DATA_BASE = r"D:\Workspace\crypto-backtest-data"
FINAL_REPORTS = os.path.join(WORKSPACE, "reports_all")

if not os.path.exists(FINAL_REPORTS):
    os.makedirs(FINAL_REPORTS)

CONFIGS = [
    {"tf": "1h", "folder": os.path.join(DATA_BASE, "delta_crypto_data_1H")},
    {"tf": "2h", "folder": os.path.join(DATA_BASE, "delta_crypto_data_2H")},
    {"tf": "4h", "folder": os.path.join(DATA_BASE, "delta_crypto_data_4H")},
    {"tf": "6h", "folder": os.path.join(DATA_BASE, "delta_crypto_data_6h", "delta_crypto_data")},
]

SYMBOLS = ["SLVONUSD", "PAXGUSD"]
STRATEGY = "donchian-channel"
CANDLE_TYPE = "heikin_ashi"

def run_backtest(symbol, timeframe, folder):
    print(f"\n>>> Running backtest for {symbol} on {timeframe}...")
    cmd = [
        "python", "run_backtest.py",
        "--strategy", STRATEGY,
        "--symbol", symbol,
        "--timeframe", timeframe,
        "--data-folder", folder,
        "--candle-type", CANDLE_TYPE
    ]
    try:
        result = subprocess.run(cmd, cwd=WORKSPACE, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error running backtest for {symbol} {timeframe}:")
            print(result.stderr)
        else:
            # Capture results from stdout
            print(result.stdout[-1000:]) # last 1000 chars should have the summary
            
            # Copy reports to final destination
            reports_dir = os.path.join(WORKSPACE, "reports")
            for filename in os.listdir(reports_dir):
                if filename.startswith(symbol) and timeframe in filename:
                    shutil.copy(os.path.join(reports_dir, filename), os.path.join(FINAL_REPORTS, filename))
                    print(f"Saved {filename} to {FINAL_REPORTS}")
            
    except Exception as e:
        print(f"Exception occurred: {e}")

if __name__ == "__main__":
    for config in CONFIGS:
        for symbol in SYMBOLS:
            run_backtest(symbol, config["tf"], config["folder"])
