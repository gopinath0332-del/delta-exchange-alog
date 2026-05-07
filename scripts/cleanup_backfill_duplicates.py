#!/usr/bin/env python3
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.config import get_config
from core.logger import setup_logging, get_logger
import core.firestore_client as fs_client

def main():
    config = get_config()
    setup_logging(log_level="INFO")
    logger = get_logger("cleanup_backfill_duplicates")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Cleaning up backfill duplicates in Firestore...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        events = data.get("events", [])
        
        if len(events) <= 1:
            continue
            
        # Identify exit events
        exit_events = []
        for i, event in enumerate(events):
            action = event.get("action", "")
            if action.startswith("EXIT_"):
                exit_events.append((i, event))
                
        if len(exit_events) <= 1:
            continue
            
        # We have multiple exit events.
        # Logic: If one is a "Backfilled" event and there's another exit event that was already there
        # (especially one with an order_id or from a much earlier timestamp), remove the backfilled one.
        
        backfilled_exits = [e for e in exit_events if "Backfilled" in e[1].get("reason", "")]
        other_exits = [e for e in exit_events if "Backfilled" not in e[1].get("reason", "")]
        
        if backfilled_exits and other_exits:
            # We found a backfilled exit on a trade that already had an exit.
            # This means the backfill was likely a mis-match.
            indices_to_remove = [e[0] for e in backfilled_exits]
            
            # Revert the root fields if they were updated by the backfill
            # (Usually backfill updates exit_order_id, exit_price, pnl, etc.)
            # We should restore them from the 'other_exits' (the original one)
            original_exit = other_exits[0][1]
            
            logger.info(f"Trade {trade_id} already has a real exit. Removing backfill duplicate.")
            
            new_events = [e for i, e in enumerate(events) if i not in indices_to_remove]
            
            updates = {
                "events": new_events,
                "exit_action": original_exit.get("action"),
                "exit_side": original_exit.get("side"),
                "exit_price": original_exit.get("price"),
                "exit_execution_price": original_exit.get("price"),
                "exit_order_id": original_exit.get("order_id"),
                "pnl": original_exit.get("pnl"),
                "status": "CLOSED"
            }
            
            doc.reference.update(updates)
            count += 1

    logger.info(f"Successfully cleaned up {count} duplicate trades.")

if __name__ == "__main__":
    main()
