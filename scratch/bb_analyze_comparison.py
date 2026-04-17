import pandas as pd
import os

def analyze():
    std_file = "scratch/batch_backtests/bb_results_1h_standard.csv"
    ha_file = "scratch/batch_backtests/bb_results_1h_heikin_ashi.csv"
    
    if not os.path.exists(std_file) or not os.path.exists(ha_file):
        print("Error: Result files not found. Ensure backtests are complete.")
        return

    df_std = pd.read_csv(std_file)
    df_ha = pd.read_csv(ha_file)
    
    # Rename columns for merging
    df_std = df_std.rename(columns={
        'Return (%)': 'Std Return (%)',
        'Profit Factor': 'Std PF',
        'Max DD (%)': 'Std Max DD (%)',
        'Trades': 'Std Trades',
        'Win Rate (%)': 'Std Win Rate (%)'
    }).drop(columns=['Candle Type', 'Sharpe', 'Sortino'])
    
    df_ha = df_ha.rename(columns={
        'Return (%)': 'HA Return (%)',
        'Profit Factor': 'HA PF',
        'Max DD (%)': 'HA Max DD (%)',
        'Trades': 'HA Trades',
        'Win Rate (%)': 'HA Win Rate (%)'
    }).drop(columns=['Candle Type', 'Sharpe', 'Sortino'])
    
    # Merge on Symbol
    merged = pd.merge(df_std, df_ha, on='Symbol', how='outer')
    
    # Calculate Average Profit Factor
    merged['Avg PF'] = (merged['Std PF'].fillna(0) + merged['HA PF'].fillna(0)) / 2
    
    # Filter: Minimum 10 trades in at least one category to avoid lucky outliers
    merged = merged[(merged['Std Trades'] >= 10) | (merged['HA Trades'] >= 10)]
    
    # Sort by Average Profit Factor
    top_performers = merged.sort_values(by='Avg PF', ascending=False).head(20)
    
    # Save comparison report
    top_performers.to_csv("scratch/batch_backtests/bb_comparison_report.csv", index=False)
    
    print("\n" + "="*80)
    print(f"{'BOLLINGER BAND 1H COMPARISON REPORT (Top 15)':^80}")
    print("="*80)
    header = f"{'Symbol':<12} | {'Std PF':<8} | {'HA PF':<8} | {'Std Ret %':<10} | {'HA Ret %':<10} | {'Trades (S/H)':<12}"
    print(header)
    print("-" * 80)
    
    for _, row in top_performers.head(15).iterrows():
        std_trades = int(row['Std Trades']) if not pd.isna(row['Std Trades']) else 0
        ha_trades = int(row['HA Trades']) if not pd.isna(row['HA Trades']) else 0
        trades_str = f"{std_trades}/{ha_trades}"
        line = (f"{row['Symbol']:<12} | "
                f"{row['Std PF'] if not pd.isna(row['Std PF']) else 0.0:>8.2f} | "
                f"{row['HA PF'] if not pd.isna(row['HA PF']) else 0.0:>8.2f} | "
                f"{row['Std Return (%)'] if not pd.isna(row['Std Return (%)']) else 0.0:>9.2f}% | "
                f"{row['HA Return (%)'] if not pd.isna(row['HA Return (%)']) else 0.0:>9.2f}% | "
                f"{trades_str:<12}")
        print(line)
    print("="*80 + "\n")
    
    print("Detailed report saved to scratch/batch_backtests/bb_comparison_report.csv")

if __name__ == "__main__":
    analyze()
