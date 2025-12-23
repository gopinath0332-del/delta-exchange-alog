"""Strategy Runner Module."""

import time
import math
import pandas as pd
from typing import Optional

from core.logger import get_logger
from core.config import Config
from notifications.manager import NotificationManager
from api.rest_client import DeltaRestClient
from core.trading import execute_strategy_signal, get_trade_config

logger = get_logger(__name__)

def run_strategy_terminal(config: Config, strategy_name: str, symbol: str, mode: str, candle_type: str = "heikin-ashi"):
    """
    Run strategy in terminal mode with dashboard output.
    
    Args:
        config: Application configuration
        strategy_name: Name of strategy to run
        symbol: Trading symbol
        mode: 'live' or 'paper'
        candle_type: 'heikin-ashi' or 'standard'
    """
    # Initialize API and Notifications
    client = DeltaRestClient(config)
    notifier = NotificationManager(config)
    
    # Resolve Product & Precision
    logger.info(f"Resolving product details for {symbol}...")
    try:
        products_init = client.get_products()
        target_prod_init = next((p for p in products_init if p.get('symbol') == symbol), None)
    except Exception as e:
        logger.warning(f"Failed to fetch initial products: {e}")
        target_prod_init = None

    p_decimals = 2 # Default
    if target_prod_init and 'tick_size' in target_prod_init:
        try:
             ts = float(target_prod_init['tick_size'])
             if ts < 1 and ts > 0:
                 p_decimals = math.ceil(abs(math.log10(ts)))
             elif ts >= 1:
                 price_precision = 0 # No decimals for large ticks
             # E.g. 0.1 -> 1, 0.01 -> 2, 0.0001 -> 4
        except Exception as e:
             logger.warning(f"Error calculating precision: {e}")
    
    logger.info(f"Using {p_decimals} decimal places for {symbol} (Tick Size: {target_prod_init.get('tick_size') if target_prod_init else '?'})")
    
    # Initialize Strategy
    # Ideally we'd use a strategy factory, but for now we hardcode BTCUSD Double Dip
    if strategy_name.lower() in ["btcusd", "double-dip", "doubledip"]:
        from strategies.double_dip_rsi import DoubleDipRSIStrategy
        strategy = DoubleDipRSIStrategy()
        logger.info("Initialized DoubleDipRSIStrategy")
    elif strategy_name.lower() in ["cci-ema", "cciema"]:
        from strategies.cci_ema_strategy import CCIEMAStrategy
        strategy = CCIEMAStrategy()
        logger.info("Initialized CCIEMAStrategy")
    elif strategy_name.lower() in ["rs-50-ema", "rsi-50-ema", "rsi50ema"]:
        from strategies.rsi_50_ema_strategy import RSI50EMAStrategy
        strategy = RSI50EMAStrategy()
        logger.info("Initialized RSI50EMAStrategy")
    elif strategy_name.lower() in ["macd-psar-100ema", "macd_psar_100ema", "macdpsar"]:
        from strategies.macd_psar_100ema_strategy import MACDPSAR100EMAStrategy
        strategy = MACDPSAR100EMAStrategy()
        logger.info("Initialized MACDPSAR100EMAStrategy")
    else:
        logger.error(f"Unknown strategy: {strategy_name}")
        return

    # Wait for Internet Connectivity (RPi Startup Fix)
    logger.info("Waiting for network connectivity...")
    network_retries = 0
    while network_retries < 30:
        try:
            import socket
            sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
            sock.close()
            logger.info("Network connected.")
            break
        except OSError:
            network_retries += 1
            if network_retries % 5 == 0:
                logger.warning(f"Waiting for network... ({network_retries}/30)")
            time.sleep(2)
    else:
        logger.error("Network connection timed out after 60s. Proceeding anyway.")

    # Get System Hostname
    import socket
    hostname = socket.gethostname()

    logger.info("Starting strategy loop... Press Ctrl+C to stop.")
    
    # Get Trade Configuration for startup alert
    trade_config = get_trade_config(symbol)
    enabled_str = "ENABLED" if trade_config['enabled'] else "DISABLED"
    
    start_msg = (
        f"{symbol} {strategy_name} started on host: **{hostname}**\n"
        f"Candle Type: {candle_type}\n"
        f"Order Placement: **{enabled_str}**\n"
        f"Order Size: {trade_config['order_size']}\n"
        f"Leverage: {trade_config['leverage']}x"
    )
    
    notifier.send_status_message(
        f"Strategy Started (Terminal - {mode})", 
        start_msg
    )
    
    try:
        while True:
            try:
                # 1. Fetch Data (1h candles)
                # We need enough history for RSI(14). 
                # Use configured lookback days.
                end_time = int(time.time())
                days_lookback = getattr(config, 'default_historical_days', 30)
                start_time = end_time - (days_lookback * 24 * 3600) 
                
                # Fetch history
                # Note: This relies on _make_direct_request. If this fails, we need to check API docs/auth.
                response = client._make_direct_request(
                    "/v2/history/candles", 
                    params={
                        "resolution": "1h",
                        "symbol": symbol,
                        "start": start_time,
                        "end": end_time
                    }
                )
                
                candles = response.get("result", [])
                if not candles:
                    logger.warning(f"No candle data fetched for {symbol}")
                    time.sleep(10)
                    continue
                
                # Parse
                df = pd.DataFrame(candles)
                if 'close' in df.columns and 'time' in df.columns:
                     # Ensure correct sort order (ascending time)
                     # Check first and last time
                     first_time = df['time'].iloc[0]
                     last_time = df['time'].iloc[-1]
                     
                     # If descending (newest first), reverse it
                     if first_time > last_time:
                         df = df.iloc[::-1].reset_index(drop=True)
                     
                     # Determine Candle Type
                     use_ha = (candle_type.lower() == "heikin-ashi")
                     
                     if use_ha:
                         logger.info(f"Calculating Heikin Ashi for {len(df)} candles...")
                         # Full Heikin Ashi Transformation
                         # HA_Close = (O + H + L + C) / 4
                         # HA_Open = (Prev_HA_Open + Prev_HA_Close) / 2
                         # HA_High = Max(H, HA_Open, HA_Close)
                         # HA_Low = Min(L, HA_Open, HA_Close)
                         
                         df_ha = df.copy()
                         
                         # Ensure float types
                         o = df['open'].astype(float)
                         h = df['high'].astype(float)
                         l = df['low'].astype(float)
                         c = df['close'].astype(float)
                         
                         # 1. HA Close
                         df_ha['close'] = (o + h + l + c) / 4.0
                         
                         # 2. HA Open (Iterative calculation required)
                         ha_open_list = [0.0] * len(df)
                         ha_close_list = df_ha['close'].values
                         
                         # First candle: HA_Open = (Open + Close) / 2
                         ha_open_list[0] = (o.iloc[0] + c.iloc[0]) / 2.0
                         
                         for i in range(1, len(df)):
                             # HA_Open[i] = (HA_Open[i-1] + HA_Close[i-1]) / 2
                             ha_open_list[i] = (ha_open_list[i-1] + ha_close_list[i-1]) / 2.0
                             
                         df_ha['open'] = ha_open_list
                         
                         # 3. HA High / Low
                         df_ha['high'] = df_ha[['high', 'open', 'close']].max(axis=1)
                         df_ha['low'] = df_ha[['low', 'open', 'close']].min(axis=1)
                         
                         # Replace original df with HA df for strategy use
                         df = df_ha
                         closes = df['close']
                         logger.info("Heikin Ashi calculation complete.")
                     else:
                         closes = df['close'].astype(float)

                     # 2. Run Backtest / Warmup (If first run or empty history)
                     if not strategy.trades and not strategy.active_trade:
                         if len(df) > 1:
                             logger.info("Backtesting history for warmup...")
                             strategy.run_backtest(df.iloc[:-1])
                             logger.info("Backtest warmup complete.")

                             # --- RECONCILIATION STEP ---
                             # After backtest, we might still be out of sync if a trade happened 
                             # while bot was off or failed to record.
                             try:
                                 logger.info("Reconciling state with live positions...")
                                 
                                 # We need product_id for get_positions
                                 products = client.get_products()
                                 target_product = next((p for p in products if p.get('symbol') == symbol), None)
                                 
                                 positions = []
                                 if target_product:
                                     pid = target_product.get('id')
                                     logger.info(f"Resolved {symbol} to Product ID: {pid}")
                                     positions = client.get_positions(product_id=pid)
                                 else:
                                     logger.warning(f"Could not resolve product ID for {symbol}. Trying without ID (might fail)...")
                                     positions = client.get_positions()

                                 logger.info(f"Reconciliation: Fetched {len(positions)} positions.")
                                 logger.info(f"Positions raw type: {type(positions)}")
                                 # logger.info(f"Positions raw data: {positions}")

                                 # If we filtered by product_id, API might return the single object directly
                                 if isinstance(positions, dict):
                                     logger.info("Positions returned as single dict object. Wrapping in list.")
                                     positions = [positions]
                                 
                                 if positions and isinstance(positions, list):
                                     logger.info(f"First position type: {type(positions[0])}")
                                 
                                 # Find position for this symbol/product
                                 # Try multiple keys for symbol match
                                 current_pos = None
                                 for p in positions:
                                     if isinstance(p, (str, int, float)):
                                         logger.error(f"Position data is primitive type {type(p)}, expected dict: {p}")
                                         continue
                                     
                                     # If we already filtered by Product ID, this is likely the one.
                                     # But let's verify if possible, or just take it if it's the only one.
                                     if len(positions) == 1 and target_product:
                                          current_pos = p
                                          break
                                          
                                     p_symbol = p.get('product_symbol') or p.get('symbol') or p.get('product_id') # Fallback check
                                     if str(p_symbol) == symbol:
                                         current_pos = p
                                         break
                                 
                                 size = 0.0
                                 entry_price = 0.0
                                 if current_pos:
                                     val_size = current_pos.get('size')
                                     if val_size is not None:
                                         size = float(val_size)
                                     
                                     val_price = current_pos.get('entry_price')
                                     if val_price is not None:
                                         entry_price = float(val_price)
                                         
                                     logger.info(f"Reconciliation: Found position for {symbol}: Size={size}, Price={entry_price}")
                                 else:
                                     logger.info(f"Reconciliation: No position found for {symbol}")

                                 strategy.reconcile_position(size, entry_price)
                                 
                                 
                             except Exception as e:
                                 logger.error(f"Failed to reconcile positions: {e}")
                                 
                             # ---------------------------
                     
                     # Now process current live candle
                     current_time_ms = int(time.time() * 1000)
                     price = float(closes.iloc[-1])
                     
                     if hasattr(strategy, 'calculate_indicators'):
                          # For CCI Strategy and Updated Double Dip RSI
                          # Update indicators first (if not done inside check_signals, but check_signals usually does it)
                          # We rely on check_signals to calculate and return action
                          action, reason = strategy.check_signals(df, current_time_ms)
                          
                          # Extract latest values for logging/dashboard from strategy state
                          current_rsi = getattr(strategy, 'last_rsi', 0.0)
                          current_atr = getattr(strategy, 'last_atr', 0.0)
                          prev_rsi = 0.0 # Not explicitly tracked unless strategy does it
                     else:
                          # Legacy Fallback (should not be reached for Double Dip anymore)
                          current_rsi, prev_rsi = strategy.calculate_rsi(closes)
                          action, reason = strategy.check_signals(current_rsi, current_time_ms)
                          logger.info(f"Analysis: RSI={current_rsi:.2f} (Prev={prev_rsi:.2f}) | Action={action}")


                     
                     if action:
                         logger.info(f"SIGNAL: {action} - {reason}")
                         
                         # Execute Signal (Order + Alert)
                         result = execute_strategy_signal(
                             client=client,
                             notifier=notifier,
                             symbol=symbol,
                             action=action,
                             price=price,
                             rsi=current_rsi if hasattr(strategy, 'calculate_rsi') else getattr(strategy, 'last_cci', 0.0),
                             reason=reason,
                             mode=mode,
                             strategy_name=strategy_name
                         )
                         
                         # Check for successful execution and actual fill price
                         exec_price = price
                         if result and isinstance(result, dict):
                             if result.get('success') and result.get('execution_price'):
                                 exec_price = float(result['execution_price'])
                                 logger.info(f"Using actual execution price for state update: {exec_price}")
                         
                         # Execute Action (Update State) with CORRECT PRICE
                         strategy.update_position_state(action, current_time_ms, current_rsi, exec_price, reason=reason)
                else:
                     logger.error(f"Unexpected candle data format: {df.columns}")
                     time.sleep(10)
                     continue

                # Responsive Sleep (Align to next 10-minute mark)
                current_ts = int(time.time())
                sleep_seconds = 600 - (current_ts % 600)
                
                # --- FETCH LIVE POSITION FOR DASHBOARD ---
                live_pos_data = None
                try:
                    # Resolve product ID first
                    products = client.get_products()
                    target_product = next((p for p in products if p.get('symbol') == symbol), None)
                    
                    if target_product:
                        pid = target_product.get('id')
                        # Use get_positions (plural) which now hits /v2/positions/margined
                        all_positions = client.get_positions(product_id=pid)
                        
                        # Handle response structure: It returns a list
                        if isinstance(all_positions, dict):
                             all_positions = [all_positions]
                             
                        for p in all_positions:
                            if isinstance(p, dict):
                                 p_id = p.get('product_id')
                                 if p_id and str(p_id) == str(pid):
                                     live_pos_data = p
                                     break
                                 # If filtered by ID and only 1 result, take it
                                 if len(all_positions) == 1:
                                     live_pos_data = p
                                     break
                    else:
                        logger.warning(f"Could not resolve product ID for {symbol} for dashboard.")

                except Exception as e:
                    logger.warning(f"Failed to fetch live dashboard position: {e}")
                
                # --- DASHBOARD OUTPUT ---
                print("\n" + "="*80)
                print(f" {symbol} STRATEGY DASHBOARD  |  {time.strftime('%Y-%m-%d %H:%M:%S')}")
                print("="*80)
                
                pos_map = {0: "FLAT", 1: "LONG", -1: "SHORT"}
                pos_str = pos_map.get(strategy.current_position, "UNKNOWN")
                print(f" Strategy:     {strategy_name.upper()}")
                print(f" Status:       RUNNING ({mode.upper()})")
                print(f" Position:     {pos_str}")
                
                if live_pos_data and float(live_pos_data.get('size', 0)) != 0:
                    sz = float(live_pos_data.get('size', 0))
                    ep = float(live_pos_data.get('entry_price', 0))
                    pnl = float(live_pos_data.get('unrealized_pnl', 0))
                    liq = float(live_pos_data.get('liquidation_price', 0))
                    margin = float(live_pos_data.get('margin', 0))
                    
                    side_str = "LONG" if sz > 0 else "SHORT"
                    print(f" Exchange Pos: {side_str} ({abs(sz)} @ ${ep:,.{p_decimals}f})")
                    print(f" PnL (Unreal): {pnl:+.{p_decimals}f} USD")
                    print(f" Margin Used:  ${margin:,.2f}")
                    print(f" Liq Price:    ${liq:,.{p_decimals}f}")
                else:
                    print(f" Exchange Pos: FLAT")

                print(f" Candle Type:  {'Heikin Ashi' if use_ha else 'Standard'}")
                print("-" * 80)
                if strategy_name.lower() in ["btcusd", "double-dip", "doubledip"]:
                    print(f"   Price:      ${closes.iloc[-1]:,.{p_decimals}f}")
                    print(f"   RSI (14):   {getattr(strategy, 'last_rsi', 0.0):.2f}")
                    print(f"   ATR (14):   {getattr(strategy, 'last_atr', 0.0):.2f}")
                    if getattr(strategy, 'trailing_stop_level', None):
                        print(f"   Trail Stop: ${strategy.trailing_stop_level:,.{p_decimals}f}")
                    if getattr(strategy, 'next_partial_target', None):
                        print(f"   Partial TP: ${strategy.next_partial_target:,.{p_decimals}f}")

                elif hasattr(strategy, 'last_cci'): # Check for CCI Strategy
                    cci_len = getattr(strategy, 'cci_length', 30)
                    atr_len = getattr(strategy, 'atr_length', 14)
                    print(f"   Price:      ${closes.iloc[-1]:,.{p_decimals}f}")
                    print(f"   CCI ({cci_len}):   {strategy.last_cci:.2f} (Live)")
                    print(f"   EMA (50):   {strategy.last_ema:.{p_decimals}f}")
                    print(f"   ATR ({atr_len}):   {strategy.last_atr:.4f}")
                    if hasattr(strategy, 'last_closed_cci'):
                         print(f"   Last Closed ({getattr(strategy, 'last_closed_time_str', '-')})")
                         print(f"     CCI:      {strategy.last_closed_cci:.2f}")
                         print(f"     EMA:      {strategy.last_closed_ema:.{p_decimals}f}")
                elif hasattr(strategy, 'last_rsi') and hasattr(strategy, 'last_ema'): # Check for RSI+EMA Strategy
                    print(f"   Price:      ${closes.iloc[-1]:,.{p_decimals}f}")
                    print(f"   RSI (14):   {strategy.last_rsi:.2f}")
                    print(f"   EMA (50):   {strategy.last_ema:.{p_decimals}f}")
                    if hasattr(strategy, 'last_closed_rsi'):
                         print(f"   Last Closed ({getattr(strategy, 'last_closed_time_str', '-')})")
                         print(f"     RSI:      {strategy.last_closed_rsi:.2f}")
                         print(f"     EMA:      {strategy.last_closed_ema:.{p_decimals}f}")

                elif hasattr(strategy, 'last_macd_line'): # Check for MACD PSAR Strategy
                    print(f"   Price:      ${closes.iloc[-1]:,.{p_decimals}f}")
                    print(f"   MACD Fast:  {getattr(strategy, 'macd_fast', 14)} | Slow: {getattr(strategy, 'macd_slow', 26)} | Sig: {getattr(strategy, 'macd_signal', 9)}")
                    print(f"   MACD Hist:  {strategy.last_hist:.4f}")
                    print(f"   EMA ({getattr(strategy, 'ema_length', 100)}): {strategy.last_ema:.{p_decimals}f}")
                    print(f"   PSAR:       {strategy.last_sar:.{p_decimals}f}")
                
                print("-" * 80)
                
                if action:
                    print(f" >>> SIGNAL TRIGGERED: {action}")
                    print(f"     Reason: {reason}")
                else:
                    print(f" Last Signal: {reason or 'None'}")
                    
                print("-" * 80)
                print(" RECENT TRADE HISTORY")
                print("-" * 80)
                # Header
                label = getattr(strategy, 'indicator_label', "RSI")
                ind_label = f"Ent. {label}"
                x_ind_label = f"Exit {label}"
                print(f" {'Type':<8} {'Entry Time':<16} {'Ent. Price':<12} {ind_label:<10} {'Exit Time':<16} {'Exit Price':<12} {x_ind_label:<10} {'Points':<10} {'Status':<10}")
                
                # Helper to calc points
                def get_points_str(trade, current_price=None):
                    try:
                        # Use pre-calculated points if available
                        if trade.get('points') is not None:
                             return f"{float(trade['points']):+.{p_decimals}f}"

                        entry = float(trade.get('entry_price', 0))
                        # Fallback calculation if status matches known types
                        if 'OPEN' in trade['status'] and current_price:
                            current = float(current_price)
                            pts = current - entry if trade['type'] == 'LONG' else entry - current
                            return f"{pts:+.{p_decimals}f}"
                        elif 'CLOSED' in trade['status'] or 'PARTIAL' in trade['status']:
                            exit_p = float(trade.get('exit_price', 0))
                            pts = exit_p - entry if trade['type'] == 'LONG' else entry - exit_p
                            return f"{pts:+.{p_decimals}f}"
                        return "-"
                    except:
                        return "-"

                # Helper to get indicator value
                def get_ind_val(trade, prefix):
                    # Dynamic lookup based on strategy label
                    label = getattr(strategy, 'indicator_label', "RSI").lower()
                    key = f"{prefix}_{label}"
                    
                    # Try specific key first
                    val = trade.get(key)
                    if val is not None:
                        return f"{val:.2f}" if isinstance(val, float) else str(val)
                        
                    # Fallback to RSI/CCI hardcoded check if old data
                    keys_to_try = [f"{prefix}_rsi", f"{prefix}_cci"]
                    for k in keys_to_try:
                        val = trade.get(k)
                        if val is not None:
                            return f"{val:.2f}" if isinstance(val, float) else str(val)
                    return "-"

                # Active Trade first
                if strategy.active_trade:
                    t = strategy.active_trade
                    e_ind = get_ind_val(t, 'entry')
                    e_price = f"{float(t.get('entry_price', 0)):.{p_decimals}f}"
                    pts_str = get_points_str(t, closes.iloc[-1])
                    status = "OPEN (P)" if t.get('partial_exit') else "OPEN"
                    print(f" {t['type']:<8} {t['entry_time']:<16} {e_price:<12} {e_ind:<10} {'-':<16} {'-':<12} {'-':<10} {pts_str:<10} {status:<10}")
                
                # Past trades (last 5, reversed)
                recent_trades = strategy.trades[-5:] if strategy.trades else []
                for t in reversed(recent_trades):
                    e_ind = get_ind_val(t, 'entry')
                    x_ind = get_ind_val(t, 'exit')
                    e_price = f"{float(t.get('entry_price', 0)):.{p_decimals}f}"
                    x_price = f"{float(t.get('exit_price', 0)):.{p_decimals}f}"
                    pts_str = get_points_str(t)
                    status = t['status']
                    if t.get('partial_exit'):
                         status += " (P)"
                    print(f" {t['type']:<8} {t['entry_time']:<16} {e_price:<12} {e_ind:<10} {t['exit_time']:<16} {x_price:<12} {x_ind:<10} {pts_str:<10} {status:<10}")
                    
                print("-" * 80)
                print(f"sleeping for {sleep_seconds}s...")
                time.sleep(sleep_seconds)
                
            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
                time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Stopping strategy...")
        notifier.send_status_message(f"Strategy Stopped (Terminal)", f"{symbol} {strategy_name} stopped by user.")
