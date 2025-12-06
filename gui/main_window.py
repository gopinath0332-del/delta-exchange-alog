"""Main GUI window for the Delta Exchange trading platform."""

import threading
import time
from typing import Any, Dict, Optional

import dearpygui.dearpygui as dpg

from api.rest_client import DeltaRestClient
from core.config import Config
from core.logger import get_logger
from gui.components.charts import ChartPanel, LogPanel
from gui.components.market_data import OrderbookPanel, ProductSelector, TickerPanel
from gui.components.portfolio import BalancePanel, OrdersTable, PositionsTable
from gui.components.theme import Colors, initialize_common_themes, setup_theme
from gui.components.trading_panel import TradingPanel

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

        # Component instances
        self.product_selector: Optional[ProductSelector] = None
        self.ticker_panel: Optional[TickerPanel] = None
        self.orderbook_panel: Optional[OrderbookPanel] = None
        self.trading_panel: Optional[TradingPanel] = None
        self.positions_table: Optional[PositionsTable] = None
        self.orders_table: Optional[OrdersTable] = None
        self.balance_panel: Optional[BalancePanel] = None
        self.chart_panel: Optional[ChartPanel] = None
        self.log_panel: Optional[LogPanel] = None

        # UI element tags
        self.main_window_tag = "main_window"
        self.status_text_tag = dpg.generate_uuid()
        self.env_indicator_tag = dpg.generate_uuid()

        logger.info("Trading GUI initialized", environment=config.environment)

    def start(self):
        """Start the GUI application."""
        try:
            # Create DearPyGui context
            dpg.create_context()

            # Setup theme
            theme = setup_theme()
            dpg.bind_theme(theme)

            # Initialize common themes
            initialize_common_themes()

            # Create main window
            self._create_main_window()

            # Create viewport
            dpg.create_viewport(
                title=f"Delta Exchange Trading Platform - {self.config.environment.upper()}",
                width=1400,
                height=900,
            )

            # Setup and show viewport
            dpg.setup_dearpygui()
            dpg.show_viewport()

            # Set primary window
            dpg.set_primary_window(self.main_window_tag, True)

            # Start update thread
            self.running = True
            self.update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self.update_thread.start()

            logger.info("GUI started successfully")

            # Add initial log
            if self.log_panel:
                self.log_panel.add_log("INFO", "Trading GUI started successfully")
                self.log_panel.add_log(
                    "INFO", f"Environment: {self.config.environment.upper()}"
                )

            # Main render loop
            while dpg.is_dearpygui_running():
                dpg.render_dearpygui_frame()

        except Exception as e:
            logger.exception("GUI error", error=str(e))
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

    def _create_main_window(self):
        """Create the main window with all components."""
        with dpg.window(tag=self.main_window_tag, label="Delta Exchange Trading"):
            # Menu bar
            with dpg.menu_bar():
                with dpg.menu(label="File"):
                    dpg.add_menu_item(label="Settings", callback=self._show_settings)
                    dpg.add_separator()
                    dpg.add_menu_item(label="Exit", callback=self._exit_app)

                with dpg.menu(label="Help"):
                    dpg.add_menu_item(label="About", callback=self._show_about)

            # Status bar at top
            with dpg.group(horizontal=True):
                dpg.add_text("Status:", color=Colors.TEXT_SECONDARY)
                dpg.add_text("Connected", tag=self.status_text_tag, color=Colors.SUCCESS)

                dpg.add_spacer(width=20)

                dpg.add_text("Environment:", color=Colors.TEXT_SECONDARY)
                env_color = Colors.WARNING if self.config.is_testnet() else Colors.ERROR
                dpg.add_text(
                    self.config.environment.upper(),
                    tag=self.env_indicator_tag,
                    color=env_color,
                )

            dpg.add_separator()
            dpg.add_spacer(height=5)

            # Main content with tabs
            with dpg.tab_bar():
                # Dashboard Tab
                with dpg.tab(label="Dashboard"):
                    self._create_dashboard_tab()

                # Trading Tab
                with dpg.tab(label="Trading"):
                    self._create_trading_tab()

                # Positions Tab
                with dpg.tab(label="Positions"):
                    self._create_positions_tab()

                # Orders Tab
                with dpg.tab(label="Orders"):
                    self._create_orders_tab()

                # Charts Tab
                with dpg.tab(label="Charts"):
                    self._create_charts_tab()

                # Logs Tab
                with dpg.tab(label="Logs"):
                    self._create_logs_tab()

    def _create_dashboard_tab(self):
        """Create dashboard tab with overview."""
        with dpg.group(horizontal=True):
            # Left column - Balance
            with dpg.child_window(width=400, height=-1):
                self.balance_panel = BalancePanel(self.api_client)
                self.balance_panel.render()

            # Right column - Quick stats
            with dpg.child_window(width=-1, height=-1):
                dpg.add_text("Quick Overview", color=Colors.ACCENT_PRIMARY)
                dpg.add_separator()
                dpg.add_spacer(height=10)

                dpg.add_text("Welcome to Delta Exchange Trading Platform!")
                dpg.add_spacer(height=10)
                dpg.add_text("• Use the Trading tab to place orders")
                dpg.add_text("• Monitor your positions in the Positions tab")
                dpg.add_text("• View and manage orders in the Orders tab")
                dpg.add_text("• Analyze price charts in the Charts tab")
                dpg.add_text("• Check application logs in the Logs tab")

                dpg.add_spacer(height=20)
                dpg.add_separator()
                dpg.add_spacer(height=10)

                # Environment warning
                if self.config.is_testnet():
                    dpg.add_text(
                        "⚠ TESTNET MODE - No real funds at risk",
                        color=Colors.WARNING,
                    )
                else:
                    dpg.add_text(
                        "⚠ PRODUCTION MODE - Real funds at risk!",
                        color=Colors.ERROR,
                    )

    def _create_trading_tab(self):
        """Create trading tab with market data and order placement."""
        with dpg.group(horizontal=True):
            # Left column - Market data
            with dpg.child_window(width=400, height=-1):
                # Product selector
                self.product_selector = ProductSelector(
                    self.api_client, self._on_product_selected
                )
                self.product_selector.render()

                dpg.add_spacer(height=10)

                # Ticker
                self.ticker_panel = TickerPanel(self.api_client, height=250)
                self.ticker_panel.render()

                dpg.add_spacer(height=10)

                # Orderbook
                self.orderbook_panel = OrderbookPanel(self.api_client, height=-1, depth=8)
                self.orderbook_panel.render()

            # Right column - Trading panel
            with dpg.child_window(width=-1, height=-1):
                self.trading_panel = TradingPanel(
                    self.api_client, on_order_placed=self._on_order_placed
                )
                self.trading_panel.render()

    def _create_positions_tab(self):
        """Create positions tab."""
        with dpg.group(horizontal=True):
            # Positions table
            with dpg.child_window(width=-1, height=-1):
                dpg.add_text("Open Positions", color=Colors.ACCENT_PRIMARY)
                dpg.add_separator()
                dpg.add_spacer(height=5)

                dpg.add_button(label="Refresh", callback=lambda: self.positions_table.refresh())

                dpg.add_spacer(height=10)

                self.positions_table = PositionsTable(self.api_client)
                self.positions_table.render()

    def _create_orders_tab(self):
        """Create orders tab."""
        with dpg.child_window(width=-1, height=-1):
            dpg.add_text("Live Orders", color=Colors.ACCENT_PRIMARY)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            dpg.add_button(label="Refresh", callback=lambda: self.orders_table.refresh())

            dpg.add_spacer(height=10)

            self.orders_table = OrdersTable(self.api_client)
            self.orders_table.render()

    def _create_charts_tab(self):
        """Create charts tab."""
        with dpg.child_window(width=-1, height=-1):
            self.chart_panel = ChartPanel(self.api_client, height=-1)
            self.chart_panel.render()

    def _create_logs_tab(self):
        """Create logs tab."""
        with dpg.child_window(width=-1, height=-1):
            self.log_panel = LogPanel(height=-1)
            self.log_panel.render()

    def _on_product_selected(self, product: Dict[str, Any]):
        """Handle product selection."""
        self.selected_product = product
        symbol = product.get("symbol", "")
        product_id = product.get("id")

        logger.info("Product selected in GUI", symbol=symbol, product_id=product_id)

        # Update components
        if self.ticker_panel:
            self.ticker_panel.update(symbol)

        if self.orderbook_panel and product_id:
            self.orderbook_panel.update(product_id)

        if self.trading_panel:
            self.trading_panel.update(product)

        if self.chart_panel:
            self.chart_panel.update(symbol)

        if self.log_panel:
            self.log_panel.add_log("INFO", f"Selected product: {symbol}")

    def _on_order_placed(self, order: Dict[str, Any]):
        """Handle order placement."""
        order_id = order.get("id", "Unknown")
        logger.info("Order placed via GUI", order_id=order_id)

        if self.log_panel:
            self.log_panel.add_log("INFO", f"Order placed: {order_id}")

        # Refresh orders table
        if self.orders_table:
            self.orders_table.refresh()

    def _update_loop(self):
        """Background update loop for real-time data."""
        update_interval = self.config.gui.update_interval / 1000  # Convert ms to seconds

        while self.running:
            try:
                # Update ticker if product is selected
                if self.selected_product and self.ticker_panel:
                    symbol = self.selected_product.get("symbol")
                    if symbol:
                        self.ticker_panel.update(symbol)

                # Update orderbook if product is selected
                if self.selected_product and self.orderbook_panel:
                    product_id = self.selected_product.get("id")
                    if product_id:
                        self.orderbook_panel.update(product_id)

                # Update balance
                if self.balance_panel:
                    self.balance_panel.refresh()

                time.sleep(update_interval)

            except Exception as e:
                logger.error("Update loop error", error=str(e))
                time.sleep(update_interval * 2)  # Back off on error

    def _show_settings(self):
        """Show settings dialog."""
        if self.log_panel:
            self.log_panel.add_log("INFO", "Settings dialog not yet implemented")

    def _show_about(self):
        """Show about dialog."""
        with dpg.window(label="About", modal=True, width=400, height=200):
            dpg.add_text("Delta Exchange Trading Platform")
            dpg.add_text("Version: 0.1.0")
            dpg.add_spacer(height=10)
            dpg.add_text("A comprehensive crypto trading platform")
            dpg.add_text("with backtesting and live trading support.")
            dpg.add_spacer(height=20)
            dpg.add_button(label="Close", callback=lambda: dpg.delete_item(dpg.last_item()))

    def _exit_app(self):
        """Exit the application."""
        logger.info("Exit requested by user")
        dpg.stop_dearpygui()


def run_gui(config: Config):
    """
    Run the GUI application.

    Args:
        config: Configuration instance
    """
    gui = TradingGUI(config)
    gui.start()
