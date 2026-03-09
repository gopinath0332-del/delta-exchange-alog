#!/usr/bin/env python3
"""
CLI script to run the backtesting framework.
"""

import argparse
import sys
import os
import time
import pandas as pd
from pathlib import Path
from tqdm import tqdm

# Set global timezone to UTC for consistent backtest reporting
# This ensures datetime.fromtimestamp() calls in strategies use UTC
# without modifying the shared strategy files.
os.environ['TZ'] = 'UTC'
if hasattr(time, 'tzset'):
    time.tzset()

from core.logger import setup_logging, get_logger
from core.config import get_config
from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import calculate_metrics
from backtest.reporter import Reporter

def get_strategy_instance(strategy_name: str, timeframe: str):
    """Factory to get the requested strategy instance."""
    name = strategy_name.lower()
    if name in ["btcusd", "double-dip", "doubledip"]:
        from strategies.double_dip_rsi import DoubleDipRSIStrategy
        strategy = DoubleDipRSIStrategy()
    elif name in ["cci-ema", "cciema"]:
        from strategies.cci_ema_strategy import CCIEMAStrategy
        strategy = CCIEMAStrategy()
    elif name in ["rs-50-ema", "rsi-50-ema", "rsi50ema"]:
        from strategies.rsi_50_ema_strategy import RSI50EMAStrategy
        strategy = RSI50EMAStrategy()
    elif name in ["macd-psar-100ema", "macd_psar_100ema", "macdpsar"]:
        from strategies.macd_psar_100ema_strategy import MACDPSAR100EMAStrategy
        strategy = MACDPSAR100EMAStrategy()
    elif name in ["rsi-200-ema", "rsi_200_ema", "rsi200ema"]:
        from strategies.rsi_200_ema_strategy import RSI200EMAStrategy
        strategy = RSI200EMAStrategy()
    elif name in ["rsi-supertrend", "rsi_supertrend", "rsisupertrend"]:
        from strategies.rsi_supertrend_strategy import RSISupertrendStrategy
        strategy = RSISupertrendStrategy()
    elif name in ["donchian-channel", "donchian_channel", "donchianchannel"]:
        from strategies.donchian_strategy import DonchianChannelStrategy
        strategy = DonchianChannelStrategy()
    elif name in ["ema-cross", "ema_cross", "emacross"]:
        from strategies.ema_cross_strategy import EMACrossStrategy
        strategy = EMACrossStrategy()
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")
        
    strategy.timeframe = timeframe
    return strategy

def print_summary(metrics: dict):
    """Print metrics summary to terminal."""
    print("\n" + "="*50)
    print(f"BACKTEST RESULTS: {metrics['Strategy Name']}")
    print("="*50)
    
    # Financials
    print(f"Initial Capital:     ${metrics['Initial Capital']:,.2f}")
    print(f"Final Capital:       ${metrics['Final Capital']:,.2f}")
    print(f"Total Return:        {metrics['Total Return %']:+.2f}%")
    
    # Ratios
    print(f"Sharpe Ratio:        {metrics['Sharpe Ratio']:.2f}")
    print(f"Sortino Ratio:       {metrics['Sortino Ratio']:.2f}")
    print(f"Max Drawdown:        {metrics['Max Drawdown %']:.2f}%")
    
    # Trade Stats
    print(f"Total Trades:        {metrics['Number of Trades']}")
    print(f"Win Rate:            {metrics['Win Rate %']:.2f}%")
    print(f"Profit Factor:       {metrics['Profit Factor']:.2f}")
    print(f"Average Win:         ${metrics['Average Win']:,.2f}")
    print(f"Average Loss:        ${metrics['Average Loss']:,.2f}")
    print("="*50 + "\n")

def run_backtest_for_file(filepath: Path, strategy_name: str, loader: DataLoader, reporter: Reporter) -> dict:
    """Run backtest for a single CSV file."""
    logger = get_logger(__name__)
    
    symbol, timeframe = loader.parse_filename(filepath)
    df = loader.load_data(filepath)
    
    if df.empty:
        logger.warning(f"No data loaded from {filepath}")
        return None
        
    try:
        strategy = get_strategy_instance(strategy_name, timeframe)
    except ValueError as e:
        logger.error(str(e))
        return None
        
    engine = BacktestEngine(strategy, symbol, timeframe, strategy_name)
    trades, equity_df = engine.run(df)
    
    metrics = calculate_metrics(
        strategy_name=f"{strategy_name} ({symbol})",
        initial_capital=engine.initial_capital,
        final_capital=engine.equity,
        trades=trades,
        equity_df=equity_df
    )
    # Add symbol for summary reporting
    metrics['Symbol'] = symbol
    
    print_summary(metrics)
    
    # Save trades to CSV if needed (optional feature)
    trades_df = pd.DataFrame(trades)
    if not trades_df.empty:
        csv_path = reporter.reports_dir / f"{symbol}_{timeframe}_trades.csv"
        trades_df.to_csv(csv_path, index=False)
        logger.info(f"Trades saved to {csv_path}")
    
    # Generate HTML report
    reporter.generate_report(
        symbol=symbol,
        timeframe=timeframe,
        metrics=metrics,
        trades=trades,
        equity_df=equity_df
    )
    
    return metrics

def main():
    parser = argparse.ArgumentParser(description="Delta Algo Python Backtesting Framework")
    parser.add_argument("--strategy", type=str, required=False, help="Name of strategy to test (e.g. donchian-channel)")
    parser.add_argument("--symbol", type=str, help="Specific symbol to test (e.g. BTCUSDT)")
    parser.add_argument("--timeframe", type=str, help="Specific timeframe to test (e.g. 1h)")
    parser.add_argument("--file", type=str, help="Specific CSV file to test")
    
    args = parser.parse_args()
    
    if not args.strategy:
        strategies = [
            "double-dip",
            "cci-ema",
            "rsi-50-ema",
            "macd-psar-100ema",
            "rsi-200-ema",
            "rsi-supertrend",
            "donchian-channel",
            "ema-cross"
        ]
        print("Available Strategies:")
        for i, s in enumerate(strategies, 1):
            print(f"  {i}. {s}")
        print()
        try:
            choice = input(f"Select a strategy (1-{len(strategies)}): ").strip()
            if not choice:
                print("No strategy selected. Exiting.")
                sys.exit(0)
            idx = int(choice) - 1
            if 0 <= idx < len(strategies):
                args.strategy = strategies[idx]
            else:
                print("Invalid choice. Exiting.")
                sys.exit(1)
        except KeyboardInterrupt:
            print("\nExiting.")
            sys.exit(0)
        except ValueError:
            print("Invalid input. Exiting.")
            sys.exit(1)
    
    # Initialize basic logging for CLI output
    setup_logging(log_level="INFO")
    logger = get_logger(__name__)
    
    config = get_config()
    data_folder = config.backtesting.data_folder
    
    loader = DataLoader(data_folder)
    reporter = Reporter()
    
    files_to_process = []
    
    if args.file:
        filepath = Path(args.file)
        if filepath.exists():
            files_to_process.append(filepath)
        else:
            logger.error(f"File not found: {args.file}")
            sys.exit(1)
    else:
        all_files = loader.get_available_files()
        if not all_files:
            logger.error(f"No CSV files found in {data_folder}")
            sys.exit(1)
            
        for f in all_files:
            sym, tf = loader.parse_filename(f)
            if args.symbol and args.symbol.upper() not in sym.upper():
                continue
            if args.timeframe and args.timeframe != tf:
                continue
            files_to_process.append(f)
            
    if not files_to_process:
        logger.error("No files matched the given filters.")
        sys.exit(1)
        
    logger.info(f"Starting backtest on {len(files_to_process)} dataset(s)...")
    
    all_metrics = []
    
    # Process each file with progress bar
    for filepath in tqdm(files_to_process, desc="Backtesting"):
        metrics = run_backtest_for_file(filepath, args.strategy, loader, reporter)
        if metrics:
            all_metrics.append(metrics)
            
    if len(all_metrics) > 1:
        logger.info(f"Successfully backtested {len(all_metrics)} datasets.")
        
        # Sort by Profit Factor descending
        sorted_metrics = sorted(all_metrics, key=lambda x: x.get('Profit Factor', 0), reverse=True)
        
        print("\n" + "="*100)
        print(f"{'OVERVIEW OF SYMBOL BACKTESTS (Sorted by Profit Factor)':^100}")
        print("="*100)
        header = f"{'Symbol':<15} | {'Net PnL':<12} | {'Max Drawdown':<15} | {'Trades':<8} | {'Win Rate':<10} | {'Profit Factor':<13}"
        print(header)
        print("-" * 100)
        
        for m in sorted_metrics:
            net_pnl = m.get('Final Capital', 0) - m.get('Initial Capital', 0)
            row = (f"{m.get('Symbol', 'N/A'):<15} | "
                   f"${net_pnl:>10.2f} | "
                   f"{m.get('Max Drawdown %', 0):>14.2f}% | "
                   f"{m.get('Number of Trades', 0):>8} | "
                   f"{m.get('Win Rate %', 0):>9.2f}% | "
                   f"{m.get('Profit Factor', 0):>13.2f}")
            print(row)
        print("="*100 + "\n")
        
    logger.info(f"All reports saved to {os.path.abspath(reporter.reports_dir)}")

if __name__ == "__main__":
    main()
