import numpy as pd
import pandas as pd
import numpy as np
from typing import List, Dict, Any

from core.logger import get_logger

logger = get_logger(__name__)

def calculate_metrics(
    strategy_name: str, 
    initial_capital: float, 
    final_capital: float, 
    trades: List[Dict[str, Any]], 
    equity_df: pd.DataFrame,
    data_df: pd.DataFrame = None
) -> Dict[str, Any]:
    """Calculate performance metrics for the backtest."""
    
    total_return = 0.0
    if initial_capital > 0:
        total_return = ((final_capital - initial_capital) / initial_capital) * 100

    num_trades = len(trades)
    if num_trades == 0:
        start_date = "N/A"
        end_date = "N/A"
        if data_df is not None and not data_df.empty and 'time' in data_df.columns:
            import datetime
            ts_min = data_df['time'].min()
            ts_max = data_df['time'].max()
            start_date = datetime.datetime.fromtimestamp(ts_min).strftime('%d-%m-%y %H:%M')
            end_date = datetime.datetime.fromtimestamp(ts_max).strftime('%d-%m-%y %H:%M')

        return {
            'Strategy Name': strategy_name,
            'Start Date': start_date,
            'End Date': end_date,
            'Initial Capital': initial_capital,
            'Final Capital': final_capital,
            'Total Return %': 0.0,
            'Sharpe Ratio': 0.0,
            'Sortino Ratio': 0.0,
            'Max Drawdown %': 0.0,
            'Number of Trades': 0,
            'Win Rate %': 0.0,
            'Profit Factor': 0.0,
            'Average Win': 0.0,
            'Average Loss': 0.0,
            'Average Win %': 0.0,
            'Average Loss %': 0.0,
            'Profitable Trades %': 0.0
        }

    # Trade stats
    winning_trades = [t for t in trades if t['Profit/Loss'] > 0]
    losing_trades = [t for t in trades if t['Profit/Loss'] < 0]
    
    win_rate = (len(winning_trades) / num_trades) * 100
    profitable_trades_pct = win_rate  # Essentially the same
    
    gross_profit = sum(t['Profit/Loss'] for t in winning_trades)
    gross_loss = abs(sum(t['Profit/Loss'] for t in losing_trades))
    
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    if gross_profit == 0 and gross_loss == 0:
        profit_factor = 0.0
        
    avg_win = (gross_profit / len(winning_trades)) if winning_trades else 0.0
    avg_loss = (sum(t['Profit/Loss'] for t in losing_trades) / len(losing_trades)) if losing_trades else 0.0
    
    avg_win_pct = np.mean([t['Return %'] for t in winning_trades]) if winning_trades else 0.0
    avg_loss_pct = np.mean([t['Return %'] for t in losing_trades]) if losing_trades else 0.0
    
    # Equity curve stats
    sharpe_ratio = 0.0
    sortino_ratio = 0.0
    max_drawdown = 0.0
    
    if len(equity_df) > 1 and 'time' in equity_df.columns:
        valid_equity = equity_df.copy()
        
        # Ensure time is datetime for daily resampling
        if pd.api.types.is_datetime64_any_dtype(valid_equity['time']):
            valid_equity.set_index('time', inplace=True)
            # Resample to daily equity to calculate standard financial metrics
            daily_equity = valid_equity['equity'].resample('D').last().ffill()
            
            if len(daily_equity) > 1:
                daily_returns = daily_equity.pct_change().dropna()
                
                # Annualized Sharpe (Root 365 for crypto)
                if daily_returns.std() != 0:
                    sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(365)
                
                # Annualized Sortino
                downside = daily_returns[daily_returns < 0]
                if not downside.empty and downside.std() != 0:
                    sortino_ratio = (daily_returns.mean() / downside.std()) * np.sqrt(365)
                
        # Drawdown 
        # Calculate from all equity points (not just daily) for maximum precision
        cummax = equity_df['equity'].cummax()
        drawdown = (equity_df['equity'] - cummax) / cummax
        max_drawdown = abs(drawdown.min() * 100) if drawdown.min() < 0 else 0.0
        
    # If daily resampling fails (e.g. invalid dates), fallback to per-trade Sharpe
    if sharpe_ratio == 0.0 and len(trades) > 1:
        returns = pd.Series([t['Return %']/100 for t in trades])
        if returns.std() != 0:
            # Per-trade sharpe
            sharpe_ratio = (returns.mean() / returns.std())
            
        downside = returns[returns < 0]
        if not downside.empty and downside.std() != 0:
            sortino_ratio = (returns.mean() / downside.std())
            
    # Extract Start and End Dates
    start_date = "N/A"
    end_date = "N/A"
    
    # Priority 1: Use full input data coverage if provided
    if data_df is not None and not data_df.empty and 'time' in data_df.columns:
        import datetime
        ts_min = data_df['time'].min()
        ts_max = data_df['time'].max()
        # Since TZ=UTC is set globally in run_backtest.py, this will be UTC
        start_date = datetime.datetime.fromtimestamp(ts_min).strftime('%d-%m-%y %H:%M')
        end_date = datetime.datetime.fromtimestamp(ts_max).strftime('%d-%m-%y %H:%M')
        
    # Priority 2: Fallback to equity timeline if data_df not provided
    elif not equity_df.empty and 'time' in equity_df.columns:
        # Convert to string format if valid
        times = equity_df['time'].dropna()
        if not times.empty:
            if pd.api.types.is_datetime64_any_dtype(times):
                start_date = times.min().strftime('%d-%m-%y %H:%M')
                end_date = times.max().strftime('%d-%m-%y %H:%M')
            else:
                start_date = str(times.iloc[0])
                end_date = str(times.iloc[-1])

    metrics = {
        'Strategy Name': strategy_name,
        'Start Date': start_date,
        'End Date': end_date,
        'Initial Capital': initial_capital,
        'Final Capital': final_capital,
        'Total Return %': total_return,
        'Sharpe Ratio': sharpe_ratio,
        'Sortino Ratio': sortino_ratio,
        'Max Drawdown %': max_drawdown,
        'Number of Trades': num_trades,
        'Win Rate %': win_rate,
        'Profit Factor': profit_factor,
        'Average Win': avg_win,
        'Average Loss': avg_loss,
        'Average Win %': avg_win_pct,
        'Average Loss %': avg_loss_pct,
        'Profitable Trades %': profitable_trades_pct
    }
    
    return metrics
