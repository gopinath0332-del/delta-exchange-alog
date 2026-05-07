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
    logger = get_logger("revert_milestones")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Reverting MILESTONE_EXIT action names...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        events = data.get("events", [])
        
        needs_update = False
        
        # Revert events
        for event in events:
            reason = str(event.get("reason", ""))
            if "Milestone" in reason and event.get("action") in ["EXIT_LONG", "EXIT_SHORT"]:
                logger.info(f"Trade {trade_id}: Reverting event action -> MILESTONE_EXIT")
                event["action"] = "MILESTONE_EXIT"
                needs_update = True
        
        # Revert root exit_action if reason matches
        reason = str(data.get("exit_reason", ""))
        if "Milestone" in reason and data.get("exit_action") in ["EXIT_LONG", "EXIT_SHORT"]:
            logger.info(f"Trade {trade_id}: Reverting root exit_action -> MILESTONE_EXIT")
            data["exit_action"] = "MILESTONE_EXIT"
            needs_update = True
            
        if needs_update:
            doc.reference.update({
                "events": events,
                "exit_action": data.get("exit_action")
            })
            count += 1

    logger.info(f"Successfully reverted {count} trades.")

if __name__ == "__main__":
    main()
