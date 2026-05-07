#!/usr/bin/env python3
import sys
import os
from datetime import datetime
import dateutil.parser

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import get_config
from core.logger import setup_logging, get_logger
import core.firestore_client as fs_client
from api.rest_client import DeltaRestClient

def main():
    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger("full_reconcile")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    client = DeltaRestClient(config)
    logger.info("Fetching all closed orders from exchange...")
    exchange_orders = client.get_order_history(state="closed")
    logger.info(f"Loaded {len(exchange_orders)} orders.")

    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    docs = trades_ref.stream()

    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        symbol = data.get("symbol")
        entry_size = float(data.get("order_size", 0))
        entry_side = data.get("entry_side", "buy")
        
        # Get existing event order IDs
        events = data.get("events", [])
        known_order_ids = {str(e.get("order_id")) for e in events if e.get("order_id")}
        
        # Calculate currently exited size
        exited_size = sum([float(e.get("order_size", 0)) for e in events if e.get("action", "").startswith("EXIT_") or "MILESTONE" in e.get("action", "")])
        
        remaining_size = entry_size - exited_size
        if remaining_size <= 0.1: # Allow for small float precision
            continue
            
        logger.info(f"Trade {trade_id} ({symbol}): {exited_size}/{entry_size} exited. Searching for remaining {remaining_size} units...")
        
        entry_time = data.get("entry_timestamp")
        if not entry_time: continue
        if hasattr(entry_time, "to_datetime"):
            entry_dt = entry_time.to_datetime().replace(tzinfo=None)
        else:
            entry_dt = entry_time.replace(tzinfo=None)
            
        # Find all exchange orders for this symbol after entry_time that are NOT already matched
        potential_orders = []
        for o in exchange_orders:
            if o.get("product_symbol") != symbol: continue
            oid = str(o.get("id"))
            if oid in known_order_ids: continue
            
            # Check side
            order_side = o.get("side")
            if not ((order_side == "buy" and entry_side == "sell") or (order_side == "sell" and entry_side == "buy")):
                continue
                
            # Check time
            order_dt = dateutil.parser.isoparse(o['created_at']).replace(tzinfo=None)
            if order_dt < entry_dt: continue
            
            potential_orders.append(o)
            
        if not potential_orders:
            continue
            
        # Sort potential orders by time
        potential_orders.sort(key=lambda x: x['created_at'])
        
        # Try to fill the remaining size
        new_updates = []
        temp_remaining = remaining_size
        
        for o in potential_orders:
            if temp_remaining <= 0.1: break
            
            o_size = float(o.get("size", 0))
            # If the order size is close to what we need, or it's a partial fill
            if o_size <= (temp_remaining + 1):
                logger.info(f"  -> Matching Order {o['id']} (size {o_size}) to fill gap.")
                
                # Determine action
                is_milestone = o_size < (entry_size * 0.9) # If order is less than 90% of entry, it's likely a milestone
                # Actually, check if it's the final piece
                is_final = abs(o_size - temp_remaining) < 1
                
                if is_milestone and not is_final:
                    action = "MILESTONE_EXIT"
                else:
                    action = "EXIT_LONG" if entry_side == "buy" else "EXIT_SHORT"
                
                # Calculate PnL (simplified for backfill)
                entry_price = float(data.get("entry_execution_price") or data.get("entry_price") or 0)
                exit_price = float(o.get("avg_fill_price") or 0)
                pnl = 0
                if entry_price and exit_price:
                    pnl_per_unit = (exit_price - entry_price) if entry_side == "buy" else (entry_price - exit_price)
                    pnl = pnl_per_unit * o_size
                
                ts = dateutil.parser.isoparse(o['created_at'])
                
                # Call journal_trade for each part
                fs_client.journal_trade(
                    symbol=symbol,
                    action=action,
                    side=o.get("side"),
                    price=exit_price,
                    order_size=o_size,
                    leverage=data.get("leverage", 1),
                    mode=data.get("mode", "live"),
                    trade_id=trade_id,
                    is_entry=False,
                    is_partial_exit=not is_final,
                    pnl=pnl,
                    order_id=str(o['id']),
                    timestamp=ts,
                    reason="Backfilled Milestone Exit" if not is_final else "Backfilled Final Exit"
                )
                temp_remaining -= o_size

    logger.info("Reconciliation complete.")

if __name__ == "__main__":
    main()
