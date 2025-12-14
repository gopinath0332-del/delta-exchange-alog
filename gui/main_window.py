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
            with dpg.tab_bar(callback=self.on_tab_change, tag="main_tab_bar"):
                # Dashboard Tab
                with dpg.tab(label="Dashboard", tag="tab_dashboard"):
                    with dpg.child_window(height=-1):
                        self.create_dashboard_tab()

                # Trading Tab
                with dpg.tab(label="Trading", tag="tab_trading"):
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
        """Create trading tab with futures product table."""
        dpg.add_text("Trading", color=(100, 200, 255))
        dpg.add_separator()
        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            # Left column - Futures product table
            with dpg.child_window(width=-1, height=-1):
                dpg.add_text("Futures", color=(100, 200, 255))
                dpg.add_separator()
                dpg.add_spacer(height=10)

                # Search box
                with dpg.group(horizontal=True):
                    dpg.add_input_text(
                        tag="futures_search",
                        hint="Search contracts...",
                        callback=self.search_futures,
                        width=300
                    )

                dpg.add_spacer(height=10)

                # Futures table
                with dpg.table(
                    tag="futures_table",
                    header_row=True,
                    resizable=True,
                    borders_innerH=True,
                    borders_innerV=True,
                    borders_outerH=True,
                    borders_outerV=True,
                    scrollY=True,
                    height=500,
                    row_background=True,
                    policy=dpg.mvTable_SizingStretchProp
                ):
                    dpg.add_table_column(label="Contract", width_fixed=True, init_width_or_weight=100)
                    dpg.add_table_column(label="Description", width_stretch=True, init_width_or_weight=150)
                    dpg.add_table_column(label="Last Price", width_fixed=True, init_width_or_weight=100)
                    dpg.add_table_column(label="24h Change", width_fixed=True, init_width_or_weight=100)
                    dpg.add_table_column(label="24h Volume", width_fixed=True, init_width_or_weight=100)
                    dpg.add_table_column(label="Open Interest", width_fixed=True, init_width_or_weight=100)
                    dpg.add_table_column(label="24h High/Low", width_fixed=True, init_width_or_weight=120)
                    dpg.add_table_column(label="Funding", width_fixed=True, init_width_or_weight=80)

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
    def on_tab_change(self, sender, app_data, user_data):
        """Handle tab change events."""
        logger.info(f"Tab changed: sender={sender}, app_data={app_data}, user_data={user_data}")
        
        # Determine selected tab tag
        selected_tab = app_data
        
        # If app_data is an int (internal ID), try to get the tag/alias
        if isinstance(app_data, int):
            alias = dpg.get_item_alias(app_data)
            if alias:
                selected_tab = alias
                logger.info(f"Resolved tab ID {app_data} to alias {alias}")
            else:
                # Fallback: check label
                label = dpg.get_item_label(app_data)
                logger.info(f"Tab ID {app_data} has label: {label}")
                if label == "Trading":
                    selected_tab = "tab_trading"
        
        # Detect if Trading tab is selected
        if selected_tab == "tab_trading":
            logger.info("Trading tab selected - triggering load_futures_products")
            # Use threading to prevent UI freeze
            import threading
            threading.Thread(target=self.load_futures_products, daemon=True).start()

    def load_futures_products(self):
        """Load futures products and populate table."""
        try:
            logger.info("Starting to load futures products")
            
            # Get symbols from configuration
            target_symbols = self.config.gui.futures_symbols
            logger.info(f"Loading futures for symbols: {target_symbols}")
            
            # Show loading status (must be on main thread)
            # DPG is generally thread-safe for item deletion/creation but let's be careful
            # For now we'll do it directly as DPG handles its own locking usually
            if dpg.does_item_exist("futures_table"):
                children = dpg.get_item_children("futures_table", slot=1)
                if children:
                    for child in children:
                        dpg.delete_item(child)
                
                # Add loading message
                with dpg.table_row(parent="futures_table"):
                    dpg.add_text("Loading...")
                    dpg.add_text("Fetching data...")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
            
            # Fetch all futures products
            logger.info("Fetching futures products from API")
            all_products = self.api_client.get_futures_products()
            logger.info(f"Fetched {len(all_products)} total futures products")
            
            # Filter for specific symbols only
            products = [p for p in all_products if p.get("symbol") in target_symbols]
            logger.info(f"Filtered to {len(products)} target products: {target_symbols}")
            
            if not products:
                logger.warning("No matching futures products found")
                # Clear table and show message
                if dpg.does_item_exist("futures_table"):
                    children = dpg.get_item_children("futures_table", slot=1)
                    if children:
                        for child in children:
                            dpg.delete_item(child)
                    with dpg.table_row(parent="futures_table"):
                        dpg.add_text("No Data")
                        dpg.add_text(f"No futures found for: {', '.join(target_symbols)}")
                        dpg.add_text("")
                        dpg.add_text("")
                        dpg.add_text("")
                        dpg.add_text("")
                        dpg.add_text("")
                        dpg.add_text("")
                return
            
            # Store products for filtering
            self.futures_products = products
            self.current_filter = "ALL"
            
            # Get ticker data for the filtered products
            logger.info("Fetching ticker data for products")
            symbols = [p.get("symbol", "") for p in products]
            self.futures_tickers = self.api_client.get_tickers_batch(symbols)
            logger.info(f"Fetched {len(self.futures_tickers)} tickers")
            
            # Update table
            logger.info("Updating futures table")
            self.update_futures_table()
            
            logger.info("Futures products loaded successfully", count=len(products))
        except Exception as e:
            logger.exception("Failed to load futures products", error=str(e))
            # Show error in table
            if dpg.does_item_exist("futures_table"):
                children = dpg.get_item_children("futures_table", slot=1)
                if children:
                    for child in children:
                        dpg.delete_item(child)
                with dpg.table_row(parent="futures_table"):
                    dpg.add_text("Error")
                    dpg.add_text(f"Failed to load: {str(e)}")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")
                    dpg.add_text("")


    def update_futures_table(self):
        """Update futures table with current filter and search."""
        try:
            logger.info("update_futures_table called")
            
            if not hasattr(self, 'futures_products'):
                logger.warning("No futures_products attribute found")
                return
            
            logger.info(f"Found {len(self.futures_products)} products to display")
            
            # Get search query
            search_query = ""
            if dpg.does_item_exist("futures_search"):
                search_query = dpg.get_value("futures_search").lower()
                logger.info(f"Search query: '{search_query}'")
            
            # Filter products
            filtered_products = self.futures_products
            
            # Apply category filter (simplified - in production you'd map products to categories)
            if hasattr(self, 'current_filter') and self.current_filter != "ALL":
                # For now, show all products regardless of filter
                # In production, you'd filter based on product metadata/tags
                logger.info(f"Filter: {self.current_filter}")
                pass
            
            # Apply search filter
            if search_query:
                filtered_products = [
                    p for p in filtered_products
                    if search_query in p.get("symbol", "").lower()
                    or search_query in p.get("description", "").lower()
                ]
                logger.info(f"After search filter: {len(filtered_products)} products")
            
            # Clear existing table rows
            if not dpg.does_item_exist("futures_table"):
                logger.error("futures_table does not exist!")
                return
            
            logger.info("Clearing existing table rows")
            children = dpg.get_item_children("futures_table", slot=1)
            if children:
                logger.info(f"Deleting {len(children)} existing rows")
                for child in children:
                    dpg.delete_item(child)
            
            # Add new rows
            logger.info(f"Adding {len(filtered_products)} rows to table")
            rows_added = 0
            
            for product in filtered_products:  # Show all filtered products (only 3 specific symbols)
                symbol = product.get("symbol", "")
                ticker = self.futures_tickers.get(symbol, {})
                
                logger.debug(f"Processing {symbol}, ticker data: {bool(ticker)}")

                
                # Extract ticker data
                last_price = float(ticker.get("close", 0))
                change_24h = float(ticker.get("price_change_24h", 0))
                volume_24h = float(ticker.get("volume", 0))
                open_interest = float(ticker.get("open_interest", 0))
                high_24h = float(ticker.get("high", 0))
                low_24h = float(ticker.get("low", 0))
                
                # Calculate change percentage
                change_pct = (change_24h / last_price * 100) if last_price > 0 else 0
                change_color = (46, 204, 113) if change_pct >= 0 else (231, 76, 60)
                
                with dpg.table_row(parent="futures_table"):
                    # Contract
                    dpg.add_text(symbol)
                    
                    # Description
                    description = product.get("description", "")
                    dpg.add_text(description[:30] + "..." if len(description) > 30 else description)
                    
                    # Last Price
                    dpg.add_text(f"${last_price:,.2f}" if last_price > 0 else "--")
                    
                    # 24h Change
                    dpg.add_text(f"{change_pct:+.2f}%", color=change_color)
                    
                    # 24h Volume
                    if volume_24h >= 1_000_000:
                        dpg.add_text(f"${volume_24h/1_000_000:.2f}M")
                    elif volume_24h >= 1_000:
                        dpg.add_text(f"${volume_24h/1_000:.2f}K")
                    else:
                        dpg.add_text(f"${volume_24h:.2f}")
                    
                    # Open Interest
                    if open_interest >= 1_000_000:
                        dpg.add_text(f"${open_interest/1_000_000:.2f}M")
                    elif open_interest >= 1_000:
                        dpg.add_text(f"${open_interest/1_000:.2f}K")
                    else:
                        dpg.add_text(f"${open_interest:.2f}")
                    
                    # 24h High/Low
                    if high_24h > 0 and low_24h > 0:
                        dpg.add_text(f"${high_24h:,.2f} / ${low_24h:,.2f}")
                    else:
                        dpg.add_text("--")
                    
                    # Funding (placeholder - would need actual funding rate API)
                    contract_type = product.get("contract_type", "")
                    if "perpetual" in contract_type.lower():
                        dpg.add_text("0.01%", color=(160, 160, 160))
                    else:
                        dpg.add_text("--", color=(160, 160, 160))
                
                rows_added += 1
            
            logger.info(f"Futures table updated successfully with {rows_added} rows")
        except Exception as e:
            logger.exception("Failed to update futures table", error=str(e))
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")


    def filter_futures(self, category: str):
        """Filter futures by category."""
        try:
            self.current_filter = category
            self.update_futures_table()
            logger.info("Futures filtered", category=category)
        except Exception as e:
            logger.error("Failed to filter futures", error=str(e))

    def search_futures(self):
        """Search futures by query."""
        try:
            self.update_futures_table()
        except Exception as e:
            logger.error("Failed to search futures", error=str(e))

    def load_products(self):
        """Load available products (legacy method for compatibility)."""
        # Redirect to new futures method
        self.load_futures_products()

    def on_product_selected(self, sender, app_data):
        """Handle product selection (legacy method for compatibility)."""

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
