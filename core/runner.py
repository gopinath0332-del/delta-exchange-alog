"""Strategy Runner Module."""

import time
import pandas as pd
from typing import Optional

from core.logger import get_logger
from core.config import Config
from notifications.manager import NotificationManager
from api.rest_client import DeltaRestClient

logger = get_logger(__name__)

def run_strategy_terminal(config: Config, strategy_name: str, symbol: str, mode: str):
    """
    Run strategy in terminal mode with dashboard output.
    
    Args:
        config: Application configuration
        strategy_name: Name of strategy to run
        symbol: Trading symbol
        mode: 'live' or 'paper'
    """
    # Initialize API and Notifications
    client = DeltaRestClient(config)
    notifier = NotificationManager(config)
    
    # Initialize Strategy
    # Ideally we'd use a strategy factory, but for now we hardcode BTCUSD Double Dip
    if strategy_name.lower() in ["btcusd", "double-dip", "doubledip"]:
        from strategies.double_dip_rsi import DoubleDipRSIStrategy
        strategy = DoubleDipRSIStrategy()
        logger.info("Initialized DoubleDipRSIStrategy")
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
    notifier.send_status_message(
        f"Strategy Started (Terminal - {mode})", 
        f"{symbol} {strategy_name} started on host: **{hostname}**"
    )
    
    try:
        while True:
            try:
                # 1. Fetch Data (1h candles)
                # We need enough history for RSI(14). 
                # 100 is "safe" but 300 provides better precision for Wilder's smoothing.
                end_time = int(time.time())
                start_time = end_time - (300 * 3600) 
                
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
                     
                     # Determine Candle Type (Default to Heikin Ashi for this strategy as per GUI)
                     use_ha = True 
                     
                     if use_ha:
                         # Calculate Heikin Ashi Close = (O + H + L + C) / 4
                         # Ensure all columns exist and are float
                         for col in ['open', 'high', 'low', 'close']:
                             if col not in df.columns:
                                 logger.error(f"Missing column for HA: {col}")
                                 closes = df['close'].astype(float) # Fallback
                                 break
                         else:
                             o = df['open'].astype(float)
                             h = df['high'].astype(float)
                             l = df['low'].astype(float)
                             c = df['close'].astype(float)
                             df['close'] = (o + h + l + c) / 4.0
                             closes = df['close']
                     else:
                         closes = df['close'].astype(float)

                     # 2. Run Backtest / Warmup (If first run or empty history)
                     if not strategy.trades and not strategy.active_trade:
                         if len(df) > 1:
                             logger.info("Backtesting history for warmup...")
                             strategy.run_backtest(df.iloc[:-1])
                     
                     # Now process current live candle
                     current_time_ms = int(time.time() * 1000)
                     current_rsi, prev_rsi = strategy.calculate_rsi(closes)
                     action, reason = strategy.check_signals(current_rsi, current_time_ms)
                     
                     logger.info(f"Analysis: RSI={current_rsi:.2f} (Prev={prev_rsi:.2f}) | Action={action}")
                     
                     if action:
                         logger.info(f"SIGNAL: {action} - {reason}")
                         
                         # Execute Action (Update State)
                         strategy.update_position_state(action, current_time_ms, current_rsi)
                         
                         # Send Notification
                         try:
                             price = closes.iloc[-1]
                             notifier.send_trade_alert(
                                 symbol=symbol,
                                 side=action,
                                 price=float(price),
                                 rsi=current_rsi,
                                 reason=reason
                             )
                         except Exception as e:
                             logger.error(f"Failed to send notification: {e}")
                else:
                     logger.error(f"Unexpected candle data format: {df.columns}")
                     time.sleep(10)
                     continue

                # Responsive Sleep (Align to next 10-minute mark)
                current_ts = int(time.time())
                sleep_seconds = 600 - (current_ts % 600)
                
                # --- DASHBOARD OUTPUT ---
                print("\n" + "="*80)
                print(f" {symbol} STRATEGY DASHBOARD  |  {time.strftime('%Y-%m-%d %H:%M:%S')}")
                print("="*80)
                
                pos_map = {0: "FLAT", 1: "LONG", -1: "SHORT"}
                pos_str = pos_map.get(strategy.current_position, "UNKNOWN")
                print(f" Status:       RUNNING ({mode.upper()})")
                print(f" Position:     {pos_str}")
                print(f" Candle Type:  {'Heikin Ashi' if use_ha else 'Standard'}")
                print("-" * 80)
                print(f" Market Data:")
                print(f"   Price:      ${closes.iloc[-1]:,.2f}")
                print(f"   RSI (14):   {current_rsi:.2f}")
                print(f"   Prev RSI:   {prev_rsi:.2f}")
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
                print(f" {'Type':<8} {'Entry Time':<16} {'Ent. RSI':<10} {'Exit Time':<16} {'Exit RSI':<10} {'Status':<10}")
                
                # Active Trade first
                if strategy.active_trade:
                    t = strategy.active_trade
                    # Truncate RSI for display if float
                    e_rsi = f"{t['entry_rsi']:.2f}" if isinstance(t['entry_rsi'], float) else str(t['entry_rsi'])
                    print(f" {t['type']:<8} {t['entry_time']:<16} {e_rsi:<10} {'-':<16} {'-':<10} {'OPEN':<10}")
                
                # Past trades (last 5, reversed)
                recent_trades = strategy.trades[-5:] if strategy.trades else []
                for t in reversed(recent_trades):
                    e_rsi = f"{t['entry_rsi']:.2f}" if isinstance(t['entry_rsi'], float) else str(t['entry_rsi'])
                    x_rsi = f"{t['exit_rsi']:.2f}" if isinstance(t['exit_rsi'], float) else str(t['exit_rsi'])
                    print(f" {t['type']:<8} {t['entry_time']:<16} {e_rsi:<10} {t['exit_time']:<16} {x_rsi:<10} {t['status']:<10}")
                    
                if not recent_trades and not strategy.active_trade:
                    print(" (No trades recorded yet)")
                    
                print("="*80)
                print(f"Sleeping for {sleep_seconds}s...")
                time.sleep(sleep_seconds)
                
            except Exception as e:
                logger.error(f"Error in strategy loop: {e}")
                time.sleep(60)

    except KeyboardInterrupt:
        logger.info("Stopping strategy...")
        notifier.send_status_message(f"Strategy Stopped (Terminal)", f"{symbol} {strategy_name} stopped by user.")
