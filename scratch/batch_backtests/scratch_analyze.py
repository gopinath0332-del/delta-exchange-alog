import pandas as pd

# Load
df_20 = pd.read_csv('results_ha_0.20.csv')
df_25 = pd.read_csv('results_ha_0.25.csv')

# Merge
df = pd.merge(df_20, df_25, on='Symbol', suffixes=('_0.20', '_0.25'))

# Calculate improvements
df['Sharpe_Diff'] = df['Sharpe_0.20'] - df['Sharpe_0.25']
df['Sortino_Diff'] = df['Sortino_0.20'] - df['Sortino_0.25']
df['Return_Diff'] = df['Return (%)_0.20'] - df['Return (%)_0.25']

# Print Top 5 by Sharpe 0.20
top_20 = df.sort_values(by='Sharpe_0.20', ascending=False).head(10)
print("\n--- TOP 10 COINS (0.20 Stop Loss) by Sharpe ---")
print(top_20[['Symbol', 'Return (%)_0.20', 'Sharpe_0.20', 'Sortino_0.20', 'Max DD (%)_0.20', 'Return (%)_0.25', 'Sharpe_0.25']].to_string(index=False))

# Best by Return
top_ret = df.sort_values(by='Return (%)_0.20', ascending=False).head(5)
print("\n--- TOP 5 COINS by Total Return (0.20 Stop Loss) ---")
print(top_ret[['Symbol', 'Return (%)_0.20', 'Sharpe_0.20', 'Sortino_0.20', 'Max DD (%)_0.20']].to_string(index=False))

# Which coin should we choose? Let's recommend the one with the highest Sortino/Sharpe while maintaining realistic drawdowns (<40%).
candidates = df[(df['Max DD (%)_0.20'] < 40) & (df['Trades_0.20'] >= 50)]
best = candidates.sort_values(by='Sortino_0.20', ascending=False).head(5)
print("\n--- TOP RECOMMENDATIONS (Max DD < 40%, Trades >= 50) ---")
print(best[['Symbol', 'Return (%)_0.20', 'Sharpe_0.20', 'Sortino_0.20', 'Max DD (%)_0.20', 'Win Rate (%)_0.20']].to_string(index=False))
