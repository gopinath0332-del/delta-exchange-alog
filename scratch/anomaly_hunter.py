import pandas as pd

def find_anomalies(timeframe):
    if timeframe == '4h':
        ha_file = 'scratch/batch_backtests/results_4h_heikin_ashi_0.20.csv'
        std_file = 'scratch/batch_backtests/results_4h_standard_0.20.csv'
    elif timeframe == '2h':
        ha_file = 'scratch/batch_backtests/results_2h_heikin_ashi_0.20.csv'
        std_file = 'scratch/batch_backtests/results_2h_standard_0.20.csv'

    try:
        df_ha = pd.read_csv(ha_file)
        df_std = pd.read_csv(std_file)
    except FileNotFoundError:
        return

    # Merge on Symbol
    df = pd.merge(df_ha, df_std, on='Symbol', suffixes=('_HA', '_STD'))
    
    # Filter where Standard outperforms HA
    # We will look for coins where Standard Shape > HA Sharpe AND Standard Return > HA Return
    # AND trades are reasonable (> 15 for 4h, > 30 for 2h)
    min_trades = 15 if timeframe == '4h' else 30
    
    anomalies = df[
        (df['Sharpe_STD'] > df['Sharpe_HA']) & 
        (df['Return (%)_STD'] > df['Return (%)_HA']) &
        (df['Trades_STD'] >= min_trades)
    ].copy()
    
    # Sort by how much better STD is over HA (Sharpe difference)
    anomalies['Sharpe_Advantage'] = anomalies['Sharpe_STD'] - anomalies['Sharpe_HA']
    anomalies = anomalies.sort_values(by='Sharpe_Advantage', ascending=False)
    
    print(f"\n=======================================================")
    print(f"ANOMALIES FOUND ON {timeframe.upper()} TIMEFRAME")
    print(f"Number of coins where Standard > Heikin Ashi: {len(anomalies)} / {len(df)}")
    print(f"=======================================================")
    
    if len(anomalies) > 0:
        # Display top 10
        display_cols = ['Symbol', 'Return (%)_STD', 'Return (%)_HA', 'Sharpe_STD', 'Sharpe_HA', 'Max DD (%)_STD', 'Max DD (%)_HA']
        print(anomalies.head(10)[display_cols].to_string(index=False))

find_anomalies('4h')
find_anomalies('2h')
