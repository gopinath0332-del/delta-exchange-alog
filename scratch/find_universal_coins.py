import pandas as pd
import glob
import os

def load_020_data():
    files = glob.glob('scratch/batch_backtests/results_*_*_0.20.csv')
    dfs = []
    for f in files:
        basename = os.path.basename(f).replace('.csv', '')
        # Name: results_{timeframe}_{candle}_0.20
        # e.g., results_1h_heikin_ashi_0.20
        parts = basename.split('_')
        timeframe = parts[1]
        if 'heikin_ashi' in basename:
            candle = 'heikin_ashi'
        else:
            candle = 'standard'
            
        try:
            df = pd.read_csv(f)
            df['Timeframe'] = timeframe
            df['Candle'] = candle
            df['Config'] = f"{timeframe}_{candle}"
            dfs.append(df)
        except Exception as e:
            print(f"Error loading {f}: {e}")
    
    return pd.concat(dfs, ignore_index=True)

df = load_020_data()

# We need coins that exist in all 6 Configs (1h_std, 1h_ha, 2h_std, 2h_ha, 4h_std, 4h_ha)
# and meet a "good performance" threshold in ALL OF THEM.

# "Good" Definition:
def is_good(row):
    return (row['Return (%)'] > 50) and (row['Sharpe'] >= 1.5) and (row['Max DD (%)'] <= 50) and (row['Trades'] >= 15)

df['Good'] = df.apply(is_good, axis=1)

# Group by Symbol
grouped = df.groupby('Symbol')

universal_performers = []

configs_needed = {'1h_standard', '1h_heikin_ashi', '2h_standard', '2h_heikin_ashi', '4h_standard', '4h_heikin_ashi'}

for symbol, group in grouped:
    # Get all configs this coin passed the 'Good' condition on
    good_configs = set(group[group['Good']]['Config'])
    
    # Are all 6 needed configs in the set of good configs?
    if configs_needed.issubset(good_configs):
        universal_performers.append(symbol)

print("\n=======================================================")
print(f"COINS THAT PERFORM 'GOOD' ACROSS ALL 6 SETUPS")
print("Thresholds: Return > 50%, Sharpe >= 1.5, Max DD <= 50%, Trades >= 15")
print("Setups: 1H, 2H, 4H on BOTH Standard and Heikin-Ashi (Stop Loss 0.20)")
print("=======================================================")

if not universal_performers:
    print("Zero coins met these strict criteria across all environments.")
else:
    for symbol in universal_performers:
        print(f"\n--- {symbol} ---")
        coin_data = df[df['Symbol'] == symbol].sort_values(by=['Timeframe', 'Candle'])
        print(coin_data[['Config', 'Return (%)', 'Sharpe', 'Max DD (%)', 'Win Rate (%)']].to_string(index=False))
