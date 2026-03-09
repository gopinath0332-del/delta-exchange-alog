import pandas as pd
from typing import List, Dict, Any, Tuple
from datetime import datetime

from core.logger import get_logger
from core.config import get_config

logger = get_logger(__name__)

class BacktestEngine:
    """Engine to simulate execution of trades and calculate equity over time."""
    
    def __init__(self, strategy, symbol: str, timeframe: str):
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.config = get_config()
        self.bt_config = self.config.backtesting
        
        self.initial_capital = self.bt_config.initial_capital
        self.equity = self.initial_capital
        self.order_size_pct = self.bt_config.order_size_pct
        self.commission = self.bt_config.commission
        
        self.processed_trades = []
        self.equity_curve = []
        
        # Initial point for equity curve
        self.equity_curve.append({
            'time': 'Start',
            'equity': self.equity
        })
        
    def _parse_time(self, time_str: str) -> datetime:
        try:
            # Often formatted as '%d-%m-%y %H:%M' by the strategy's run_backtest
            return datetime.strptime(time_str.split(' (')[0], '%d-%m-%y %H:%M')
        except:
            return None

    def run(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
        logger.info(f"Running backtest for {self.symbol} on {self.timeframe} timeframe")
        
        # Run the strategy's built-in backtest logic to generate raw signals
        self.strategy.run_backtest(df)
        raw_trades = getattr(self.strategy, 'trades', [])
        
        for trade in raw_trades:
            # Only process closed or partial closed trades
            if trade['status'] not in ['CLOSED', 'PARTIAL', 'TRAIL STOP', 'CHANNEL EXIT'] and not ('exit_price' in trade and trade['exit_price']):
                continue 
                
            entry_price = float(trade['entry_price'])
            exit_price = float(trade['exit_price']) if trade.get('exit_price') and trade['exit_price'] != '-' else entry_price
            
            if exit_price == entry_price:
                # Might be unbroken trade due to end of data, skip if no real exit
                continue
                
            # Sizing
            trade_capital = self.equity * self.order_size_pct
            position_size = trade_capital / entry_price
            
            # PnL
            if trade['type'] == 'LONG':
                pnl = (exit_price - entry_price) * position_size
            else: # SHORT
                pnl = (entry_price - exit_price) * position_size
                
            # Commission
            comm_cost = (trade_capital * self.commission) + ((exit_price * position_size) * self.commission)
            pnl -= comm_cost
            
            self.equity += pnl
            return_pct = (pnl / trade_capital) * 100
            
            # Calculate duration if possible
            duration_str = "N/A"
            dt_entry = self._parse_time(trade.get('entry_time', ''))
            dt_exit = self._parse_time(trade.get('exit_time', ''))
            if dt_entry and dt_exit:
                diff = dt_exit - dt_entry
                duration_str = str(diff)
            
            processed_trade = {
                'Symbol': self.symbol,
                'Entry Time': trade.get('entry_time', ''),
                'Exit Time': trade.get('exit_time', ''),
                'Entry Price': entry_price,
                'Exit Price': exit_price,
                'Position Type': trade['type'],
                'Position Size': position_size,
                'Profit/Loss': pnl,
                'Return %': return_pct,
                'Duration': duration_str
            }
            self.processed_trades.append(processed_trade)
            
            self.equity_curve.append({
                'time': trade.get('exit_time', ''),
                'equity': self.equity
            })
            
        logger.info(f"Backtest engine finished. Final equity: ${self.equity:.2f}")
        
        # Construct DataFrame for equity curve
        equity_df = pd.DataFrame(self.equity_curve)
        if len(equity_df) > 1:
            # Try parsing time for proper plotting later
            try:
                equity_df['time'] = pd.to_datetime(equity_df['time'].apply(lambda x: x.split(' (')[0] if isinstance(x, str) else x), format='%d-%m-%y %H:%M', errors='coerce')
            except:
                pass
                
        return self.processed_trades, equity_df
