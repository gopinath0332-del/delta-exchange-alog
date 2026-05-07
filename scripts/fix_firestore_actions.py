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
    logger = get_logger("fix_actions_v2")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Syncing all trade actions based on entry_side...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        entry_side = data.get("entry_side")
        
        if not entry_side:
            continue
            
        # Determine the correct exit action name
        # If entry was BUY (long), all exits should be EXIT_LONG
        # If entry was SELL (short), all exits should be EXIT_SHORT
        correct_exit_action = "EXIT_LONG" if entry_side == "buy" else "EXIT_SHORT"
        
        needs_update = False
        updates = {}
        
        # Check root exit_action
        if data.get("exit_action") and data.get("exit_action").startswith("EXIT_") and data.get("exit_action") != correct_exit_action:
            logger.info(f"Trade {trade_id}: Root exit_action {data.get('exit_action')} -> {correct_exit_action}")
            updates["exit_action"] = correct_exit_action
            needs_update = True
            
        # Check events array
        events = data.get("events", [])
        for i, event in enumerate(events):
            action = event.get("action", "")
            if action.startswith("EXIT_") and action != correct_exit_action:
                logger.info(f"Trade {trade_id}: Event {i} action {action} -> {correct_exit_action}")
                event["action"] = correct_exit_action
                needs_update = True
                
        if needs_update:
            updates["events"] = events
            doc.reference.update(updates)
            count += 1

    logger.info(f"Successfully fixed actions for {count} trades.")

if __name__ == "__main__":
    main()
