import pandas as pd
import numpy as np
import datetime
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
            ts_min = data_df['time'].min()
            ts_max = data_df['time'].max()
            # Ensure ts is in seconds (not milliseconds 1e11+)
            if ts_min > 1e10: ts_min /= 1000
            if ts_max > 1e10: ts_max /= 1000
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
            'Profitable Trades %': 0.0,
            'Total Fees': 0.0,
            'Detailed Table': []
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
    
    total_fees = sum(t.get('Fee', 0.0) for t in trades)
    
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
        ts_min = data_df['time'].min()
        ts_max = data_df['time'].max()
        if ts_min > 1e10: ts_min /= 1000
        if ts_max > 1e10: ts_max /= 1000
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

    # Buy and Hold metrics
    buy_hold_return_val = 0.0
    buy_hold_rtn_pct = 0.0
    strategy_outperformance = 0.0
    if data_df is not None and not data_df.empty and 'close' in data_df.columns:
        first_price = data_df['close'].iloc[0]
        last_price = data_df['close'].iloc[-1]
        
        if first_price > 0:
            # Assuming we bought initial_capital worth of asset at start
            units_bought = initial_capital / first_price
            buy_hold_final_value = units_bought * last_price
            buy_hold_return_val = buy_hold_final_value - initial_capital
            buy_hold_rtn_pct = (buy_hold_return_val / initial_capital) * 100
            
            # Outperformance is strategy return USD - buy/hold return USD
            strategy_outperformance = (final_capital - initial_capital) - buy_hold_return_val

    # Detailed Metrics Block
    # Detailed Metrics Block
    def calc_stats(subset):
        if not subset:
            return {
                'net_pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0, 'pf': 0.0, 'comm': 0.0, 'payoff': 0.0,
                'total_trades': 0, 'open_trades': 0, 'winning_trades': 0, 'losing_trades': 0, 'pct_profitable': 0.0,
                'avg_pnl': 0.0, 'avg_pnl_pct': 0.0, 'avg_win': 0.0, 'avg_win_pct': 0.0, 'avg_loss': 0.0, 'avg_loss_pct': 0.0,
                'ratio_win_loss': 0.0, 'max_win': 0.0, 'max_win_pct': 0.0, 'max_win_pct_gross': 0.0,
                'max_loss': 0.0, 'max_loss_pct': 0.0, 'max_loss_pct_gross': 0.0,
                'avg_bars': 0, 'avg_bars_win': 0, 'avg_bars_loss': 0,
                # MAE / MFE aggregates
                'avg_mae_pct': 0.0, 'avg_mfe_pct': 0.0,
                'max_mae_pct': 0.0, 'max_mfe_pct': 0.0,
            }
        
        wins = [t for t in subset if t.get('Profit/Loss', 0) > 0]
        losses = [t for t in subset if t.get('Profit/Loss', 0) < 0]
        
        gp = sum(t.get('Profit/Loss', 0) for t in wins)
        gl = abs(sum(t.get('Profit/Loss', 0) for t in losses))
        npnl = sum(t.get('Profit/Loss', 0) for t in subset)
        comm = sum(t.get('Fee', 0.0) for t in subset)
        pf = (gp / gl) if gl > 0 else (float('inf') if gp > 0 else 0.0)
        payoff = npnl / len(subset)
        
        open_t = len([t for t in subset if t.get('Exit Type') == 'END OF DATA'])
        
        avg_pnl = npnl / len(subset)
        avg_pnl_pct = float(np.mean([t.get('Return %', 0) for t in subset]))
        
        avg_win = gp / len(wins) if wins else 0.0
        avg_win_pct = float(np.mean([t.get('Return %', 0) for t in wins])) if wins else 0.0
        
        avg_loss = sum(t.get('Profit/Loss', 0) for t in losses) / len(losses) if losses else 0.0
        avg_loss_pct = float(np.mean([t.get('Return %', 0) for t in losses])) if losses else 0.0
        
        ratio_win_loss = abs(avg_win / avg_loss) if avg_loss != 0 else (float('inf') if avg_win > 0 else 0.0)
        
        max_win = max([t.get('Profit/Loss', 0) for t in wins]) if wins else 0.0
        max_win_pct = max([t.get('Return %', 0) for t in wins]) if wins else 0.0
        max_win_pct_gross = (max_win / gp)*100 if gp > 0 else 0.0
        
        max_loss = min([t.get('Profit/Loss', 0) for t in losses]) if losses else 0.0
        max_loss_pct = min([t.get('Return %', 0) for t in losses]) if losses else 0.0
        max_loss_pct_gross = (abs(max_loss) / gl)*100 if gl > 0 else 0.0
        
        avg_bars = int(np.mean([t.get('Bars Held', 0) for t in subset])) if subset else 0
        avg_bars_win = int(np.mean([t.get('Bars Held', 0) for t in wins])) if wins else 0
        avg_bars_loss = int(np.mean([t.get('Bars Held', 0) for t in losses])) if losses else 0

        # --- MAE / MFE aggregates ---
        # Average and maximum MAE % across all trades in this subset.
        # MAE measures the worst price move against the position during the trade
        # (a proxy for "heat taken" and stop placement quality).
        mae_pcts = [t.get('MAE %', 0.0) for t in subset]
        mfe_pcts = [t.get('MFE %', 0.0) for t in subset]
        avg_mae_pct = float(np.mean(mae_pcts)) if mae_pcts else 0.0
        avg_mfe_pct = float(np.mean(mfe_pcts)) if mfe_pcts else 0.0
        max_mae_pct = float(max(mae_pcts)) if mae_pcts else 0.0
        max_mfe_pct = float(max(mfe_pcts)) if mfe_pcts else 0.0
        
        return {
            'net_pnl': npnl, 'gross_profit': gp, 'gross_loss': gl, 'pf': pf, 'comm': comm, 'payoff': payoff,
            'total_trades': len(subset), 'open_trades': open_t, 'winning_trades': len(wins), 'losing_trades': len(losses),
            'pct_profitable': (len(wins) / len(subset)) * 100,
            'avg_pnl': avg_pnl, 'avg_pnl_pct': avg_pnl_pct,
            'avg_win': avg_win, 'avg_win_pct': avg_win_pct,
            'avg_loss': avg_loss, 'avg_loss_pct': avg_loss_pct,
            'ratio_win_loss': ratio_win_loss,
            'max_win': max_win, 'max_win_pct': max_win_pct, 'max_win_pct_gross': max_win_pct_gross,
            'max_loss': max_loss, 'max_loss_pct': max_loss_pct, 'max_loss_pct_gross': max_loss_pct_gross,
            'avg_bars': avg_bars, 'avg_bars_win': avg_bars_win, 'avg_bars_loss': avg_bars_loss,
            # MAE / MFE aggregates
            'avg_mae_pct': avg_mae_pct, 'avg_mfe_pct': avg_mfe_pct,
            'max_mae_pct': max_mae_pct, 'max_mfe_pct': max_mfe_pct,
        }
        
    stats_all = calc_stats(trades)
    stats_long = calc_stats([t for t in trades if t.get('Position Type') == 'LONG'])
    stats_short = calc_stats([t for t in trades if t.get('Position Type') == 'SHORT'])
    
    def pct(val): return (val / initial_capital) * 100 if initial_capital > 0 else 0.0

    def fmt_cur_pct(amt, p):
        if amt > 0: return f'<span class="val-pos">+{amt:,.2f} <small>USD</small></span><span class="val-pos pct-val">+{p:,.2f}%</span>'
        elif amt < 0: return f'<span class="val-neg">{amt:,.2f} <small>USD</small></span><span class="val-neg pct-val">{p:,.2f}%</span>'
        else: return f'<span class="val-neu">0.00 <small>USD</small></span><span class="val-neu pct-val">0.00%</span>'

    def fmt_cur_pct_no_sign(amt, p):
        return f'<span class="val-neu">{amt:,.2f} <small>USD</small></span><span class="val-neu pct-val">{p:,.2f}%</span>'
        
    def fmt_cur(amt):
        # Allow +/- formatting for outperformance/returns where generic cur applies
        if amt > 0: return f'<span class="val-pos">+{amt:,.2f} <small>USD</small></span>'
        elif amt < 0: return f'<span class="val-neg">{amt:,.2f} <small>USD</small></span>'
        return f'<span class="val-neu">{amt:,.2f} <small>USD</small></span>'
        
    def fmt_cur_neut(amt):
        return f'<span class="val-neu">{amt:,.2f} <small>USD</small></span>'

    def fmt_pct(p):
        return f'<span class="val-neu">{p:,.2f}%</span>'
        
    def fmt_factor(pf):
        return f'<span class="val-neu">{"&infin;" if pf == float("inf") else f"{pf:.3f}"}</span>'
        
    def fmt_num(n):
        return f'<span class="val-neu">{n}</span>'

    # Runups and Drawdowns
    dd_events = []
    ru_events = []
    
    if equity_df is not None and not equity_df.empty and len(equity_df) > 1:
        def try_parse(t):
            try:
                return datetime.datetime.strptime(str(t).split(' (')[0], '%d-%m-%y %H:%M')
            except:
                return None
        
        times = equity_df['time'].apply(try_parse)
        equities = equity_df['equity'].values
        
        peak_val = equities[0]
        peak_idx = 0
        trough_val_for_dd = equities[0]
        
        # Drawdowns
        for i in range(1, len(equities)):
            if equities[i] >= peak_val:
                if peak_val > trough_val_for_dd:
                    dd_val = peak_val - trough_val_for_dd
                    dd_pct = (dd_val / peak_val) * 100 if peak_val > 0 else 0
                    if dd_val > 0:
                        dur = times.iloc[i] - times.iloc[peak_idx] if pd.notnull(times.iloc[i]) and pd.notnull(times.iloc[peak_idx]) else pd.Timedelta(0)
                        dd_events.append({'val': dd_val, 'pct': dd_pct, 'dur': dur})
                peak_val = equities[i]
                peak_idx = i
                trough_val_for_dd = equities[i]
            else:
                if equities[i] < trough_val_for_dd:
                    trough_val_for_dd = equities[i]
        
        if peak_val > trough_val_for_dd:
            dd_val = peak_val - trough_val_for_dd
            dd_pct = (dd_val / peak_val) * 100 if peak_val > 0 else 0
            dur = times.iloc[-1] - times.iloc[peak_idx] if pd.notnull(times.iloc[-1]) and pd.notnull(times.iloc[peak_idx]) else pd.Timedelta(0)
            dd_events.append({'val': dd_val, 'pct': dd_pct, 'dur': dur})
            
        # Run-ups
        trough_val = equities[0]
        trough_idx = 0
        peak_val_for_ru = equities[0]
        
        for i in range(1, len(equities)):
            if equities[i] <= trough_val:
                if peak_val_for_ru > trough_val:
                    ru_val = peak_val_for_ru - trough_val
                    ru_pct = (ru_val / trough_val) * 100 if trough_val > 0 else 0
                    if ru_val > 0:
                        dur = times.iloc[i] - times.iloc[trough_idx] if pd.notnull(times.iloc[i]) and pd.notnull(times.iloc[trough_idx]) else pd.Timedelta(0)
                        ru_events.append({'val': ru_val, 'pct': ru_pct, 'dur': dur})
                trough_val = equities[i]
                trough_idx = i
                peak_val_for_ru = equities[i]
            else:
                if equities[i] > peak_val_for_ru:
                    peak_val_for_ru = equities[i]
                    
        if peak_val_for_ru > trough_val:
            ru_val = peak_val_for_ru - trough_val
            ru_pct = (ru_val / trough_val) * 100 if trough_val > 0 else 0
            dur = times.iloc[-1] - times.iloc[trough_idx] if pd.notnull(times.iloc[-1]) and pd.notnull(times.iloc[trough_idx]) else pd.Timedelta(0)
            ru_events.append({'val': ru_val, 'pct': ru_pct, 'dur': dur})

    def format_dur(td):
        if not td or pd.isnull(td): return "N/A"
        days = td.days
        if days > 0: return f"{days} days"
        hours = td.seconds // 3600
        if hours > 0: return f"{hours} hours"
        mins = (td.seconds % 3600) // 60
        return f"{mins} mins"

    avg_dd_dur = format_dur(sum((e['dur'] for e in dd_events), pd.Timedelta(0)) / len(dd_events)) if dd_events else "N/A"
    avg_dd_val = sum(e['val'] for e in dd_events) / len(dd_events) if dd_events else 0.0
    avg_dd_pct = sum(e['pct'] for e in dd_events) / len(dd_events) if dd_events else 0.0
    
    max_dd_val = max((e['val'] for e in dd_events), default=0.0)
    max_dd_pct = max((e['pct'] for e in dd_events), default=0.0)
    
    avg_ru_dur = format_dur(sum((e['dur'] for e in ru_events), pd.Timedelta(0)) / len(ru_events)) if ru_events else "N/A"
    avg_ru_val = sum(e['val'] for e in ru_events) / len(ru_events) if ru_events else 0.0
    avg_ru_pct = sum(e['pct'] for e in ru_events) / len(ru_events) if ru_events else 0.0
    
    max_ru_val = max((e['val'] for e in ru_events), default=0.0)
    max_ru_pct = max((e['pct'] for e in ru_events), default=0.0)

    detailed_metrics = [
        {'Metric': 'Initial capital', 'All': fmt_cur_neut(initial_capital), 'Long': '', 'Short': ''},
        {'Metric': 'Open P&L', 'All': fmt_cur_pct(0, 0), 'Long': '', 'Short': ''},
        {'Metric': 'Net P&L', 'All': fmt_cur_pct(stats_all['net_pnl'], pct(stats_all['net_pnl'])), 'Long': fmt_cur_pct(stats_long['net_pnl'], pct(stats_long['net_pnl'])), 'Short': fmt_cur_pct(stats_short['net_pnl'], pct(stats_short['net_pnl']))},
        {'Metric': 'Gross profit', 'All': fmt_cur_pct_no_sign(stats_all['gross_profit'], pct(stats_all['gross_profit'])), 'Long': fmt_cur_pct_no_sign(stats_long['gross_profit'], pct(stats_long['gross_profit'])), 'Short': fmt_cur_pct_no_sign(stats_short['gross_profit'], pct(stats_short['gross_profit']))},
        {'Metric': 'Gross loss', 'All': fmt_cur_pct_no_sign(stats_all['gross_loss'], pct(stats_all['gross_loss'])), 'Long': fmt_cur_pct_no_sign(stats_long['gross_loss'], pct(stats_long['gross_loss'])), 'Short': fmt_cur_pct_no_sign(stats_short['gross_loss'], pct(stats_short['gross_loss']))},
        {'Metric': 'Profit factor', 'All': fmt_factor(stats_all['pf']), 'Long': fmt_factor(stats_long['pf']), 'Short': fmt_factor(stats_short['pf'])},
        {'Metric': 'Commission paid', 'All': fmt_cur_neut(stats_all['comm']), 'Long': fmt_cur_neut(stats_long['comm']), 'Short': fmt_cur_neut(stats_short['comm'])},
        {'Metric': 'Expected payoff', 'All': fmt_cur_neut(stats_all['payoff']), 'Long': fmt_cur_neut(stats_long['payoff']), 'Short': fmt_cur_neut(stats_short['payoff'])},
        {'is_header': True, 'Metric': 'Buy & Hold Comparison', 'All': '', 'Long': '', 'Short': ''},
        {'Metric': 'Buy & hold return', 'All': fmt_cur_pct(buy_hold_return_val, buy_hold_rtn_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Buy & hold % gain', 'All': fmt_pct(buy_hold_rtn_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Strategy outperformance', 'All': fmt_cur(strategy_outperformance), 'Long': '', 'Short': ''},
        {'is_header': True, 'Metric': 'Risk-adjusted performance', 'All': '', 'Long': '', 'Short': ''},
        {'Metric': 'Sharpe ratio', 'All': fmt_factor(sharpe_ratio), 'Long': '', 'Short': ''},
        {'Metric': 'Sortino ratio', 'All': fmt_factor(sortino_ratio), 'Long': '', 'Short': ''},
        {'is_header': True, 'Metric': 'Details', 'All': '', 'Long': '', 'Short': ''},
        {'Metric': 'Total trades', 'All': fmt_num(stats_all['total_trades']), 'Long': fmt_num(stats_long['total_trades']), 'Short': fmt_num(stats_short['total_trades'])},
        {'Metric': 'Total open trades', 'All': fmt_num(stats_all['open_trades']), 'Long': fmt_num(stats_long['open_trades']), 'Short': fmt_num(stats_short['open_trades'])},
        {'Metric': 'Winning trades', 'All': fmt_num(stats_all['winning_trades']), 'Long': fmt_num(stats_long['winning_trades']), 'Short': fmt_num(stats_short['winning_trades'])},
        {'Metric': 'Losing trades', 'All': fmt_num(stats_all['losing_trades']), 'Long': fmt_num(stats_long['losing_trades']), 'Short': fmt_num(stats_short['losing_trades'])},
        {'Metric': 'Percent profitable', 'All': fmt_pct(stats_all['pct_profitable']), 'Long': fmt_pct(stats_long['pct_profitable']), 'Short': fmt_pct(stats_short['pct_profitable'])},
        {'Metric': 'Avg P&L', 'All': fmt_cur_pct_no_sign(stats_all['avg_pnl'], stats_all['avg_pnl_pct']), 'Long': fmt_cur_pct_no_sign(stats_long['avg_pnl'], stats_long['avg_pnl_pct']), 'Short': fmt_cur_pct_no_sign(stats_short['avg_pnl'], stats_short['avg_pnl_pct'])},
        {'Metric': 'Avg winning trade', 'All': fmt_cur_pct_no_sign(stats_all['avg_win'], stats_all['avg_win_pct']), 'Long': fmt_cur_pct_no_sign(stats_long['avg_win'], stats_long['avg_win_pct']), 'Short': fmt_cur_pct_no_sign(stats_short['avg_win'], stats_short['avg_win_pct'])},
        {'Metric': 'Avg losing trade', 'All': fmt_cur_pct_no_sign(stats_all['avg_loss'], stats_all['avg_loss_pct']), 'Long': fmt_cur_pct_no_sign(stats_long['avg_loss'], stats_long['avg_loss_pct']), 'Short': fmt_cur_pct_no_sign(stats_short['avg_loss'], stats_short['avg_loss_pct'])},
        {'Metric': 'Ratio avg win / avg loss', 'All': fmt_factor(stats_all['ratio_win_loss']), 'Long': fmt_factor(stats_long['ratio_win_loss']), 'Short': fmt_factor(stats_short['ratio_win_loss'])},
        {'Metric': 'Largest winning trade', 'All': fmt_cur_neut(stats_all['max_win']), 'Long': fmt_cur_neut(stats_long['max_win']), 'Short': fmt_cur_neut(stats_short['max_win'])},
        {'Metric': 'Largest winning trade percent', 'All': fmt_pct(stats_all['max_win_pct']), 'Long': fmt_pct(stats_long['max_win_pct']), 'Short': fmt_pct(stats_short['max_win_pct'])},
        {'Metric': 'Largest winner as % of gross profit', 'All': fmt_pct(stats_all['max_win_pct_gross']), 'Long': fmt_pct(stats_long['max_win_pct_gross']), 'Short': fmt_pct(stats_short['max_win_pct_gross'])},
        {'Metric': 'Largest losing trade', 'All': fmt_cur_neut(stats_all['max_loss']), 'Long': fmt_cur_neut(stats_long['max_loss']), 'Short': fmt_cur_neut(stats_short['max_loss'])},
        {'Metric': 'Largest losing trade percent', 'All': fmt_pct(stats_all['max_loss_pct']), 'Long': fmt_pct(stats_long['max_loss_pct']), 'Short': fmt_pct(stats_short['max_loss_pct'])},
        {'Metric': 'Largest loser as % of gross loss', 'All': fmt_pct(stats_all['max_loss_pct_gross']), 'Long': fmt_pct(stats_long['max_loss_pct_gross']), 'Short': fmt_pct(stats_short['max_loss_pct_gross'])},
        {'Metric': 'Avg # bars in trades', 'All': fmt_num(stats_all['avg_bars']), 'Long': fmt_num(stats_long['avg_bars']), 'Short': fmt_num(stats_short['avg_bars'])},
        {'Metric': 'Avg # bars in winning trades', 'All': fmt_num(stats_all['avg_bars_win']), 'Long': fmt_num(stats_long['avg_bars_win']), 'Short': fmt_num(stats_short['avg_bars_win'])},
        {'Metric': 'Avg # bars in losing trades', 'All': fmt_num(stats_all['avg_bars_loss']), 'Long': fmt_num(stats_long['avg_bars_loss']), 'Short': fmt_num(stats_short['avg_bars_loss'])},
        # ---- MAE / MFE Analysis ----
        # MAE (Maximum Adverse Excursion) = worst intra-trade price move against the position.
        # MFE (Maximum Favorable Excursion) = best unrealised profit available during the trade.
        # Both are expressed as % of entry price, averaged and maximised across the trade set.
        {'is_header': True, 'Metric': 'MAE / MFE Analysis', 'All': '', 'Long': '', 'Short': ''},
        {'Metric': 'Avg MAE % (max adverse excursion)', 'All': fmt_pct(stats_all['avg_mae_pct']), 'Long': fmt_pct(stats_long['avg_mae_pct']), 'Short': fmt_pct(stats_short['avg_mae_pct'])},
        {'Metric': 'Max MAE % (worst heat taken)', 'All': fmt_pct(stats_all['max_mae_pct']), 'Long': fmt_pct(stats_long['max_mae_pct']), 'Short': fmt_pct(stats_short['max_mae_pct'])},
        {'Metric': 'Avg MFE % (max favorable excursion)', 'All': fmt_pct(stats_all['avg_mfe_pct']), 'Long': fmt_pct(stats_long['avg_mfe_pct']), 'Short': fmt_pct(stats_short['avg_mfe_pct'])},
        {'Metric': 'Max MFE % (best opportunity seen)', 'All': fmt_pct(stats_all['max_mfe_pct']), 'Long': fmt_pct(stats_long['max_mfe_pct']), 'Short': fmt_pct(stats_short['max_mfe_pct'])},
        {'is_header': True, 'Metric': 'Run-ups and drawdowns', 'All': '', 'Long': '', 'Short': ''},

        {'is_header': True, 'Metric': 'Run-ups', 'All': '', 'Long': '', 'Short': ''},
        {'Metric': 'Avg equity run-up duration (close-to-close)', 'All': f'<span class="val-neu">{avg_ru_dur}</span>', 'Long': '', 'Short': ''},
        {'Metric': 'Avg equity run-up (close-to-close)', 'All': fmt_cur_pct_no_sign(avg_ru_val, avg_ru_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Max equity run-up (close-to-close)', 'All': fmt_cur_pct_no_sign(max_ru_val, max_ru_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Max equity run-up (intrabar)', 'All': fmt_cur_pct_no_sign(max_ru_val, max_ru_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Max equity run-up as % of initial capital (intrabar)', 'All': fmt_pct((max_ru_val/initial_capital)*100 if initial_capital > 0 else 0), 'Long': '', 'Short': ''},

        {'is_header': True, 'Metric': 'Drawdowns', 'All': '', 'Long': '', 'Short': ''},
        {'Metric': 'Avg equity drawdown duration (close-to-close)', 'All': f'<span class="val-neu">{avg_dd_dur}</span>', 'Long': '', 'Short': ''},
        {'Metric': 'Avg equity drawdown (close-to-close)', 'All': fmt_cur_pct_no_sign(avg_dd_val, avg_dd_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Max equity drawdown (close-to-close)', 'All': fmt_cur_pct_no_sign(max_dd_val, max_dd_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Max equity drawdown (intrabar)', 'All': fmt_cur_pct_no_sign(max_dd_val, max_dd_pct), 'Long': '', 'Short': ''},
        {'Metric': 'Max equity drawdown as % of initial capital (intrabar)', 'All': fmt_pct((max_dd_val/initial_capital)*100 if initial_capital > 0 else 0), 'Long': '', 'Short': ''},
        {'Metric': 'Return of max equity drawdown', 'All': fmt_cur_neut(0), 'Long': '', 'Short': ''}
    ]

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
        'Profitable Trades %': profitable_trades_pct,
        'Total Fees': total_fees,
        'Detailed Table': detailed_metrics
    }
    
    return metrics
