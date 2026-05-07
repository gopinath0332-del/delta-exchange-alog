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
    logger = get_logger("fix_milestones")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Retroactively standardizing MILESTONE_EXIT action names...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        events = data.get("events", [])
        entry_side = data.get("entry_side", "buy")
        standard_exit = "EXIT_LONG" if entry_side == "buy" else "EXIT_SHORT"
        
        needs_update = False
        
        # Fix events
        for event in events:
            if event.get("action") == "MILESTONE_EXIT":
                logger.info(f"Trade {trade_id}: Fixing event action MILESTONE_EXIT -> {standard_exit}")
                event["action"] = standard_exit
                needs_update = True
        
        # Fix root exit_action if it's MILESTONE_EXIT
        if data.get("exit_action") == "MILESTONE_EXIT":
            logger.info(f"Trade {trade_id}: Fixing root exit_action MILESTONE_EXIT -> {standard_exit}")
            data["exit_action"] = standard_exit
            needs_update = True
            
        if needs_update:
            doc.reference.update({
                "events": events,
                "exit_action": data.get("exit_action")
            })
            count += 1

    logger.info(f"Successfully standardized {count} trades.")

if __name__ == "__main__":
    main()
