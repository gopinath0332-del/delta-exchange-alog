import pandas as pd
import glob
import os

def load_020_data():
    files = glob.glob('scratch/batch_backtests/results_*_*_0.20.csv')
    dfs = []
    for f in files:
        basename = os.path.basename(f).replace('.csv', '')
        parts = basename.split('_')
        timeframe = parts[1]
        candle = 'heikin_ashi' if 'heikin_ashi' in basename else 'standard'
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

# Broaden criteria: Score coins based on how many "Good" configs they hit
# A config is "Good" if Return > 0 and Sharpe > 1.0 (Lowered from 1.5)
def is_good(row):
    return (row['Return (%)'] > 0) and (row['Sharpe'] >= 1.0) and (row['Max DD (%)'] <= 60)

df['Good'] = df.apply(is_good, axis=1)

# Count 'Good' setups per symbol
summary = df.groupby('Symbol')['Good'].sum().reset_index()
summary.columns = ['Symbol', 'Good_Count']

# Get details for the best ones
top_symbols = summary.sort_values(by='Good_Count', ascending=False).head(10)

print("\n=======================================================")
print(f"MOST RELIABLE COINS ACROSS ALL ENVIRONMENTS")
print("Conditions: Return > 0%, Sharpe >= 1.0, Max DD <= 60%")
print("Max Good Count possible: 6 (1h/2h/4h x HA/Standard)")
print("=======================================================")

for _, row in top_symbols.iterrows():
    symbol = row['Symbol']
    count = row['Good_Count']
    print(f"\n--- {symbol} (Hits: {count}/6) ---")
    coin_data = df[df['Symbol'] == symbol].sort_values(by=['Timeframe', 'Candle'])
    print(coin_data[['Config', 'Return (%)', 'Sharpe', 'Max DD (%)', 'Win Rate (%)']].to_string(index=False))
