from datetime import datetime, timezone
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from core.logger import get_logger
from core.config import get_config

logger = get_logger(__name__)

class BacktestEngine:
    """Engine to simulate execution of trades and calculate equity over time."""
    
    def __init__(self, strategy, symbol: str, timeframe: str, strategy_name: str = "", leverage: int = 1):
        self.strategy = strategy
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name if strategy_name else type(strategy).__name__.lower()
        self.leverage = leverage
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
        
        # Load symbol-specific metadata (fees, etc.)
        from core.trading import get_product_metadata
        self.metadata = get_product_metadata(self.symbol)
        
        # Use taker rate from metadata if available, otherwise fallback to config
        self.commission = self.metadata.get("taker_commission_rate", self.bt_config.commission)
        
        self.processed_trades = []
        self.equity_curve = []
        
    def _parse_time(self, time_str: str) -> Optional[datetime]:
        if not time_str or not isinstance(time_str, str):
            return None
        clean_time = time_str.split(' (')[0]
        try:
            # First try the %d-%m-%y %H:%M format from strategy's active_trade format
            return datetime.strptime(clean_time, '%d-%m-%y %H:%M')
        except ValueError:
            try:
                # Fallback to standard ISO format if outputting default pandas timestamps
                return pd.to_datetime(clean_time).to_pydatetime()
            except (ValueError, TypeError):
                return None

    def _calculate_mae_mfe(self, df: pd.DataFrame, raw_trades: List[Dict[str, Any]]):
        """Append MAE / MFE annotations to the raw trade dictionaries."""
        if df.empty or not raw_trades:
            return

        time_vals = df['time'].values
        # Create a lookup for candle times to indices for fast window indexing
        time_str_to_idx: Dict[str, int] = {}
        for _idx, _ts in enumerate(time_vals):
            try:
                # Use fromtimestamp (LOCAL time) to match format_time() in strategies
                _dt_str = datetime.fromtimestamp(float(_ts)).strftime('%d-%m-%y %H:%M')
                if _dt_str not in time_str_to_idx:
                    time_str_to_idx[_dt_str] = _idx
            except (ValueError, OSError, OverflowError):
                pass

        for trade in raw_trades:
            # Default — will be overridden if we can locate the candle window
            trade['mae_price'] = 0.0
            trade['mae_pct']   = 0.0
            trade['mfe_price'] = 0.0
            trade['mfe_pct']   = 0.0

            trade_type  = trade.get('type', 'LONG')
            entry_price = None

            try:
                entry_price = float(trade.get('entry_price', 0))
            except (TypeError, ValueError):
                continue

            if entry_price is None or entry_price <= 0:
                continue

            # Strip any parenthetical suffix (e.g. "06-12-25 06:30 (open)") before lookup
            entry_str = (trade.get('entry_time') or '').split(' (')[0].strip()
            exit_str  = (trade.get('exit_time')  or '').split(' (')[0].strip()

            entry_idx = time_str_to_idx.get(entry_str)
            exit_idx  = time_str_to_idx.get(exit_str)

            if entry_idx is not None and exit_idx is not None:
                # Scan the inclusive candle slice from entry bar to exit bar.
                i_start = min(entry_idx, exit_idx)
                i_end   = max(entry_idx, exit_idx)
                indices = np.arange(i_start, i_end + 1)
            elif entry_idx is not None:
                indices = np.arange(entry_idx, len(df))
            else:
                continue

            if len(indices) == 0:
                continue

            highs = df['high'].values[indices].astype(float)
            lows  = df['low'].values[indices].astype(float)

            if len(highs) == 0 or len(lows) == 0:
                continue

            max_high = float(np.nanmax(highs))
            min_low  = float(np.nanmin(lows))

            if trade_type == 'LONG':
                mfe_price = max(max_high - entry_price, 0.0)
                mae_price = max(entry_price - min_low, 0.0)
            else:  # SHORT
                mfe_price = max(entry_price - min_low, 0.0)
                mae_price = max(max_high - entry_price, 0.0)

            trade['mae_price'] = round(mae_price, 8)
            trade['mae_pct']   = round((mae_price / entry_price) * 100, 4)
            trade['mfe_price'] = round(mfe_price, 8)
            trade['mfe_pct']   = round((mfe_price / entry_price) * 100, 4)

    def run(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
        logger.info(f"Running backtest for {self.symbol} on {self.timeframe} timeframe")

        # Run the strategy's built-in backtest logic to generate raw signals
        self.strategy.run_backtest(df)
        raw_trades = getattr(self.strategy, 'trades', [])

        # Annotate every raw trade with MAE / MFE
        self._calculate_mae_mfe(df, raw_trades)

        # Pre-pass: assign stable numeric IDs for partial tracking
        _next_id = 0
        _partial_pending: dict = {}
        for t in raw_trades:
            pair_key = f"{t.get('type', '')}_{t.get('entry_time', '')}"
            is_partial = t.get('status') == 'PARTIAL' or 'MILESTONE' in str(t.get('status', ''))
            
            if is_partial:
                if pair_key not in _partial_pending:
                    t['_backtest_id'] = _next_id
                    _partial_pending[pair_key] = _next_id
                    _next_id += 1
                else:
                    t['_backtest_id'] = _partial_pending[pair_key]
            elif pair_key in _partial_pending:
                t['_backtest_id'] = _partial_pending.pop(pair_key)
            else:
                t['_backtest_id'] = _next_id
                _next_id += 1

        # Process raw strategy trades into detailed PnL reports
        self.process_trades(raw_trades)

        # Build per-candle mark-to-market equity curve
        self.equity_curve = self._build_candle_equity_curve(df)

        equity_df = pd.DataFrame(self.equity_curve)
        if len(equity_df) > 1:
            try:
                equity_df['time'] = pd.to_datetime(
                    equity_df['time'].apply(lambda x: x.split(' (')[0] if isinstance(x, str) else x),
                    format='%d-%m-%y %H:%M',
                    errors='coerce'
                )
            except (ValueError, TypeError):
                pass

        logger.info(f"Backtest engine finished. Final equity: ${self.equity:.2f}")
        return self.processed_trades, equity_df

    def process_trades(self, raw_trades: List[Dict[str, Any]]):
        """Process raw strategy trades into detailed PnL reports using risk settings."""
        from core.trading import calculate_position_size, get_contract_value
        
        remaining_pct_map = {}
        rm_config = self.config.risk_management
        sizing_method = getattr(rm_config, 'sizing_method', 'fixed')
        risk_pct = getattr(rm_config, 'risk_pct_per_trade', 0.01)
        margin_cap = getattr(rm_config, 'fractional_margin_cap', 0.2)
        atr_mult = getattr(rm_config, 'atr_margin_multiplier', 2.0)
        atr_cap_mult = getattr(rm_config, 'atr_margin_cap_multiplier', 1.5)
        
        contract_val = get_contract_value(self.symbol)
        
        for trade in raw_trades:
            if trade['status'] not in ['CLOSED', 'PARTIAL', 'TRAIL STOP', 'CHANNEL EXIT'] and not ('exit_price' in trade and trade['exit_price']) and not 'MILESTONE' in str(trade.get('status', '')):
                continue 
                
            entry_price = float(trade['entry_price'])
            exit_price = float(trade['exit_price']) if trade.get('exit_price') and trade['exit_price'] != '-' else entry_price
            entry_atr = trade.get('entry_atr', 0.0)
            
            if exit_price == entry_price:
                continue
            
            trade_key = trade['_backtest_id']
            current_remaining_pct = remaining_pct_map.get(trade_key, 1.0)
            
            if sizing_method.lower() == "fractional" and entry_atr > 0:
                size_for_full_trade, _ = calculate_position_size(
                    target_margin=0.0,
                    price=entry_price,
                    leverage=self.leverage,
                    contract_value=contract_val,
                    enable_partial_tp=getattr(self.strategy, 'enable_partial_tp', False),
                    sizing_method="fractional",
                    equity=self.equity,
                    risk_pct=risk_pct,
                    atr=entry_atr,
                    atr_multiplier=atr_mult,
                    fractional_margin_cap=margin_cap,
                    atr_margin_cap_multiplier=atr_cap_mult
                )
                total_initial_size = size_for_full_trade
            else:
                base_capital = self.equity if self.use_compounding else self.initial_capital
                trade_capital = base_capital * self.order_size_pct
                total_initial_size = (trade_capital * self.leverage) / (entry_price * contract_val)
            
            if 'exit_pct' in trade:
                exit_pct_of_remaining = float(trade['exit_pct'])
            elif trade['status'] == 'PARTIAL':
                exit_pct_of_remaining = 0.5
            else:
                exit_pct_of_remaining = 1.0

            position_size = total_initial_size * current_remaining_pct * exit_pct_of_remaining
            
            new_remaining_pct = current_remaining_pct * (1.0 - exit_pct_of_remaining)
            if new_remaining_pct <= 0.0001:
                if trade_key in remaining_pct_map:
                    del remaining_pct_map[trade_key]
            else:
                remaining_pct_map[trade_key] = new_remaining_pct
            
            if trade['type'] == 'LONG':
                pnl = (exit_price - entry_price) * position_size * contract_val
            else:
                pnl = (entry_price - exit_price) * position_size * contract_val
                
            if self.stop_loss_pct is not None:
                segment_margin = (position_size * entry_price * contract_val) / self.leverage
                max_loss = segment_margin * self.stop_loss_pct
                if pnl < -max_loss:
                    pnl = -max_loss
                    price_diff = max_loss / (position_size * contract_val)
                    exit_price = (entry_price - price_diff) if trade['type'] == 'LONG' else (entry_price + price_diff)
                    trade['status'] = 'EXCHANGE SL'
                
            trade_dollar_volume = entry_price * position_size * contract_val
            comm_cost = (trade_dollar_volume * self.commission) + ((exit_price * position_size * contract_val) * self.commission)
            
            net_pnl = pnl - comm_cost
            self.equity += net_pnl
            
            duration_str = "N/A"
            bars_held = 0
            dt_entry = self._parse_time(trade.get('entry_time', ''))
            dt_exit = self._parse_time(trade.get('exit_time', ''))
            if dt_entry and dt_exit:
                diff = dt_exit - dt_entry
                duration_str = str(diff)
                try:
                    import re
                    match = re.match(r'(\d+)([hmdw])', self.timeframe.lower())
                    if match:
                        val = int(match.group(1))
                        unit = match.group(2)
                        sec = diff.total_seconds()
                        if unit == 'h': bars_held = int(sec / (val * 3600))
                        elif unit == 'm': bars_held = int(sec / (val * 60))
                        elif unit == 'd': bars_held = int(sec / (val * 86400))
                        elif unit == 'w': bars_held = int(sec / (val * 604800))
                except (ValueError, ZeroDivisionError):
                    pass
            
            status_val = trade.get('status', 'CLOSED')
            if status_val == 'CLOSED':
                display_type = trade['type']
            elif status_val == 'PARTIAL':
                display_type = f"{trade['type']} (Partial)"
            elif status_val.startswith('MILESTONE'):
                m_label = status_val.title().replace('_', ' ')
                display_type = f"{trade['type']} ({m_label})"
            else:
                display_type = f"{trade['type']} ({status_val.title().replace('_', ' ').replace('Sl', 'SL')})"

            used_margin = (position_size * entry_price * contract_val) / self.leverage
            return_pct = (net_pnl / used_margin * 100) if used_margin > 0 else 0.0

            processed_trade = {
                'Symbol': self.symbol,
                'Leverage': self.leverage,
                'Entry Time': trade.get('entry_time', ''),
                'Exit Time': trade.get('exit_time', ''),
                'Position Type': trade['type'],
                'Display Type': display_type,
                'Exit Type': status_val,
                'Position Size': round(position_size, 4),
                'Margin': round(used_margin, 2),
                'Entry Price': entry_price,
                'Exit Price': exit_price,
                'Fee': round(comm_cost, 4),
                'Profit/Loss': round(net_pnl, 4),
                'Return %': round(return_pct, 2),
                'Duration': duration_str,
                'Bars Held': bars_held,
                'MAE Price': trade.get('mae_price', 0.0),
                'MAE %':     trade.get('mae_pct',   0.0),
                'MFE Price': trade.get('mfe_price', 0.0),
                'MFE %':     trade.get('mfe_pct',   0.0),
            }
            self.processed_trades.append(processed_trade)

    def _build_candle_equity_curve(self, df: pd.DataFrame) -> list:
        """Return a per-candle equity list with mark-to-market unrealised PnL."""
        parsed_trades = []
        for t in self.processed_trades:
            parsed_trades.append({
                'entry_dt': self._parse_time(t['Entry Time']),
                'exit_dt':  self._parse_time(t['Exit Time']),
                'size':     t['Position Size'],
                'ep':       t['Entry Price'],
                'direction': t['Position Type'],
                'pnl':      t['Profit/Loss'],
            })

        candle_curve = []
        times = df['time'].values
        closes = df['close'].values

        for i in range(len(df)):
            ts = times[i]
            if ts > 1e10:
                ts /= 1000
            
            candle_dt = datetime.fromtimestamp(ts)
            candle_close = closes[i]
            candle_time_str = candle_dt.strftime('%d-%m-%y %H:%M')

            equity = self.initial_capital
            unrealised = 0.0
            for pt in parsed_trades:
                if pt['exit_dt'] is None or pt['entry_dt'] is None:
                    continue
                if pt['exit_dt'] <= candle_dt:
                    equity += pt['pnl']
                elif pt['entry_dt'] <= candle_dt:
                    # Note: We should ideally use contract_val here too if we want perfect accuracy
                    # but for unrealised estimation, points * size is enough if size is in base asset
                    # Actually, process_trades returns size in contracts, so we need contract_val
                    # Let's check get_contract_value again
                    from core.trading import get_contract_value
                    cv = get_contract_value(self.symbol)
                    if pt['direction'] == 'LONG':
                        unrealised += (candle_close - pt['ep']) * pt['size'] * cv
                    else:
                        unrealised += (pt['ep'] - candle_close) * pt['size'] * cv

            candle_curve.append({
                'time': candle_time_str,
                'equity': round(equity + unrealised, 2)
            })

        return candle_curve
