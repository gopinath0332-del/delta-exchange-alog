"""
In-memory cache for passing order context from the trading bot to the WebSocket handler.
This allows the bot to place orders and the WebSocket to handle the actual notification
and journaling once filled, preserving strategy-specific data like reasons and RSI.
"""

from typing import Dict, Any
from threading import Lock

class OrderCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        
    def add(self, order_id: str, context: Dict[str, Any]) -> None:
        """Add context for a newly placed order."""
        if not order_id:
            return
        with self._lock:
            self._cache[order_id] = context
            
    def get(self, order_id: str) -> Dict[str, Any]:
        """Get context for an order."""
        with self._lock:
            return self._cache.get(order_id, {})
            
    def pop(self, order_id: str) -> Dict[str, Any]:
        """Get and remove context for an order."""
        with self._lock:
            return self._cache.pop(order_id, {})

# Global singleton instance
order_cache = OrderCache()
