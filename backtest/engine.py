import pandas as pd
import datetime
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
        self.commission = self.bt_config.commission
        
        self.processed_trades = []
        self.equity_curve = []
        
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

    def _build_candle_equity_curve(self, df: pd.DataFrame) -> list:
        """Return a per-candle equity list with mark-to-market unrealised PnL."""
        # Pre-parse all trade times once to avoid repeated try/except parsing per candle
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
        closed_equity = self.initial_capital  # running total of realised PnL

        # Sort df by time (should already be sorted, but ensure it)
        times = df['time'].values
        closes = df['close'].values

        # Pointer into sorted parsed_trades by exit_dt for efficient closed_equity updates
        # We'll update closed_equity incrementally as we advance through candles
        # (trades are processed in chronological exit order after the main loop)

        for i in range(len(df)):
            ts = times[i]
            if ts > 1e10:
                ts /= 1000
            candle_dt = datetime.datetime.utcfromtimestamp(ts)
            candle_close = closes[i]
            candle_time_str = candle_dt.strftime('%d-%m-%y %H:%M')

            # Accumulate closed PnL and compute unrealised in a single pass
            equity = self.initial_capital
            unrealised = 0.0
            for pt in parsed_trades:
                if pt['exit_dt'] is None or pt['entry_dt'] is None:
                    continue
                if pt['exit_dt'] <= candle_dt:
                    equity += pt['pnl']
                elif pt['entry_dt'] <= candle_dt:
                    if pt['direction'] == 'LONG':
                        unrealised += (candle_close - pt['ep']) * pt['size']
                    else:
                        unrealised += (pt['ep'] - candle_close) * pt['size']

            candle_curve.append({
                'time':   candle_time_str,
                'equity': equity + unrealised,
            })

        return candle_curve

    # ---------------------------------------------------------------------------
    # MAE / MFE Calculation
    # ---------------------------------------------------------------------------

    def _calculate_mae_mfe(
        self,
        df: pd.DataFrame,
        raw_trades: List[Dict[str, Any]]
    ) -> None:
        """
        Annotate each raw trade dict (in-place) with Maximum Adverse Excursion
        (MAE) and Maximum Favorable Excursion (MFE) values.

        Definitions:
          - MAE = the largest price move AGAINST the position during the trade
                  (measures how much heat the trade took before resolving).
          - MFE = the largest price move IN FAVOUR of the position during the
                  trade (measures the best unrealised profit available).

        Both values are returned in absolute price units and as a percentage
        of the entry price.

        The candle slice used is all bars whose timestamp falls between
        entry_time and exit_time (inclusive), matched against df['time'].

        Args:
            df:          The full OHLCV DataFrame used for the backtest.
            raw_trades:  List of raw trade dicts produced by strategy.run_backtest().
        """
        # Build a quick lookup: time_value -> row_index for efficient bar matching.
        # df['time'] may be in seconds or milliseconds; normalise to seconds.
        time_vals = df['time'].values.copy().astype(float)
        # Convert timestamp to seconds if it looks like milliseconds (>= 1e10)
        time_vals = np.where(time_vals >= 1e10, time_vals / 1000.0, time_vals)

        for trade in raw_trades:
            # Default — will be overridden if we can locate the candle window
            trade['mae_price'] = 0.0
            trade['mae_pct']   = 0.0
            trade['mfe_price'] = 0.0
            trade['mfe_pct']   = 0.0

            trade_type   = trade.get('type', 'LONG')
            entry_price  = None
            entry_dt     = self._parse_time(trade.get('entry_time', ''))
            exit_dt      = self._parse_time(trade.get('exit_time', ''))

            try:
                entry_price = float(trade.get('entry_price', 0))
            except (TypeError, ValueError):
                continue

            if entry_price is None or entry_price <= 0:
                continue

            # Resolve candle window if we have valid timestamps.
            # _parse_time() can return Python None OR a pandas NaT (from pd.to_datetime),
            # so we must guard against both. pd.isnull() handles both cases safely.
            entry_valid = entry_dt is not None and not pd.isnull(entry_dt)
            exit_valid  = exit_dt  is not None and not pd.isnull(exit_dt)

            if entry_valid and exit_valid:
                # Convert parsed datetimes to unix seconds for comparison
                entry_ts = entry_dt.replace(tzinfo=datetime.timezone.utc).timestamp()
                exit_ts  = exit_dt.replace(tzinfo=datetime.timezone.utc).timestamp()

                # Allow a small tolerance (1/2 bar) to handle rounding
                bar_duration_sec = 3600  # fallback: 1-hour bars
                if len(time_vals) > 1:
                    bar_duration_sec = max(float(time_vals[1] - time_vals[0]), 60)

                tolerance = bar_duration_sec * 0.5

                # Mask: bars that overlap the trade window
                mask = (time_vals >= entry_ts - tolerance) & (time_vals <= exit_ts + tolerance)
                indices = np.where(mask)[0]
            else:
                # No timestamps — fall back to first / last bar (edge case)
                indices = np.arange(len(df))

            if len(indices) == 0:
                continue

            # Extract high / low arrays for the trade window
            highs = df['high'].values[indices].astype(float)
            lows  = df['low'].values[indices].astype(float)

            if len(highs) == 0 or len(lows) == 0:
                continue

            max_high = float(np.nanmax(highs))
            min_low  = float(np.nanmin(lows))

            if trade_type == 'LONG':
                # Favourable move: price went UP from entry (best high reached)
                mfe_price = max(max_high - entry_price, 0.0)
                # Adverse move: price went DOWN from entry (worst low reached)
                mae_price = max(entry_price - min_low, 0.0)
            else:  # SHORT
                # Favourable move: price went DOWN from entry (lowest low reached)
                mfe_price = max(entry_price - min_low, 0.0)
                # Adverse move: price went UP from entry (highest high reached)
                mae_price = max(max_high - entry_price, 0.0)

            # Convert to percentage of entry price
            trade['mae_price'] = round(mae_price, 8)
            trade['mae_pct']   = round((mae_price / entry_price) * 100, 4)
            trade['mfe_price'] = round(mfe_price, 8)
            trade['mfe_pct']   = round((mfe_price / entry_price) * 100, 4)

    def run(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
        logger.info(f"Running backtest for {self.symbol} on {self.timeframe} timeframe")

        # Run the strategy's built-in backtest logic to generate raw signals
        self.strategy.run_backtest(df)
        raw_trades = getattr(self.strategy, 'trades', [])

        # Annotate every raw trade with MAE / MFE BEFORE the processing loop so
        # that the values are available when building each processed_trade dict.
        self._calculate_mae_mfe(df, raw_trades)

        # Keep track of active partials to apply to the next matching trade exit
        partial_remaining_size_map = {}

        # Pre-pass: assign stable numeric IDs so each PARTIAL and its matching CLOSED
        # exit share the same key, even if multiple trades share the same type+entry_time.
        _next_id = 0
        _partial_pending: dict = {}  # "type_entry_time" -> id
        for t in raw_trades:
            pair_key = f"{t.get('type', '')}_{t.get('entry_time', '')}"
            if t.get('status') == 'PARTIAL':
                t['_backtest_id'] = _next_id
                _partial_pending[pair_key] = _next_id
                _next_id += 1
            elif pair_key in _partial_pending:
                # Final close leg of a partial — reuse the same ID
                t['_backtest_id'] = _partial_pending.pop(pair_key)
            else:
                t['_backtest_id'] = _next_id
                _next_id += 1

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
            
            # Use the pre-assigned stable ID so partial/close pairs always share the same key,
            # avoiding collisions when multiple trades of the same type share an entry timestamp.
            trade_key = trade['_backtest_id']
            
            if trade_key in partial_remaining_size_map and trade['status'] != 'PARTIAL':
                # This is the final 50% closing exit of a previously partially closed position
                position_size = partial_remaining_size_map[trade_key]
                del partial_remaining_size_map[trade_key]
            else:
                # Standard full position sizing (leverage scales notional, trade_capital is the margin)
                position_size = (trade_capital * self.leverage) / entry_price
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
                
            # Hard Stop Loss Check — caps loss at stop_loss_pct of margin for this segment
            if self.stop_loss_pct is not None:
                segment_margin = (position_size * entry_price) / self.leverage
                max_loss = segment_margin * self.stop_loss_pct
                if pnl < -max_loss:
                    pnl = -max_loss
                    price_diff = max_loss / position_size
                    exit_price = (entry_price - price_diff) if trade['type'] == 'LONG' else (entry_price + price_diff)
                    trade['status'] = 'EXCHANGE SL'
                
            # Commission
            # Fee is based on the dollar volume of the portion of the position being exited/entered
            trade_dollar_volume = entry_price * position_size
            comm_cost = (trade_dollar_volume * self.commission) + ((exit_price * position_size) * self.commission)
            pnl -= comm_cost
            
            self.equity += pnl
            return_pct = (pnl / trade_capital) * 100
            
            # Calculate duration if possible
            duration_str = "N/A"
            bars_held = 0
            dt_entry = self._parse_time(trade.get('entry_time', ''))
            dt_exit = self._parse_time(trade.get('exit_time', ''))
            if dt_entry and dt_exit:
                diff = dt_exit - dt_entry
                duration_str = str(diff)
                
                # Estimate bars held based on timeframe (e.g., '1h', '15m')
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
                except Exception:
                    pass
            
            processed_trade = {
                'Symbol': self.symbol,
                'Leverage': self.leverage,
                'Entry Time': trade.get('entry_time', ''),
                'Exit Time': trade.get('exit_time', ''),
                'Position Type': trade['type'],
                'Exit Type': trade.get('status', 'CLOSED'),
                'Position Size': position_size,
                'Entry Price': entry_price,
                'Exit Price': exit_price,
                'Fee': comm_cost,
                'Profit/Loss': pnl,
                'Return %': return_pct,
                'Duration': duration_str,
                'Bars Held': bars_held,
                # MAE / MFE fields — populated by _calculate_mae_mfe() above.
                # These represent the worst drawdown and best unrealised profit
                # experienced during the life of this trade, measured in price
                # points and as a percentage of entry price.
                'MAE Price': trade.get('mae_price', 0.0),
                'MAE %':     trade.get('mae_pct',   0.0),
                'MFE Price': trade.get('mfe_price', 0.0),
                'MFE %':     trade.get('mfe_pct',   0.0),
            }
            self.processed_trades.append(processed_trade)

        logger.info(f"Backtest engine finished. Final equity: ${self.equity:.2f}")

        # Build per-candle mark-to-market equity curve
        self.equity_curve = self._build_candle_equity_curve(df)

        # Construct DataFrame for equity curve
        equity_df = pd.DataFrame(self.equity_curve)
        if len(equity_df) > 1:
            # Try parsing time for proper plotting later
            try:
                equity_df['time'] = pd.to_datetime(
                    equity_df['time'].apply(lambda x: x.split(' (')[0] if isinstance(x, str) else x),
                    format='%d-%m-%y %H:%M',
                    errors='coerce'
                )
            except Exception:
                pass

        return self.processed_trades, equity_df
