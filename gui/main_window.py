"""Main GUI window for the Delta Exchange trading platform - Fixed version using working patterns."""

import threading
import time
from typing import Any, Dict, Optional

import dearpygui.dearpygui as dpg

from api.rest_client import DeltaRestClient
from core.config import Config
from core.logger import get_logger

logger = get_logger(__name__)


class TradingGUI:
    """Main GUI application for Delta Exchange trading."""

    def __init__(self, config: Config):
        """
        Initialize trading GUI.

        Args:
            config: Configuration instance
        """
        self.config = config
        self.api_client = DeltaRestClient(config)
        self.running = False
        self.update_thread: Optional[threading.Thread] = None
        self.selected_product: Optional[Dict[str, Any]] = None

        logger.info("Trading GUI initialized", environment=config.environment)

    def start(self):
        """Start the GUI application."""
        try:
            # Create DearPyGui context
            dpg.create_context()

            # Set global font scale for better readability
            dpg.set_global_font_scale(1.5)

            # Setup UI
            self.setup_ui()

            # Create viewport
            dpg.create_viewport(
                title=f"Delta Exchange Trading Platform - {self.config.environment.upper()}",
                width=1400,
                height=900,
            )

            # Setup and show viewport
            dpg.setup_dearpygui()
            dpg.show_viewport()

            # Start update thread
            self.running = True
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()

            logger.info("GUI started successfully")

            # Main render loop
            while dpg.is_dearpygui_running():
                dpg.render_dearpygui_frame()

        except Exception as e:
            logger.exception("GUI error", error=str(e))
            print(f"\nError: {e}")
            print("\nIf GUI fails, use terminal mode:")
            print("  python3 main.py fetch-data --symbol BTCUSD")
            raise

        finally:
            self.stop()

    def stop(self):
        """Stop the GUI application."""
        self.running = False

        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=2)

        dpg.destroy_context()
        logger.info("GUI stopped")

    def setup_ui(self):
        """Setup the main UI - using working patterns from reference project."""
        # Main window - using with context manager WITHOUT tag
        with dpg.window(label="Delta Exchange Trading", width=1400, height=900, pos=(50, 50)):
            # Status bar
            with dpg.group(horizontal=True):
                dpg.add_text("Status:", color=(160, 160, 160))
                dpg.add_text("Connected", tag="status_text", color=(46, 204, 113))
                dpg.add_spacer(width=20)
                dpg.add_text("Environment:", color=(160, 160, 160))
                env_color = (241, 196, 15) if self.config.is_testnet() else (231, 76, 60)
                dpg.add_text(self.config.environment.upper(), tag="env_text", color=env_color)

            dpg.add_separator()

            # Main tabs
            with dpg.tab_bar():
                # Dashboard Tab
                with dpg.tab(label="Dashboard"):
                    with dpg.child_window(height=-1):
                        self.create_dashboard_tab()

                # Trading Tab
                with dpg.tab(label="Trading"):
                    with dpg.child_window(height=-1):
                        self.create_trading_tab()

                # Positions Tab
                with dpg.tab(label="Positions"):
                    with dpg.child_window(height=-1):
                        self.create_positions_tab()

                # Orders Tab
                with dpg.tab(label="Orders"):
                    with dpg.child_window(height=-1):
                        self.create_orders_tab()

                # Charts Tab
                with dpg.tab(label="Charts"):
                    with dpg.child_window(height=-1):
                        self.create_charts_tab()

    def create_dashboard_tab(self):
        """Create dashboard tab."""
        dpg.add_text("Delta Exchange Trading Platform", color=(100, 200, 255))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            # Left column - Quick stats
            with dpg.child_window(width=400, height=-1):
                dpg.add_text("Account Summary", color=(100, 200, 255))
                dpg.add_separator()
                dpg.add_spacer(height=10)

                dpg.add_text("Balance:", color=(160, 160, 160))
                dpg.add_text("$0.00", tag="balance_text")
                dpg.add_spacer(height=5)

                dpg.add_text("Available:", color=(160, 160, 160))
                dpg.add_text("$0.00", tag="available_text", color=(46, 204, 113))
                dpg.add_spacer(height=5)

                dpg.add_text("In Positions:", color=(160, 160, 160))
                dpg.add_text("$0.00", tag="locked_text", color=(241, 196, 15))

                dpg.add_spacer(height=20)
                dpg.add_button(label="Refresh Balance", callback=self.refresh_balance)

            # Right column - Welcome message
            with dpg.child_window(width=-1, height=-1):
                dpg.add_text("Welcome!", color=(100, 200, 255))
                dpg.add_separator()
                dpg.add_spacer(height=10)

                dpg.add_text("• Use the Trading tab to select products and place orders")
                dpg.add_text("• Monitor your positions in the Positions tab")
                dpg.add_text("• View and manage orders in the Orders tab")
                dpg.add_text("• Analyze price charts in the Charts tab")

                dpg.add_spacer(height=20)
                dpg.add_separator()
                dpg.add_spacer(height=10)

                if self.config.is_testnet():
                    dpg.add_text("⚠ TESTNET MODE - No real funds at risk", color=(241, 196, 15))
                else:
                    dpg.add_text("⚠ PRODUCTION MODE - Real funds at risk!", color=(231, 76, 60))

    def create_trading_tab(self):
        """Create trading tab."""
        dpg.add_text("Trading", color=(100, 200, 255))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            # Left column - Market data
            with dpg.child_window(width=400, height=-1):
                dpg.add_text("Market Data", color=(100, 200, 255))
                dpg.add_separator()
                dpg.add_spacer(height=10)

                dpg.add_text("Product:")
                dpg.add_combo([], tag="product_combo", width=-1, callback=self.on_product_selected)
                dpg.add_button(label="Load Products", callback=self.load_products, width=-1)

                dpg.add_spacer(height=20)
                dpg.add_text("Ticker", color=(100, 200, 255))
                dpg.add_separator()

                dpg.add_text("Symbol: --", tag="ticker_symbol")
                dpg.add_text("Price: $--", tag="ticker_price")
                dpg.add_text("24h Change: --", tag="ticker_change")

            # Right column - Order placement
            with dpg.child_window(width=-1, height=-1):
                dpg.add_text("Place Order", color=(100, 200, 255))
                dpg.add_separator()
                dpg.add_spacer(height=10)

                dpg.add_text("Order Type:")
                dpg.add_combo(["Market Order", "Limit Order"], default_value="Limit Order", tag="order_type", width=-1)

                dpg.add_spacer(height=10)
                dpg.add_text("Side:")
                dpg.add_radio_button(["Buy", "Sell"], tag="order_side", horizontal=True)

                dpg.add_spacer(height=10)
                dpg.add_text("Quantity:")
                dpg.add_input_int(tag="order_quantity", default_value=1, min_value=1, min_clamped=True, width=-1)

                dpg.add_spacer(height=10)
                dpg.add_text("Price:")
                dpg.add_input_float(tag="order_price", default_value=0.0, format="%.2f", width=-1)

                dpg.add_spacer(height=20)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="Buy", callback=lambda: self.place_order("buy"), width=150, height=40)
                    dpg.add_spacer(width=10)
                    dpg.add_button(label="Sell", callback=lambda: self.place_order("sell"), width=150, height=40)

                dpg.add_spacer(height=10)
                dpg.add_text("", tag="order_status", wrap=400)

    def create_positions_tab(self):
        """Create positions tab."""
        dpg.add_text("Open Positions", color=(100, 200, 255))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        dpg.add_button(label="Refresh Positions", callback=self.refresh_positions)
        dpg.add_spacer(height=10)

        with dpg.table(tag="positions_table", header_row=True, resizable=True,
                      borders_innerH=True, borders_innerV=True,
                      borders_outerH=True, borders_outerV=True):
            dpg.add_table_column(label="Symbol")
            dpg.add_table_column(label="Size")
            dpg.add_table_column(label="Entry Price")
            dpg.add_table_column(label="Current Price")
            dpg.add_table_column(label="P&L")
            dpg.add_table_column(label="Margin")

    def create_orders_tab(self):
        """Create orders tab."""
        dpg.add_text("Live Orders", color=(100, 200, 255))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        dpg.add_button(label="Refresh Orders", callback=self.refresh_orders)
        dpg.add_spacer(height=10)

        with dpg.table(tag="orders_table", header_row=True, resizable=True,
                      borders_innerH=True, borders_innerV=True,
                      borders_outerH=True, borders_outerV=True):
            dpg.add_table_column(label="Order ID")
            dpg.add_table_column(label="Symbol")
            dpg.add_table_column(label="Type")
            dpg.add_table_column(label="Side")
            dpg.add_table_column(label="Price")
            dpg.add_table_column(label="Quantity")
            dpg.add_table_column(label="Status")

    def create_charts_tab(self):
        """Create charts tab."""
        dpg.add_text("Price Charts", color=(100, 200, 255))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        dpg.add_text("Charts feature coming soon...")
        dpg.add_text("Use terminal mode for data analysis:")
        dpg.add_text("  python3 main.py fetch-data --symbol BTCUSD --timeframe 1h")

    # Callback methods
    def load_products(self):
        """Load available products."""
        try:
            products = self.api_client.get_products()
            product_items = []
            for product in products:
                if product.get("state") == "live":
                    symbol = product.get("symbol", "")
                    product_id = product.get("id", "")
                    product_items.append(f"{symbol} (ID: {product_id})")

            if dpg.does_item_exist("product_combo"):
                dpg.configure_item("product_combo", items=product_items)

            logger.info("Products loaded", count=len(product_items))
        except Exception as e:
            logger.error("Failed to load products", error=str(e))

    def on_product_selected(self, sender, app_data):
        """Handle product selection."""
        try:
            if "ID:" in app_data:
                product_id_str = app_data.split("ID: ")[1].rstrip(")")
                symbol = app_data.split(" (ID:")[0]

                if dpg.does_item_exist("ticker_symbol"):
                    dpg.set_value("ticker_symbol", f"Symbol: {symbol}")

                logger.info("Product selected", symbol=symbol)
        except Exception as e:
            logger.error("Failed to handle product selection", error=str(e))

    def place_order(self, side: str):
        """Place an order."""
        try:
            if dpg.does_item_exist("order_status"):
                dpg.set_value("order_status", f"Order placement not yet implemented for {side}")
            logger.info("Order placement requested", side=side)
        except Exception as e:
            logger.error("Failed to place order", error=str(e))

    def refresh_balance(self):
        """Refresh account balance."""
        try:
            # Get wallet balance - API returns dict with balance info
            response = self.api_client.client.get_wallet_balances()
            
            # Handle response - it's a list of balances per asset
            if isinstance(response, list) and len(response) > 0:
                # Get USDT balance (most common)
                balance_data = response[0]  # First asset
                total = float(balance_data.get("balance", 0))
                available = float(balance_data.get("available_balance", 0))
                locked = total - available
            else:
                total = available = locked = 0.0

            if dpg.does_item_exist("balance_text"):
                dpg.set_value("balance_text", f"${total:,.2f}")
            if dpg.does_item_exist("available_text"):
                dpg.set_value("available_text", f"${available:,.2f}")
            if dpg.does_item_exist("locked_text"):
                dpg.set_value("locked_text", f"${locked:,.2f}")

            logger.info("Balance refreshed", balance=total)
        except Exception as e:
            logger.error("Failed to refresh balance", error=str(e))
            # Set default values on error
            if dpg.does_item_exist("balance_text"):
                dpg.set_value("balance_text", "Error loading")


    def refresh_positions(self):
        """Refresh positions table."""
        try:
            positions = self.api_client.get_positions()
            # Clear existing rows
            if dpg.does_item_exist("positions_table"):
                children = dpg.get_item_children("positions_table", slot=1)
                if children:
                    for child in children:
                        dpg.delete_item(child)

                # Add new rows
                for pos in positions:
                    with dpg.table_row(parent="positions_table"):
                        dpg.add_text(pos.get("product", {}).get("symbol", "Unknown"))
                        dpg.add_text(str(pos.get("size", 0)))
                        dpg.add_text(f"${pos.get('entry_price', 0):,.2f}")
                        dpg.add_text(f"${pos.get('mark_price', 0):,.2f}")
                        pnl = pos.get("unrealized_pnl", 0)
                        pnl_color = (46, 204, 113) if pnl >= 0 else (231, 76, 60)
                        dpg.add_text(f"${pnl:,.2f}", color=pnl_color)
                        dpg.add_text(f"${pos.get('margin', 0):,.2f}")

            logger.info("Positions refreshed", count=len(positions))
        except Exception as e:
            logger.error("Failed to refresh positions", error=str(e))

    def refresh_orders(self):
        """Refresh orders table."""
        try:
            orders = self.api_client.get_live_orders()
            # Clear existing rows
            if dpg.does_item_exist("orders_table"):
                children = dpg.get_item_children("orders_table", slot=1)
                if children:
                    for child in children:
                        dpg.delete_item(child)

                # Add new rows
                for order in orders:
                    with dpg.table_row(parent="orders_table"):
                        dpg.add_text(str(order.get("id", "Unknown")))
                        dpg.add_text(order.get("product", {}).get("symbol", "Unknown"))
                        dpg.add_text(order.get("order_type", "Unknown"))
                        side = order.get("side", "Unknown")
                        side_color = (46, 204, 113) if side == "buy" else (231, 76, 60)
                        dpg.add_text(side.upper(), color=side_color)
                        dpg.add_text(f"${order.get('limit_price', 0):,.2f}")
                        dpg.add_text(str(order.get("size", 0)))
                        dpg.add_text(order.get("state", "Unknown").upper())

            logger.info("Orders refreshed", count=len(orders))
        except Exception as e:
            logger.error("Failed to refresh orders", error=str(e))

    def _update_loop(self):
        """Background update loop for real-time data."""
        update_interval = self.config.gui.update_interval / 1000

        while self.running:
            try:
                time.sleep(update_interval)
            except Exception as e:
                logger.error("Update loop error", error=str(e))
                time.sleep(update_interval * 2)


def run_gui(config: Config):
    """
    Run the GUI application.

    Args:
        config: Configuration instance
    """
    gui = TradingGUI(config)
    gui.start()
