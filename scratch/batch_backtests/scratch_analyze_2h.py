import pandas as pd
import glob
import os

files = glob.glob('results_2h_*.csv')

dfs = []
for f in files:
    # file format: results_2h_{candle}_{pct}.csv
    parts = f.replace('.csv', '').split('_')
    # parts: ['results', '2h', 'standard/heikin', 'ashi', '0.20']
    
    if 'heikin_ashi' in f:
        candle = 'heikin_ashi'
        pct = parts[-1]
    else:
        candle = 'standard'
        pct = parts[-1]
        
    df = pd.read_csv(f)
    df['Scenario'] = f"{candle}_{pct}"
    df['Candle'] = candle
    df['StopLoss'] = pct
    dfs.append(df)

all_data = pd.concat(dfs, ignore_index=True)

# Let's aggregate by Scenario
summary = all_data.groupby('Scenario').agg({
    'Return (%)': 'mean',
    'Sharpe': 'mean',
    'Max DD (%)': 'mean',
    'Trades': 'mean',
    'Win Rate (%)': 'mean'
}).reset_index()

print("AVERAGE PERFORMANCE ACROSS ALL COINS BY SCENARIO:")
print(summary.sort_values(by='Sharpe', ascending=False).to_string(index=False))

print("\n---------------------------------------------------------")
print("BEST INDIVIDUAL PERFORMERS OVERALL (Min 30 Trades, Max DD < 40%)")
candidates = all_data[(all_data['Trades'] >= 30) & (all_data['Max DD (%)'] <= 40)]
top_performers = candidates.sort_values(by='Sharpe', ascending=False).head(15)
print(top_performers[['Symbol', 'Scenario', 'Return (%)', 'Sharpe', 'Sortino', 'Max DD (%)', 'Win Rate (%)']].to_string(index=False))

print("\n---------------------------------------------------------")
# Find best optimal scenario count
# For each coin, which scenario gave the best Sharpe?
idx = all_data.groupby('Symbol')['Sharpe'].idxmax()
best_scenarios_per_coin = all_data.loc[idx]
wins_by_scenario = best_scenarios_per_coin['Scenario'].value_counts()
print("NUMBER OF COINS WHERE THIS SCENARIO WAS THE #1 PERFORMER:")
print(wins_by_scenario.to_string())
