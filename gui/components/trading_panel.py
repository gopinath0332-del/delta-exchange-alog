"""Trading panel for order placement and management."""

from typing import Any, Callable, Dict, Optional

import dearpygui.dearpygui as dpg

from api.rest_client import DeltaRestClient
from core.logger import get_logger
from data.models import OrderSide, OrderType
from gui.components.base_component import BasePanel
from gui.components.theme import BUY_BUTTON_THEME, SELL_BUTTON_THEME, Colors

logger = get_logger(__name__)


class TradingPanel(BasePanel):
    """Panel for placing and managing orders."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 500,
        on_order_placed: Optional[Callable] = None,
    ):
        """
        Initialize trading panel.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            width: Panel width
            height: Panel height
            on_order_placed: Callback when order is placed
        """
        super().__init__("Place Order", tag, width, height)
        self.api_client = api_client
        self.on_order_placed = on_order_placed
        self.current_product: Optional[Dict[str, Any]] = None

        # UI element tags
        self.product_text_tag = dpg.generate_uuid()
        self.order_type_combo_tag = dpg.generate_uuid()
        self.side_radio_tag = dpg.generate_uuid()
        self.quantity_input_tag = dpg.generate_uuid()
        self.price_input_tag = dpg.generate_uuid()
        self.leverage_input_tag = dpg.generate_uuid()
        self.total_value_text_tag = dpg.generate_uuid()
        self.margin_required_text_tag = dpg.generate_uuid()
        self.status_text_tag = dpg.generate_uuid()

    def render_content(self):
        """Render trading panel content."""
        # Product display
        with dpg.group(horizontal=True):
            dpg.add_text("Product:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("None selected", tag=self.product_text_tag, color=Colors.TEXT_PRIMARY)

        dpg.add_separator()
        dpg.add_spacer(height=5)

        # Order type selection
        dpg.add_text("Order Type:", color=Colors.TEXT_SECONDARY)
        dpg.add_combo(
            tag=self.order_type_combo_tag,
            items=["Market Order", "Limit Order"],
            default_value="Limit Order",
            callback=self._on_order_type_changed,
            width=-1,
        )

        dpg.add_spacer(height=10)

        # Side selection (Buy/Sell)
        dpg.add_text("Side:", color=Colors.TEXT_SECONDARY)
        dpg.add_radio_button(
            tag=self.side_radio_tag,
            items=["Buy", "Sell"],
            default_value="Buy",
            horizontal=True,
        )

        dpg.add_spacer(height=10)

        # Quantity input
        dpg.add_text("Quantity (contracts):", color=Colors.TEXT_SECONDARY)
        dpg.add_input_int(
            tag=self.quantity_input_tag,
            default_value=1,
            min_value=1,
            min_clamped=True,
            callback=self._calculate_totals,
            width=-1,
        )

        dpg.add_spacer(height=10)

        # Price input (for limit orders)
        dpg.add_text("Limit Price:", color=Colors.TEXT_SECONDARY)
        dpg.add_input_float(
            tag=self.price_input_tag,
            default_value=0.0,
            format="%.2f",
            callback=self._calculate_totals,
            width=-1,
        )

        dpg.add_spacer(height=10)

        # Leverage input
        dpg.add_text("Leverage:", color=Colors.TEXT_SECONDARY)
        dpg.add_input_int(
            tag=self.leverage_input_tag,
            default_value=1,
            min_value=1,
            max_value=100,
            min_clamped=True,
            max_clamped=True,
            callback=self._calculate_totals,
            width=-1,
        )

        dpg.add_separator()
        dpg.add_spacer(height=5)

        # Order summary
        dpg.add_text("Order Summary", color=Colors.ACCENT_PRIMARY)

        with dpg.group(horizontal=True):
            dpg.add_text("Total Value:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.total_value_text_tag, color=Colors.TEXT_PRIMARY)

        with dpg.group(horizontal=True):
            dpg.add_text("Margin Required:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("$0.00", tag=self.margin_required_text_tag, color=Colors.TEXT_PRIMARY)

        dpg.add_spacer(height=10)

        # Action buttons
        with dpg.group(horizontal=True):
            buy_btn = dpg.add_button(
                label="Buy",
                callback=lambda: self._place_order("buy"),
                width=150,
                height=40,
            )
            dpg.bind_item_theme(buy_btn, BUY_BUTTON_THEME)

            dpg.add_spacer(width=10)

            sell_btn = dpg.add_button(
                label="Sell",
                callback=lambda: self._place_order("sell"),
                width=150,
                height=40,
            )
            dpg.bind_item_theme(sell_btn, SELL_BUTTON_THEME)

        dpg.add_spacer(height=10)

        # Status message
        dpg.add_text("", tag=self.status_text_tag, wrap=400)

    def _on_order_type_changed(self, sender, app_data):
        """Handle order type change."""
        is_limit = app_data == "Limit Order"

        # Enable/disable price input based on order type
        if dpg.does_item_exist(self.price_input_tag):
            if is_limit:
                dpg.enable_item(self.price_input_tag)
            else:
                dpg.disable_item(self.price_input_tag)

    def _calculate_totals(self):
        """Calculate and display order totals."""
        try:
            if not self.current_product:
                return

            quantity = dpg.get_value(self.quantity_input_tag)
            price = dpg.get_value(self.price_input_tag)
            leverage = dpg.get_value(self.leverage_input_tag)

            if quantity <= 0 or price <= 0:
                return

            # Calculate total value
            contract_value = self.current_product.get("contract_value", 1)
            total_value = quantity * price * contract_value

            # Calculate margin required
            margin_required = total_value / leverage if leverage > 0 else total_value

            # Update UI
            if dpg.does_item_exist(self.total_value_text_tag):
                dpg.set_value(self.total_value_text_tag, f"${total_value:,.2f}")

            if dpg.does_item_exist(self.margin_required_text_tag):
                dpg.set_value(self.margin_required_text_tag, f"${margin_required:,.2f}")

        except Exception as e:
            logger.error("Failed to calculate totals", error=str(e))

    def _place_order(self, side: str):
        """
        Place an order.

        Args:
            side: Order side ('buy' or 'sell')
        """
        try:
            if not self.current_product:
                self._set_status("Please select a product first", Colors.ERROR)
                return

            product_id = self.current_product.get("id")
            quantity = dpg.get_value(self.quantity_input_tag)
            order_type_str = dpg.get_value(self.order_type_combo_tag)
            order_type = "market_order" if order_type_str == "Market Order" else "limit_order"

            # Validate inputs
            if quantity <= 0:
                self._set_status("Quantity must be greater than 0", Colors.ERROR)
                return

            # Get price for limit orders
            limit_price = None
            if order_type == "limit_order":
                price = dpg.get_value(self.price_input_tag)
                if price <= 0:
                    self._set_status("Price must be greater than 0 for limit orders", Colors.ERROR)
                    return
                limit_price = str(price)

            # Set leverage first
            leverage = dpg.get_value(self.leverage_input_tag)
            if leverage > 1:
                self.api_client.set_leverage(product_id, str(leverage))
                logger.info("Leverage set", product_id=product_id, leverage=leverage)

            # Place order
            self._set_status("Placing order...", Colors.INFO)

            order_response = self.api_client.place_order(
                product_id=product_id,
                size=quantity,
                side=side,
                order_type=order_type,
                limit_price=limit_price,
            )

            # Success
            order_id = order_response.get("id", "Unknown")
            self._set_status(
                f"Order placed successfully! Order ID: {order_id}",
                Colors.SUCCESS,
            )

            logger.info(
                "Order placed",
                product_id=product_id,
                side=side,
                quantity=quantity,
                order_type=order_type,
                order_id=order_id,
            )

            # Call callback
            if self.on_order_placed:
                self.on_order_placed(order_response)

        except Exception as e:
            error_msg = f"Failed to place order: {str(e)}"
            self._set_status(error_msg, Colors.ERROR)
            logger.error("Order placement failed", error=str(e))

    def _set_status(self, message: str, color: tuple):
        """Set status message."""
        if dpg.does_item_exist(self.status_text_tag):
            dpg.set_value(self.status_text_tag, message)
            dpg.configure_item(self.status_text_tag, color=color)

    def update(self, product: Dict[str, Any]):
        """
        Update trading panel with selected product.

        Args:
            product: Product data dictionary
        """
        self.current_product = product

        # Update product display
        symbol = product.get("symbol", "Unknown")
        product_id = product.get("id", "")

        if dpg.does_item_exist(self.product_text_tag):
            dpg.set_value(self.product_text_tag, f"{symbol} (ID: {product_id})")

        # Reset status
        self._set_status("", Colors.TEXT_PRIMARY)

        # Recalculate totals
        self._calculate_totals()

        logger.info("Trading panel updated", symbol=symbol, product_id=product_id)
