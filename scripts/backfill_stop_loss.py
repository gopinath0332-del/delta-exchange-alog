#!/usr/bin/env python3
import sys
import os
import argparse
import time
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import get_config
from core.logger import setup_logging, get_logger
import core.firestore_client as fs_client
from api.rest_client import DeltaRestClient

def get_product_contract_value(client: DeltaRestClient, product_id: int) -> float:
    # Basic caching to avoid hammering API
    if not hasattr(client, "_product_cache"):
        client._product_cache = {}
        try:
            products = client.get_products()
            for p in products:
                client._product_cache[p['id']] = float(p.get('contract_value', 1.0))
        except Exception:
            pass
    return client._product_cache.get(product_id, 1.0)

def main():
    parser = argparse.ArgumentParser(description="Backfill missing bracket stop-loss orders in Firestore")
    parser.add_argument("--execute", action="store_true", help="Actually execute the updates (default is dry-run)")
    parser.add_argument("--days", type=int, default=30, help="Number of days to look back")
    args = parser.parse_args()

    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger("backfill")

    if args.execute:
        logger.info("RUNNING IN EXECUTE MODE. Firestore WILL be modified.")
    else:
        logger.info("RUNNING IN DRY-RUN MODE. No data will be modified.")

    client = DeltaRestClient(config)

    # 1. Fetch orders from the last 30 days
    end_time_us = int(time.time() * 1_000_000)
    start_time_us = int((time.time() - (args.days * 86400)) * 1_000_000)

    logger.info(f"Fetching Delta Exchange order history for the last {args.days} days...")
    orders = client.get_order_history(state="closed", start_time=start_time_us, end_time=end_time_us)
    
    # Filter for filled/closed orders that are market_orders (which is what triggered stops become)
    # or stop_market_orders if Delta classifies them differently.
    stop_orders = [
        o for o in orders 
        if o.get('state') == 'closed' and o.get('order_type') in ['market_order', 'stop_market_order', 'bracket_stop']
    ]
    logger.info(f"Found {len(stop_orders)} executed market/stop orders in the last {args.days} days.")

    # 2. Fetch all Firebase trades from the last 30 days
    logger.info("Fetching Firestore trades...")
    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized. Ensure FIREBASE_CREDENTIALS_PATH is set.")
        return

    # To avoid fetching the entire database, we fetch trades that were created or active in the last 30 days.
    # Since we don't have complex querying here, let's just fetch recent ones or all if small.
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    docs = trades_ref.stream()

    trades = {}
    known_order_ids = set()

    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        trades[doc.id] = data
        
        # Track all known order IDs
        if data.get('entry_order_id'):
            known_order_ids.add(str(data.get('entry_order_id')))
        if data.get('exit_order_id'):
            known_order_ids.add(str(data.get('exit_order_id')))
        
        for event in data.get('events', []):
            if event.get('order_id'):
                known_order_ids.add(str(event.get('order_id')))

    logger.info(f"Loaded {len(trades)} trades from Firestore. Found {len(known_order_ids)} known order IDs.")

    # 3. Cross-Mapping
    missing_updates = []
    
    # Sort stop orders chronologically
    stop_orders.sort(key=lambda x: x.get('created_at', 0))

    for order in stop_orders:
        order_id = str(order.get('id'))
        symbol = order.get('product_symbol')
        
        if order_id in known_order_ids:
            continue
            
        # This is a missing stop-loss order!
        order_time_raw = order.get('created_at', 0)
        # Parse time to datetime
        if isinstance(order_time_raw, str):
            order_time = datetime.fromisoformat(order_time_raw.replace('Z', '+00:00')).replace(tzinfo=None)
        else:
            order_time = datetime.utcfromtimestamp(order_time_raw / 1_000_000)
            
        logger.info(f"Found MISSING stop-loss: {order_id} | {symbol} | Time: {order_time}")
        
        # Find the matching trade. 
        # Criteria: symbol matches, AND entry_timestamp < order_time.
        # Matching logic:
        # 1. Trade must be on the same symbol
        # 2. Trade entry must be BEFORE the order creation
        # 3. Preference:
        #    a. Trades with [SYNC] or NO POSITION in the exit reason (these are placeholders)
        #    b. Trades that are still OPEN
        #    c. Trades that closed very recently
        
        candidates = []
        for trade_id, trade in trades.items():
            if trade.get('symbol') == symbol:
                entry_time = trade.get('entry_timestamp')
                # Handle Firestore Timestamp objects or datetimes
                if hasattr(entry_time, 'to_datetime'):
                    entry_dt = entry_time.to_datetime().replace(tzinfo=None)
                elif isinstance(entry_time, datetime):
                    entry_dt = entry_time.replace(tzinfo=None)
                else:
                    continue

                if entry_dt and entry_dt < order_time:
                    # Calculate priority
                    priority = 0
                    reason = str(trade.get('exit_reason', ''))
                    if "[SYNC]" in reason or "NO POSITION" in reason:
                        priority = 100 # Highest priority: it's a placeholder
                    elif trade.get('status') == 'OPEN':
                        priority = 50
                    else:
                        priority = 1
                        
                    # Calculate time diff (closer is better)
                    time_diff = (order_time - entry_dt).total_seconds()
                    
                    # If it's a SYNC trade, we don't care if it's "closed" already
                    candidates.append({
                        'id': trade_id,
                        'priority': priority,
                        'time_diff': time_diff,
                        'data': trade
                    })
        
        if not candidates:
            logger.warning(f"  -> Could not find any prior trade for {symbol} to attach stop-loss {order.get('id')}")
            continue
            
        # Sort by priority (desc) then time_diff (asc)
        candidates.sort(key=lambda x: (-x['priority'], x['time_diff']))
        best_match = candidates[0]
        best_match_id = best_match['id']
        best_match_data = best_match['data']
        
        logger.info(f"  -> MATCHED to trade {best_match_id} (Priority: {best_match['priority']}, Opened {best_match['time_diff']/3600:.1f} hours prior, Status: {best_match_data.get('status')})")
        
        # Calculate PnL Approximation
        exit_price = float(order.get('average_fill_price', 0))
        entry_price = float(best_match_data.get('entry_price', 0))
        size = float(order.get('size', 0))
        product_id = int(order.get('product_id', 0))
        
        contract_value = get_product_contract_value(client, product_id)
        
        pnl = 0.0
        if entry_price > 0 and exit_price > 0:
            entry_side = best_match_data.get('entry_side', 'buy')
            # Assuming linear for simplicity (most contracts on Delta are linear USDT/USDC, BTC/ETH might be inverse)
            if entry_side == 'buy':
                pnl = (exit_price - entry_price) * size * contract_value
            else:
                pnl = (entry_price - exit_price) * size * contract_value
                
        # Queue the update
        missing_updates.append({
            'trade_id': best_match_id,
            'order': order,
            'pnl': pnl,
            'exit_price': exit_price,
            'size': size,
            'side': order.get('side'),
            'product_id': product_id
        })

    logger.info(f"Identified {len(missing_updates)} trades that need updating.")
    
    if not args.execute:
        logger.info("DRY-RUN mode. Exiting without modifying Firestore.")
        for update in missing_updates:
            print(f"Would update trade {update['trade_id']} with SL Order {update['order'].get('id')} (PnL: {update['pnl']:.2f})")
        return

    # 4. Execute Updates
    logger.info("Executing Firestore updates...")
    for idx, update in enumerate(missing_updates):
        order = update['order']
        logger.info(f"Updating {idx+1}/{len(missing_updates)}: Trade {update['trade_id']} <- Order {order.get('id')}")
        
        # Use entry_side from the matched trade to determine the correct exit action name
        entry_side = best_match_data.get('entry_side', 'buy')
        action = "EXIT_LONG" if entry_side == "buy" else "EXIT_SHORT"
        
        try:
            fs_client.journal_trade(
                symbol=order.get('product_symbol'),
                action=action,
                side=update['side'],
                price=update['exit_price'],
                execution_price=update['exit_price'],
                order_size=int(update['size']),
                leverage=0,  # Retains existing leverage
                mode="live",
                trade_id=update['trade_id'],
                is_entry=False,
                pnl=update['pnl'],
                order_id=str(order.get('id')),
                reason="Exchange Triggered Bracket Stop-Loss (Backfilled)"
            )
        except Exception as e:
            logger.error(f"Failed to update trade {update['trade_id']}: {e}")

    logger.info("Backfill complete.")

if __name__ == "__main__":
    main()
