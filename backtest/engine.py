import pandas as pd
from typing import List, Dict, Any, Tuple
from datetime import datetime

from core.logger import get_logger
from core.config import get_config

logger = get_logger(__name__)

class BacktestEngine:
    """Engine to simulate execution of trades and calculate equity over time."""
    
    def __init__(self, strategy, symbol: str, timeframe: str, strategy_name: str = ""):
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name if strategy_name else type(strategy).__name__.lower()
        self.config = get_config()
        self.bt_config = self.config.backtesting
        
        # Determine strategy stop loss if set in settings.yaml
        strat_key = self.strategy_name.replace("-", "_")
        strat_config = self.config.settings.get("strategies", {}).get(strat_key, {})
        self.stop_loss_pct = strat_config.get("stop_loss_pct", None)
        
        self.initial_capital = self.bt_config.initial_capital
        self.equity = self.initial_capital
        self.order_size_pct = self.bt_config.order_size_pct
        self.use_compounding = getattr(self.bt_config, 'use_compounding', False)
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
            # First try the %d-%m-%y %H:%M format from strategy's active_trade format
            return datetime.strptime(time_str.split(' (')[0], '%d-%m-%y %H:%M')
        except:
            try:
                # Fallback to standard ISO format if outputting default pandas timestamps
                return pd.to_datetime(time_str.split(' (')[0]).to_pydatetime()
            except:
                return None

    def run(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
        logger.info(f"Running backtest for {self.symbol} on {self.timeframe} timeframe")
        
        # Run the strategy's built-in backtest logic to generate raw signals
        self.strategy.run_backtest(df)
        raw_trades = getattr(self.strategy, 'trades', [])
        
        # Keep track of active partials to apply to the next matching trade exit
        partial_remaining_size_map = {}
        
        for trade in raw_trades:
            # Only process closed or partial closed trades
            if trade['status'] not in ['CLOSED', 'PARTIAL', 'TRAIL STOP', 'CHANNEL EXIT'] and not ('exit_price' in trade and trade['exit_price']):
                continue 
                
            entry_price = float(trade['entry_price'])
            exit_price = float(trade['exit_price']) if trade.get('exit_price') and trade['exit_price'] != '-' else entry_price
            
            if exit_price == entry_price:
                # Might be unbroken trade due to end of data, skip if no real exit
                continue
                
            # Sizing (Compound Sizing based on current Equity to match TradingView)
            base_capital = self.equity if self.use_compounding else self.initial_capital
            trade_capital = base_capital * self.order_size_pct
            
            # Identify the trade ID or unique entry for tracking partials
            # Since the strategy trades sequentially, we can track by entry_time + type
            trade_key = f"{trade['type']}_{trade.get('entry_time', '')}"
            
            if trade_key in partial_remaining_size_map and trade['status'] != 'PARTIAL':
                # This is the final 50% closing exit of a previously partially closed position
                position_size = partial_remaining_size_map[trade_key]
                del partial_remaining_size_map[trade_key]
            else:
                # Standard full position sizing
                position_size = trade_capital / entry_price
                if trade['status'] == 'PARTIAL':
                    # Only calculate PnL on 50% size if partial, and save the other 50% for later
                    half_size = position_size / 2.0
                    partial_remaining_size_map[trade_key] = half_size
                    position_size = half_size
            
            # PnL
            if trade['type'] == 'LONG':
                pnl = (exit_price - entry_price) * position_size
            else: # SHORT
                pnl = (entry_price - exit_price) * position_size
                
            # Exchange Hard Stop Loss Check (IGNORED per user request)
            # if self.stop_loss_pct is not None:
            #     # Calculate max loss based on the fractional trade capital of this specific exit segment
            #     segment_capital = trade_capital * (position_size / (trade_capital / entry_price))
            #     max_loss = segment_capital * self.stop_loss_pct
            #     
            #     if pnl < -max_loss:
            #         pnl = -max_loss
            #         # Overwrite exit price logically where the stop loss hit
            #         price_diff = max_loss / position_size
            #         exit_price = (entry_price - price_diff) if trade['type'] == 'LONG' else (entry_price + price_diff)
            #         trade['status'] = 'EXCHANGE SL'
                
            # Commission
            # Fee is based on the dollar volume of the portion of the position being exited/entered
            trade_dollar_volume = entry_price * position_size
            comm_cost = (trade_dollar_volume * self.commission) + ((exit_price * position_size) * self.commission)
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
                'Position Type': trade['type'],
                'Exit Type': trade.get('status', 'CLOSED'),
                'Position Size': position_size,
                'Entry Price': entry_price,
                'Exit Price': exit_price,
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
