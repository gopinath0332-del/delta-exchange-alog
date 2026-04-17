import pandas as pd

def analyze():
    df = pd.read_csv(r'd:\Workspace\delta-exchange-alog\scratch\batch_backtests\bb_results_2H_final.csv')
    df = df[df['Trades'] >= 5]
    
    # Ranks
    df['PF_Rank'] = df['Profit Factor'].rank(ascending=False)
    df['Sharpe_Rank'] = df['Sharpe'].rank(ascending=False)
    df['Return_Rank'] = df['Return (%)'].rank(ascending=False)
    
    sol_rows = df[df['Symbol'] == 'SOLUSD']
    if sol_rows.empty:
        print("SOL not found in the filtered results.")
        return
        
    sol = sol_rows.iloc[0]
    top_10 = df.sort_values('Profit Factor', ascending=False).head(10)
    batch_avg = df.mean(numeric_only=True)
    
    print('\nSOLUSD POSITION:')
    print(f'Profit Factor Rank: {int(sol["PF_Rank"])} / {len(df)}')
    print(f'Sharpe Ratio Rank:  {int(sol["Sharpe_Rank"])} / {len(df)}')
    print(f'Return Rank:        {int(sol["Return_Rank"])} / {len(df)}')
    
    print('\nDETAILED COMPARISON:')
    data = {
        'Metric': ['Profit Factor', 'Sharpe Ratio', 'Return (%)', 'Max DD (%)', 'Win Rate (%)'],
        'SOLUSD': [sol['Profit Factor'], sol['Sharpe'], sol['Return (%)'], sol['Max DD (%)'], sol['Win Rate (%)']],
        'Top 10 Avg': [top_10['Profit Factor'].mean(), top_10['Sharpe'].mean(), top_10['Return (%)'].mean(), top_10['Max DD (%)'].mean(), top_10['Win Rate (%)'].mean()],
        'Batch Avg': [batch_avg['Profit Factor'], batch_avg['Sharpe'], batch_avg['Return (%)'], batch_avg['Max DD (%)'], batch_avg['Win Rate (%)']]
    }
    print(pd.DataFrame(data).to_string(index=False))

if __name__ == "__main__":
    analyze()
