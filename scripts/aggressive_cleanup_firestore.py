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
    logger = get_logger("aggressive_cleanup")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Performing AGGRESSIVE deduplication in Firestore...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        events = data.get("events", [])
        
        # Split events into entry and exit
        entry_events = [e for e in events if e.get("action", "").startswith("ENTRY_")]
        exit_events = [e for e in events if e.get("action", "").startswith("EXIT_")]
        
        if len(exit_events) <= 1:
            continue
            
        logger.info(f"Trade {trade_id} has {len(exit_events)} exit events. Cleaning up...")
        
        # Prioritization:
        # 1. Real bot-recorded exits (has order_id and NOT backfilled)
        # 2. Backfilled exits (has order_id and IS backfilled)
        # 3. Everything else (syncs, etc.)
        
        bot_exits = [e for e in exit_events if e.get("order_id") and "Backfilled" not in e.get("reason", "")]
        backfilled_exits = [e for e in exit_events if e.get("order_id") and "Backfilled" in e.get("reason", "")]
        
        best_exit = None
        if backfilled_exits:
            # Prefer backfilled exit as it comes directly from exchange history
            backfilled_exits.sort(key=lambda x: str(x.get("timestamp")), reverse=True)
            best_exit = backfilled_exits[0]
            logger.info(f"  -> Keeping BACKFILLED exit: {best_exit.get('order_id')}")
        elif bot_exits:
            # Fallback to bot recorded exit
            bot_exits.sort(key=lambda x: str(x.get("timestamp")), reverse=True)
            best_exit = bot_exits[0]
            logger.info(f"  -> Keeping BOT exit: {best_exit.get('order_id')}")
        else:
            # Keep the first sync if nothing else
            exit_events.sort(key=lambda x: str(x.get("timestamp")))
            best_exit = exit_events[0]
            logger.info(f"  -> Keeping placeholder exit: {best_exit.get('reason')}")
            
        # Reconstruct the events array
        new_events = entry_events + [best_exit]
        
        # Update root fields to match the best exit
        updates = {
            "events": new_events,
            "exit_action": best_exit.get("action"),
            "exit_side": best_exit.get("side"),
            "exit_price": best_exit.get("price"),
            "exit_execution_price": best_exit.get("price"),
            "exit_order_id": best_exit.get("order_id"),
            "pnl": best_exit.get("pnl"),
            "status": "CLOSED"
        }
        
        doc.reference.update(updates)
        count += 1

    logger.info(f"Successfully cleaned up {count} trades.")

if __name__ == "__main__":
    main()
