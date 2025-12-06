"""Market data display components."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import dearpygui.dearpygui as dpg

from api.rest_client import DeltaRestClient
from core.logger import get_logger
from gui.components.base_component import BasePanel
from gui.components.theme import Colors

logger = get_logger(__name__)


class TickerPanel(BasePanel):
    """Panel displaying real-time ticker information."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 200,
    ):
        """
        Initialize ticker panel.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            width: Panel width
            height: Panel height
        """
        super().__init__("Market Ticker", tag, width, height)
        self.api_client = api_client
        self.current_symbol: Optional[str] = None
        self.ticker_data: Dict[str, Any] = {}

        # UI element tags
        self.symbol_text_tag = dpg.generate_uuid()
        self.price_text_tag = dpg.generate_uuid()
        self.change_text_tag = dpg.generate_uuid()
        self.volume_text_tag = dpg.generate_uuid()
        self.high_text_tag = dpg.generate_uuid()
        self.low_text_tag = dpg.generate_uuid()
        self.timestamp_text_tag = dpg.generate_uuid()

    def render_content(self):
        """Render ticker panel content."""
        with dpg.group(horizontal=True):
            dpg.add_text("Symbol:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.symbol_text_tag, color=Colors.TEXT_PRIMARY)

        dpg.add_spacer(height=5)

        # Price display (large)
        with dpg.group(horizontal=True):
            dpg.add_text("Price:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.price_text_tag, color=Colors.TEXT_PRIMARY)

        # 24h change
        with dpg.group(horizontal=True):
            dpg.add_text("24h Change:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.change_text_tag)

        dpg.add_spacer(height=5)

        # Volume, High, Low
        with dpg.group(horizontal=True):
            dpg.add_text("24h Volume:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.volume_text_tag, color=Colors.TEXT_PRIMARY)

        with dpg.group(horizontal=True):
            dpg.add_text("24h High:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.high_text_tag, color=Colors.PROFIT_GREEN)

        with dpg.group(horizontal=True):
            dpg.add_text("24h Low:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.low_text_tag, color=Colors.LOSS_RED)

        dpg.add_spacer(height=5)

        # Timestamp
        with dpg.group(horizontal=True):
            dpg.add_text("Updated:", color=Colors.TEXT_SECONDARY)
            dpg.add_text("--", tag=self.timestamp_text_tag, color=Colors.TEXT_SECONDARY)

    def update(self, symbol: str):
        """
        Update ticker with new symbol data.

        Args:
            symbol: Trading symbol
        """
        try:
            self.current_symbol = symbol
            ticker = self.api_client.get_ticker(symbol)
            self.ticker_data = ticker

            # Update UI
            if dpg.does_item_exist(self.symbol_text_tag):
                dpg.set_value(self.symbol_text_tag, symbol)

            # Extract price data
            price = ticker.get("close") or ticker.get("mark_price") or ticker.get("last_price", 0)
            if dpg.does_item_exist(self.price_text_tag):
                dpg.set_value(self.price_text_tag, f"${price:,.2f}" if price > 0 else "--")

            # Calculate 24h change if available
            if "close" in ticker and "open" in ticker and ticker["open"] > 0:
                change_pct = ((ticker["close"] - ticker["open"]) / ticker["open"]) * 100
                change_color = Colors.PROFIT_GREEN if change_pct >= 0 else Colors.LOSS_RED
                if dpg.does_item_exist(self.change_text_tag):
                    dpg.set_value(
                        self.change_text_tag, f"{change_pct:+.2f}%"
                    )
                    dpg.configure_item(self.change_text_tag, color=change_color)

            # Volume
            volume = ticker.get("volume", 0)
            if dpg.does_item_exist(self.volume_text_tag):
                dpg.set_value(self.volume_text_tag, f"{volume:,.2f}" if volume > 0 else "--")

            # High/Low
            high = ticker.get("high", 0)
            low = ticker.get("low", 0)
            if dpg.does_item_exist(self.high_text_tag):
                dpg.set_value(self.high_text_tag, f"${high:,.2f}" if high > 0 else "--")
            if dpg.does_item_exist(self.low_text_tag):
                dpg.set_value(self.low_text_tag, f"${low:,.2f}" if low > 0 else "--")

            # Timestamp
            if dpg.does_item_exist(self.timestamp_text_tag):
                dpg.set_value(self.timestamp_text_tag, datetime.now().strftime("%H:%M:%S"))

            logger.debug("Ticker updated", symbol=symbol, price=price)

        except Exception as e:
            logger.error("Failed to update ticker", symbol=symbol, error=str(e))


class OrderbookPanel(BasePanel):
    """Panel displaying orderbook (bids and asks)."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 400,
        depth: int = 10,
    ):
        """
        Initialize orderbook panel.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            width: Panel width
            height: Panel height
            depth: Number of price levels to show
        """
        super().__init__("Order Book", tag, width, height)
        self.api_client = api_client
        self.depth = depth
        self.current_product_id: Optional[int] = None

        # UI element tags
        self.asks_table_tag = dpg.generate_uuid()
        self.bids_table_tag = dpg.generate_uuid()

    def render_content(self):
        """Render orderbook panel content."""
        # Asks (sell orders) - shown in reverse order (lowest first)
        dpg.add_text("Asks (Sell Orders)", color=Colors.SELL_RED)
        dpg.add_separator()

        with dpg.table(
            tag=self.asks_table_tag,
            header_row=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
        ):
            dpg.add_table_column(label="Price")
            dpg.add_table_column(label="Size")
            dpg.add_table_column(label="Total")

        dpg.add_spacer(height=10)

        # Spread indicator
        dpg.add_text("--- Spread ---", color=Colors.TEXT_SECONDARY)

        dpg.add_spacer(height=10)

        # Bids (buy orders)
        dpg.add_text("Bids (Buy Orders)", color=Colors.BUY_GREEN)
        dpg.add_separator()

        with dpg.table(
            tag=self.bids_table_tag,
            header_row=True,
            borders_innerH=True,
            borders_outerH=True,
            borders_innerV=True,
            borders_outerV=True,
        ):
            dpg.add_table_column(label="Price")
            dpg.add_table_column(label="Size")
            dpg.add_table_column(label="Total")

    def update(self, product_id: int):
        """
        Update orderbook with new product data.

        Args:
            product_id: Product ID
        """
        try:
            self.current_product_id = product_id
            orderbook = self.api_client.get_l2_orderbook(product_id)

            # Clear existing rows
            self._clear_table(self.asks_table_tag)
            self._clear_table(self.bids_table_tag)

            # Update asks (reverse order - lowest price first)
            asks = orderbook.get("sell", [])[:self.depth]
            asks.reverse()  # Show lowest ask at bottom (closest to spread)

            for ask in asks:
                price = float(ask.get("price", 0))
                size = float(ask.get("size", 0))
                total = price * size

                with dpg.table_row(parent=self.asks_table_tag):
                    dpg.add_text(f"${price:,.2f}", color=Colors.SELL_RED)
                    dpg.add_text(f"{size:,.4f}")
                    dpg.add_text(f"${total:,.2f}")

            # Update bids
            bids = orderbook.get("buy", [])[:self.depth]

            for bid in bids:
                price = float(bid.get("price", 0))
                size = float(bid.get("size", 0))
                total = price * size

                with dpg.table_row(parent=self.bids_table_tag):
                    dpg.add_text(f"${price:,.2f}", color=Colors.BUY_GREEN)
                    dpg.add_text(f"{size:,.4f}")
                    dpg.add_text(f"${total:,.2f}")

            logger.debug("Orderbook updated", product_id=product_id)

        except Exception as e:
            logger.error("Failed to update orderbook", product_id=product_id, error=str(e))

    def _clear_table(self, table_tag: str):
        """Clear all rows from a table."""
        if dpg.does_item_exist(table_tag):
            children = dpg.get_item_children(table_tag, slot=1)
            if children:
                for child in children:
                    dpg.delete_item(child)


class ProductSelector(BasePanel):
    """Panel for selecting trading products."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        on_product_selected: callable,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 100,
    ):
        """
        Initialize product selector.

        Args:
            api_client: Delta REST API client
            on_product_selected: Callback when product is selected (receives product dict)
            tag: Optional unique tag
            width: Panel width
            height: Panel height
        """
        super().__init__("Select Product", tag, width, height)
        self.api_client = api_client
        self.on_product_selected = on_product_selected
        self.products: List[Dict[str, Any]] = []
        self.product_combo_tag = dpg.generate_uuid()

    def render_content(self):
        """Render product selector content."""
        dpg.add_text("Trading Pair:", color=Colors.TEXT_SECONDARY)

        dpg.add_combo(
            tag=self.product_combo_tag,
            items=[],
            default_value="Select a product...",
            callback=self._on_combo_changed,
            width=-1,
        )

        # Load products button
        dpg.add_button(
            label="Refresh Products",
            callback=self._load_products,
            width=-1,
        )

    def _load_products(self):
        """Load available products from API."""
        try:
            products = self.api_client.get_products()
            self.products = products

            # Filter for active products and create display names
            product_items = []
            for product in products:
                if product.get("state") == "live":
                    symbol = product.get("symbol", "")
                    product_id = product.get("id", "")
                    display_name = f"{symbol} (ID: {product_id})"
                    product_items.append(display_name)

            # Update combo box
            if dpg.does_item_exist(self.product_combo_tag):
                dpg.configure_item(self.product_combo_tag, items=product_items)

            logger.info("Products loaded", count=len(product_items))

        except Exception as e:
            logger.error("Failed to load products", error=str(e))

    def _on_combo_changed(self, sender, app_data):
        """Handle product selection change."""
        try:
            # Extract product ID from display name
            if "ID:" in app_data:
                product_id_str = app_data.split("ID: ")[1].rstrip(")")
                product_id = int(product_id_str)

                # Find the full product data
                product = next((p for p in self.products if p.get("id") == product_id), None)

                if product and self.on_product_selected:
                    self.on_product_selected(product)
                    logger.info("Product selected", product_id=product_id, symbol=product.get("symbol"))

        except Exception as e:
            logger.error("Failed to handle product selection", error=str(e))

    def update(self, data: Any):
        """Update product selector."""
        self._load_products()
