#!/usr/bin/env python3
import sys
import os
import dateutil.parser
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import get_config
from core.logger import setup_logging, get_logger
import core.firestore_client as fs_client
from api.rest_client import DeltaRestClient

def main():
    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger("fix_timestamps")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    client = DeltaRestClient(config)
    
    logger.info("Fetching all closed orders from Delta Exchange to get true timestamps...")
    orders = client.get_order_history(state="closed")
    order_map = {str(o['id']): o for o in orders}
    logger.info(f"Loaded {len(order_map)} orders from exchange.")

    logger.info("Syncing Firestore backfilled timestamps...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        events = data.get("events", [])
        
        needs_update = False
        updates = {}
        
        # Check every event
        for event in events:
            if "Backfilled" in event.get("reason", ""):
                order_id = str(event.get("order_id"))
                if order_id in order_map:
                    true_ts_str = order_map[order_id].get("created_at")
                    if true_ts_str:
                        true_ts = dateutil.parser.isoparse(true_ts_str)
                        # Compare (using string representation to avoid tz issues in comparison)
                        curr_ts = event.get("timestamp")
                        
                        logger.info(f"Trade {trade_id}: Fixing backfilled timestamp for order {order_id} -> {true_ts}")
                        event["timestamp"] = true_ts
                        needs_update = True
                        
        if needs_update:
            # Also update root exit_timestamp if it matches the fixed event
            last_event = events[-1]
            if last_event.get("action", "").startswith("EXIT_"):
                updates["exit_timestamp"] = last_event.get("timestamp")
            
            updates["events"] = events
            doc.reference.update(updates)
            count += 1

    logger.info(f"Successfully fixed timestamps for {count} trades.")

if __name__ == "__main__":
    main()
