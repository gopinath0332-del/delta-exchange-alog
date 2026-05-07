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
    logger = get_logger("smart_cleanup")

    if not fs_client._firestore_client:
        logger.error("Firestore client is not initialized.")
        return

    logger.info("Performing SMART deduplication (supporting milestones) in Firestore...")
    trades_ref = fs_client._firestore_client.collection(fs_client._firestore_collection)
    
    docs = trades_ref.stream()

    count = 0
    for doc in docs:
        data = doc.to_dict()
        trade_id = doc.id
        events = data.get("events", [])
        
        # Split events
        entry_events = [e for e in events if e.get("action", "").startswith("ENTRY_")]
        exit_candidate_events = [e for e in events if e.get("action", "").startswith("EXIT_") or "MILESTONE" in e.get("action", "")]
        
        if len(exit_candidate_events) <= 1:
            # Check if we should remove a SYNC event if it's the only one and reason matches?
            # No, keep it if it's the only one.
            continue
            
        logger.info(f"Trade {trade_id} has {len(exit_candidate_events)} exit-related events. Filtering...")
        
        # Deduplication logic by Order ID
        seen_order_ids = {}
        unique_exits = []
        
        # Sort by priority: Backfilled > Bot Recorded > Sync
        def get_priority(e):
            if e.get("order_id"):
                if "Backfilled" in e.get("reason", ""): return 3
                return 2
            return 1
            
        # Group by order_id (if exists) or reason
        for e in exit_candidate_events:
            oid = str(e.get("order_id", "None"))
            if oid != "None":
                if oid not in seen_order_ids or get_priority(e) > get_priority(seen_order_ids[oid]):
                    seen_order_ids[oid] = e
            else:
                # Handle events without order_id (Sync placeholders)
                # Keep them only if no other event exists for that "slot"
                # For now, we'll just put them in a special bucket
                unique_exits.append(e)
                
        # Combine unique order events
        final_unique_exits = list(seen_order_ids.values())
        
        # If we have real orders, remove any [SYNC] placeholders
        if any([e.get("order_id") for e in final_unique_exits]):
            final_unique_exits = [e for e in final_unique_exits if "[SYNC]" not in e.get("reason", "")]
            # Also filter the non-order-id ones
            unique_exits = [e for e in unique_exits if "[SYNC]" not in e.get("reason", "")]

        final_unique_exits.extend(unique_exits)
        
        # Sort chronologically
        final_unique_exits.sort(key=lambda x: str(x.get("timestamp")))
        
        if len(final_unique_exits) == len(exit_candidate_events):
            continue
            
        logger.info(f"  -> Reduced {len(exit_candidate_events)} events to {len(final_unique_exits)}")
        
        # Reconstruct events array
        new_events = entry_events + final_unique_exits
        
        # Update root fields based on the LAST event
        best_last_exit = final_unique_exits[-1]
        updates = {
            "events": new_events,
            "exit_action": best_last_exit.get("action"),
            "exit_side": best_last_exit.get("side"),
            "exit_price": best_last_exit.get("price"),
            "exit_execution_price": best_last_exit.get("price"),
            "exit_order_id": best_last_exit.get("order_id"),
            "pnl": best_last_exit.get("pnl"),
            "exit_timestamp": best_last_exit.get("timestamp")
        }
        
        # Determine status
        # If total exited size >= entry size, it's CLOSED
        entry_size = data.get("order_size", 0)
        total_exited = sum([float(e.get("order_size", 0)) for e in final_unique_exits])
        if total_exited >= (entry_size * 0.98):
            updates["status"] = "CLOSED"
        else:
            updates["status"] = "PARTIAL_CLOSED"
            
        doc.reference.update(updates)
        count += 1

    logger.info(f"Successfully cleaned up {count} trades.")

if __name__ == "__main__":
    main()
