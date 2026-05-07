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
    logger = get_logger("deduplicate_exits")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Deduplicating exit events in Firestore...")
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
                logger.info(f"  -> Event {i}: action={action}, order_id={event.get('order_id')}, reason={event.get('reason')}")
                
        if len(exit_events) <= 1:
            continue
            
        # We have multiple exit events.
        # Logic: If one has an order_id and the other doesn't (and is a SYNC), remove the SYNC one.
        logger.info(f"Trade {trade_id} has {len(exit_events)} exit events. Analyzing...")
        
        real_exits = [e for e in exit_events if e[1].get("order_id")]
        sync_exits = [e for e in exit_events if not e[1].get("order_id") and "[SYNC]" in e[1].get("reason", "")]
        
        logger.info(f"  -> Real exits: {len(real_exits)}, Sync exits: {len(sync_exits)}")
        
        if real_exits and sync_exits:
            # We found a real exit and a sync exit. Remove the sync exit(s).
            indices_to_remove = [e[0] for e in sync_exits]
            
            # Remove from high index to low to avoid index shift issues
            new_events = [e for i, e in enumerate(events) if i not in indices_to_remove]
            
            logger.info(f"  -> Removing {len(indices_to_remove)} sync exit(s) from trade {trade_id}")
            
            doc.reference.update({
                "events": new_events
            })
            count += 1
        elif len(exit_events) > 1:
            # Maybe they are both real or both sync? 
            # If they have the same order_id, they are definitely duplicates.
            seen_order_ids = {}
            indices_to_remove = []
            for i, event in exit_events:
                oid = event.get("order_id")
                if oid:
                    if oid in seen_order_ids:
                        indices_to_remove.append(i)
                    else:
                        seen_order_ids[oid] = i
            
            if indices_to_remove:
                new_events = [e for i, e in enumerate(events) if i not in indices_to_remove]
                logger.info(f"  -> Removing {len(indices_to_remove)} duplicate order_id exits from trade {trade_id}")
                doc.reference.update({
                    "events": new_events
                })
                count += 1

    logger.info(f"Successfully deduplicated {count} trades.")

if __name__ == "__main__":
    main()
