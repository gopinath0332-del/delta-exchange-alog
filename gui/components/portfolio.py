"""Portfolio components for displaying positions, orders, and balance."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import dearpygui.dearpygui as dpg

from api.rest_client import DeltaRestClient
from core.logger import get_logger
from gui.components.base_component import BasePanel, BaseTable
from gui.components.theme import Colors

logger = get_logger(__name__)


class PositionsTable(BaseTable):
    """Table displaying open positions."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        on_close_position: Optional[Callable] = None,
    ):
        """
        Initialize positions table.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            on_close_position: Callback when position is closed
        """
        columns = ["Symbol", "Size", "Entry Price", "Current Price", "P&L", "Margin", "Action"]
        super().__init__(tag, columns)
        self.api_client = api_client
        self.on_close_position = on_close_position

    def render_cell(self, column: str, value: Any, row_data: Dict[str, Any]):
        """Render table cell with custom formatting."""
        if column == "P&L":
            # Color code P&L
            pnl = float(value) if value else 0
            color = Colors.PROFIT_GREEN if pnl >= 0 else Colors.LOSS_RED
            dpg.add_text(f"${pnl:,.2f}", color=color)

        elif column == "Entry Price" or column == "Current Price" or column == "Margin":
            # Format as currency
            val = float(value) if value else 0
            dpg.add_text(f"${val:,.2f}")

        elif column == "Action":
            # Add close button
            product_id = row_data.get("product_id")
            if product_id:
                dpg.add_button(
                    label="Close",
                    callback=lambda: self._close_position(product_id),
                    small=True,
                )

        else:
            dpg.add_text(str(value))

    def _close_position(self, product_id: int):
        """Close a position."""
        try:
            logger.info("Closing position", product_id=product_id)
            # TODO: Implement position closing logic
            if self.on_close_position:
                self.on_close_position(product_id)
        except Exception as e:
            logger.error("Failed to close position", product_id=product_id, error=str(e))

    def refresh(self):
        """Refresh positions from API."""
        try:
            positions = self.api_client.get_positions()

            # Transform API data to table format
            table_data = []
            for pos in positions:
                table_data.append({
                    "Symbol": pos.get("product", {}).get("symbol", "Unknown"),
                    "Size": pos.get("size", 0),
                    "Entry Price": pos.get("entry_price", 0),
                    "Current Price": pos.get("mark_price", 0),
                    "P&L": pos.get("unrealized_pnl", 0),
                    "Margin": pos.get("margin", 0),
                    "product_id": pos.get("product_id"),
                })

            self.update(table_data)
            logger.debug("Positions refreshed", count=len(table_data))

        except Exception as e:
            logger.error("Failed to refresh positions", error=str(e))


class OrdersTable(BaseTable):
    """Table displaying orders."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        on_cancel_order: Optional[Callable] = None,
    ):
        """
        Initialize orders table.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            on_cancel_order: Callback when order is cancelled
        """
        columns = ["Order ID", "Symbol", "Type", "Side", "Price", "Quantity", "Status", "Action"]
        super().__init__(tag, columns)
        self.api_client = api_client
        self.on_cancel_order = on_cancel_order

    def render_cell(self, column: str, value: Any, row_data: Dict[str, Any]):
        """Render table cell with custom formatting."""
        if column == "Side":
            # Color code buy/sell
            color = Colors.BUY_GREEN if value == "buy" else Colors.SELL_RED
            dpg.add_text(str(value).upper(), color=color)

        elif column == "Status":
            # Color code status
            status_colors = {
                "open": Colors.INFO,
                "filled": Colors.SUCCESS,
                "cancelled": Colors.TEXT_SECONDARY,
                "rejected": Colors.ERROR,
            }
            color = status_colors.get(str(value).lower(), Colors.TEXT_PRIMARY)
            dpg.add_text(str(value).upper(), color=color)

        elif column == "Price" or column == "Quantity":
            # Format numbers
            val = float(value) if value else 0
            if column == "Price":
                dpg.add_text(f"${val:,.2f}")
            else:
                dpg.add_text(f"{val:,.4f}")

        elif column == "Action":
            # Add cancel button for open orders
            status = row_data.get("Status", "").lower()
            if status == "open":
                order_id = row_data.get("order_id")
                product_id = row_data.get("product_id")
                if order_id and product_id:
                    dpg.add_button(
                        label="Cancel",
                        callback=lambda: self._cancel_order(product_id, order_id),
                        small=True,
                    )

        else:
            dpg.add_text(str(value))

    def _cancel_order(self, product_id: int, order_id: int):
        """Cancel an order."""
        try:
            self.api_client.cancel_order(product_id, order_id)
            logger.info("Order cancelled", product_id=product_id, order_id=order_id)

            if self.on_cancel_order:
                self.on_cancel_order(product_id, order_id)

            # Refresh table
            self.refresh()

        except Exception as e:
            logger.error("Failed to cancel order", product_id=product_id, order_id=order_id, error=str(e))

    def refresh(self):
        """Refresh orders from API."""
        try:
            orders = self.api_client.get_live_orders()

            # Transform API data to table format
            table_data = []
            for order in orders:
                table_data.append({
                    "Order ID": order.get("id", "Unknown"),
                    "Symbol": order.get("product", {}).get("symbol", "Unknown"),
                    "Type": order.get("order_type", "Unknown"),
                    "Side": order.get("side", "Unknown"),
                    "Price": order.get("limit_price", 0),
                    "Quantity": order.get("size", 0),
                    "Status": order.get("state", "Unknown"),
                    "order_id": order.get("id"),
                    "product_id": order.get("product_id"),
                })

            self.update(table_data)
            logger.debug("Orders refreshed", count=len(table_data))

        except Exception as e:
            logger.error("Failed to refresh orders", error=str(e))


class BalancePanel(BasePanel):
    """Panel displaying wallet balance information."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 200,
    ):
        """
        Initialize balance panel.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            width: Panel width
            height: Panel height
        """
        super().__init__("Wallet Balance", tag, width, height)
        self.api_client = api_client

        # UI element tags
        self.balance_text_tag = dpg.generate_uuid()
        self.available_text_tag = dpg.generate_uuid()
        self.locked_text_tag = dpg.generate_uuid()
        self.equity_text_tag = dpg.generate_uuid()
        self.margin_text_tag = dpg.generate_uuid()

    def render_content(self):
        """Render balance panel content."""
        # Total balance
        with dpg.group(horizontal=True):
            dpg.add_text("Total Balance:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.balance_text_tag, color=Colors.TEXT_PRIMARY)

        # Available balance
        with dpg.group(horizontal=True):
            dpg.add_text("Available:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.available_text_tag, color=Colors.PROFIT_GREEN)

        # Locked balance
        with dpg.group(horizontal=True):
            dpg.add_text("Locked (in positions):", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.locked_text_tag, color=Colors.WARNING)

        dpg.add_separator()

        # Equity
        with dpg.group(horizontal=True):
            dpg.add_text("Equity:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.equity_text_tag, color=Colors.TEXT_PRIMARY)

        # Margin used
        with dpg.group(horizontal=True):
            dpg.add_text("Margin Used:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.margin_text_tag, color=Colors.TEXT_PRIMARY)

    def refresh(self):
        """Refresh balance from API."""
        try:
            balance = self.api_client.get_wallet_balance()

            # Extract balance data
            total_balance = float(balance.get("balance", 0))
            available_balance = float(balance.get("available_balance", 0))
            locked_balance = total_balance - available_balance

            # Update UI
            if dpg.does_item_exist(self.balance_text_tag):
                dpg.set_value(self.balance_text_tag, f"${total_balance:,.2f}")

            if dpg.does_item_exist(self.available_text_tag):
                dpg.set_value(self.available_text_tag, f"${available_balance:,.2f}")

            if dpg.does_item_exist(self.locked_text_tag):
                dpg.set_value(self.locked_text_tag, f"${locked_balance:,.2f}")

            # Get positions for equity calculation
            positions = self.api_client.get_positions()
            total_unrealized_pnl = sum(float(p.get("unrealized_pnl", 0)) for p in positions)
            equity = total_balance + total_unrealized_pnl

            if dpg.does_item_exist(self.equity_text_tag):
                dpg.set_value(self.equity_text_tag, f"${equity:,.2f}")

            # Margin used
            total_margin = sum(float(p.get("margin", 0)) for p in positions)
            if dpg.does_item_exist(self.margin_text_tag):
                dpg.set_value(self.margin_text_tag, f"${total_margin:,.2f}")

            logger.debug("Balance refreshed", balance=total_balance, available=available_balance)

        except Exception as e:
            logger.error("Failed to refresh balance", error=str(e))

    def update(self, data: Any):
        """Update balance panel."""
        self.refresh()
