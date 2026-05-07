#!/usr/bin/env python3
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import get_config
from core.logger import setup_logging, get_logger
import core.firestore_client as fs_client
from api.rest_client import DeltaRestClient

def main():
    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger("check_partials")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    client = DeltaRestClient(config)
    orders = client.get_order_history(state="closed")
    
    logger.info("Checking for missing final exits on partially closed trades...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    docs = trades_ref.stream()

    for doc in docs:
        data = doc.to_dict()
        if data.get("status") not in ["PARTIAL_CLOSED", "OPEN"]:
            continue
            
        trade_id = doc.id
        symbol = data.get("symbol")
        entry_size = data.get("order_size", 0)
        
        events = data.get("events", [])
        exited_size = sum([e.get("order_size", 0) for e in events if e.get("action", "").startswith("EXIT_") or e.get("action", "") == "MILESTONE_EXIT"])
        
        remaining_size = entry_size - exited_size
        if remaining_size <= 0:
            # Trade is actually closed!
            logger.info(f"Trade {trade_id} has remaining size {remaining_size} but status is {data.get('status')}. Marking as CLOSED.")
            doc.reference.update({"status": "CLOSED"})
            continue
            
        # Check if there is an exchange order that matches the remaining size
        entry_time = data.get("entry_timestamp")
        if not entry_time: continue
        
        # Firestore Timestamp to datetime
        if hasattr(entry_time, "to_datetime"):
            entry_dt = entry_time.to_datetime().replace(tzinfo=None)
        else:
            entry_dt = entry_time.replace(tzinfo=None)
            
        # Look for a closing order
        for order in orders:
            order_time = datetime.fromisoformat(order['created_at'].replace('Z', '+00:00')).replace(tzinfo=None)
            if order_time > entry_dt and order['product_symbol'] == symbol:
                order_id = str(order['id'])
                # Skip if already in events
                if any([str(e.get("order_id")) == order_id for e in events]):
                    continue
                    
                # Match by side and size?
                entry_side = data.get("entry_side")
                order_side = order.get("side")
                if (order_side == "buy" and entry_side == "sell") or (order_side == "sell" and entry_side == "buy"):
                    # Potential exit!
                    order_size = float(order.get("size", 0))
                    logger.info(f"Trade {trade_id}: Found potential missing order {order_id} size {order_size} at {order_time}")
                    # If this order covers the remaining size, it's the final exit
                    if abs(order_size - remaining_size) < 1:
                        logger.info(f"  -> This looks like the FINAL EXIT!")
                    else:
                        logger.info(f"  -> This looks like ANOTHER PARTIAL EXIT!")

if __name__ == "__main__":
    from datetime import datetime
    main()
