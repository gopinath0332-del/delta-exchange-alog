"""
WebSocket Event Handler for Delta Exchange.
Processes real-time order and position updates.
"""

from typing import Dict, Any, Optional
from datetime import datetime

from core.logger import get_logger
from core.firestore_client import get_open_trade_by_symbol, get_trade_by_entry_order_id, journal_trade
from notifications.manager import NotificationManager
from core.order_cache import order_cache

logger = get_logger(__name__)


class WebSocketEventHandler:
    """Handles incoming WebSocket events for orders and positions."""
    
    def __init__(self, notifier: NotificationManager):
        self.notifier = notifier
        # Keep track of recently processed order IDs to avoid duplicate processing
        self.processed_orders = set()

    def handle_order_event(self, data: Dict[str, Any]) -> None:
        """
        Process an 'orders' channel event.
        
        Args:
            data: The JSON payload from the WebSocket
        """
        logger.info(f"Handling order event: {data.get('type')}")
        # Delta Exchange payload usually nests the actual data
        payload = data.get("payload", {})
        if not payload:
            return
            
        # The payload might contain a single order or a list
        # Let's handle both
        orders = []
        if isinstance(payload, list):
            orders = payload
        elif isinstance(payload, dict):
            # Sometimes events are nested under 'data' or just flat
            if "data" in payload and isinstance(payload["data"], list):
                orders = payload["data"]
            elif "id" in payload:
                orders = [payload]
                
        for order in orders:
            self._process_single_order(order)

    def _process_single_order(self, order: Dict[str, Any]) -> None:
        """Process a single order object."""
        order_id = str(order.get("id", ""))
        state = order.get("state", "").lower()
        
        if not order_id or not state:
            return
            
        # We only care about filled (closed) orders
        if state not in ["closed", "filled", "cancelled"]:
            return
            
        # Avoid duplicate processing if we get multiple updates
        if order_id in self.processed_orders:
            return
            
        symbol = order.get("product_symbol", "")
        side = order.get("side", "")
        order_type = order.get("order_type", "")
        filled_size = float(order.get("size", 0)) - float(order.get("unfilled_size", order.get("size", 0)))
        avg_fill_price = float(order.get("avg_fill_price", order.get("limit_price", 0)))
        
        if filled_size <= 0 and state != "cancelled":
            return
            
        logger.info(f"WebSocket Order Update: {symbol} {side} {filled_size} @ {avg_fill_price} (State: {state}, Type: {order_type})")
        
        # If cancelled, just log and ignore
        if state == "cancelled":
            self.processed_orders.add(order_id)
            return

        # At this point, the order is filled.
        self.processed_orders.add(order_id)
        
        # 1. Check if this is a BOT INITIATED order from our cache
        bot_context = order_cache.pop(order_id)
        
        if bot_context:
            logger.info(f"Order {order_id} identified from cache: {bot_context['action']} - {bot_context['reason']}")
            
            # Send Notification with full bot context
            self.notifier.send_trade_alert(
                symbol=symbol,
                side=bot_context['action'],
                price=avg_fill_price,
                size=filled_size,
                reason=bot_context['reason'],
                strategy_name=bot_context.get('strategy_name'),
                rsi=bot_context.get('rsi'),
                mode=bot_context.get('mode', 'live'),
                market_price=avg_fill_price,
            )
            
            # Update Journal with exact fill price
            journal_trade(
                symbol=symbol,
                action=bot_context['action'],
                side=side,
                price=avg_fill_price,
                execution_price=avg_fill_price,
                order_size=int(filled_size),
                leverage=0,
                mode=bot_context.get('mode', 'live'),
                trade_id=bot_context.get('trade_id'),
                is_entry=bot_context.get('is_entry', False),
                order_id=order_id
            )
            return

        # 2. If NOT in cache, it's an EXCHANGE INITIATED order (e.g. Stop Loss)
        logger.info(f"Order {order_id} NOT in cache. Identified as EXCHANGE INITIATED.")
        
        # Determine if this was an ENTRY or EXIT based on our Firestore state
        trade_id = get_open_trade_by_symbol(symbol)
        
        if not trade_id:
            logger.warning(f"Filled order {order_id} ({symbol}) cannot be matched to any Firestore trade. Ignoring.")
            return
            
        # Exchange-initiated exits are almost always Stop-Losses or Take-Profits hitting
        logger.info(f"Order {order_id} identified as EXCHANGE EXIT for open trade {trade_id}")
        
        # Infer the action
        action_name = "STOP_LOSS" if order_type in ["stop_market", "stop_limit", "bracket_stop"] else "EXCHANGE_EXIT"
        action = f"EXIT_{action_name}"
        
        # Send Notification
        self.notifier.send_trade_alert(
            symbol=symbol,
            side=action,
            price=avg_fill_price,
            size=filled_size,
            reason=f"Exchange Triggered (Type: {order_type})"
        )
        
        # Update Journal
        journal_trade(
            symbol=symbol,
            action=action,
            side=side,
            price=avg_fill_price,
            execution_price=avg_fill_price,
            order_size=int(filled_size),
            leverage=0,
            mode="live",
            trade_id=trade_id,
            is_entry=False,
            order_id=order_id
        )

    def handle_position_event(self, data: Dict[str, Any]) -> None:
        """
        Process a 'positions' channel event.
        
        Args:
            data: The JSON payload from the WebSocket
        """
        # For now, we mainly rely on 'orders' for fills.
        # We can use positions to verify sync state later.
        pass
