"""Chart and log visualization components."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import dearpygui.dearpygui as dpg

from api.rest_client import DeltaRestClient
from core.logger import get_logger
from gui.components.base_component import BasePanel
from gui.components.theme import Colors

logger = get_logger(__name__)


class ChartPanel(BasePanel):
    """Panel displaying candlestick charts."""

    def __init__(
        self,
        api_client: DeltaRestClient,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 500,
    ):
        """
        Initialize chart panel.

        Args:
            api_client: Delta REST API client
            tag: Optional unique tag
            width: Panel width
            height: Panel height
        """
        super().__init__("Price Chart", tag, width, height, border=False)
        self.api_client = api_client
        self.current_symbol: Optional[str] = None
        self.current_timeframe = "1h"

        # UI element tags
        self.timeframe_combo_tag = dpg.generate_uuid()
        self.plot_tag = dpg.generate_uuid()
        self.candle_series_tag = dpg.generate_uuid()
        self.xaxis_tag = dpg.generate_uuid()
        self.yaxis_tag = dpg.generate_uuid()

    def render_content(self):
        """Render chart panel content."""
        # Timeframe selector
        with dpg.group(horizontal=True):
            dpg.add_text("Timeframe:", color=Colors.TEXT_SECONDARY)
            dpg.add_combo(
                tag=self.timeframe_combo_tag,
                items=["5m", "15m", "1h", "4h", "1d"],
                default_value="1h",
                callback=self._on_timeframe_changed,
                width=100,
            )

            dpg.add_spacer(width=20)

            dpg.add_button(
                label="Refresh",
                callback=lambda: self.update(self.current_symbol) if self.current_symbol else None,
            )

        dpg.add_spacer(height=10)

        # Create plot
        with dpg.plot(
            tag=self.plot_tag,
            label="",
            height=-1,
            width=-1,
        ):
            dpg.add_plot_legend()

            # X-axis (time)
            dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag=self.xaxis_tag, time=True)

            # Y-axis (price)
            dpg.add_plot_axis(dpg.mvYAxis, label="Price ($)", tag=self.yaxis_tag)

            # Candlestick series will be added dynamically

    def _on_timeframe_changed(self, sender, app_data):
        """Handle timeframe change."""
        self.current_timeframe = app_data
        if self.current_symbol:
            self.update(self.current_symbol)

    def update(self, symbol: str):
        """
        Update chart with new symbol data.

        Args:
            symbol: Trading symbol
        """
        try:
            self.current_symbol = symbol

            # Fetch historical candles
            candles = self.api_client.get_historical_candles(
                symbol=symbol,
                resolution=self.current_timeframe,
                days=7,  # Last 7 days
            )

            if not candles:
                logger.warning("No candles data received", symbol=symbol)
                return

            # Prepare data for candlestick plot
            dates = []
            opens = []
            highs = []
            lows = []
            closes = []

            for candle in candles:
                timestamp = candle.get("time", 0)
                dates.append(timestamp)
                opens.append(candle.get("open", 0))
                highs.append(candle.get("high", 0))
                lows.append(candle.get("low", 0))
                closes.append(candle.get("close", 0))

            # Clear existing series
            if dpg.does_item_exist(self.yaxis_tag):
                children = dpg.get_item_children(self.yaxis_tag, slot=1)
                if children:
                    for child in children:
                        dpg.delete_item(child)

            # Add candlestick series
            if dates and opens and highs and lows and closes:
                dpg.add_candle_series(
                    dates,
                    opens,
                    closes,
                    lows,
                    highs,
                    label=f"{symbol} {self.current_timeframe}",
                    parent=self.yaxis_tag,
                    bull_color=Colors.CANDLE_UP,
                    bear_color=Colors.CANDLE_DOWN,
                )

                # Fit axes to data
                dpg.fit_axis_data(self.xaxis_tag)
                dpg.fit_axis_data(self.yaxis_tag)

            logger.info(
                "Chart updated",
                symbol=symbol,
                timeframe=self.current_timeframe,
                candles=len(candles),
            )

        except Exception as e:
            logger.error("Failed to update chart", symbol=symbol, error=str(e))


class LogPanel(BasePanel):
    """Panel displaying application logs."""

    def __init__(
        self,
        tag: Optional[str] = None,
        width: int = -1,
        height: int = 400,
        max_lines: int = 1000,
    ):
        """
        Initialize log panel.

        Args:
            tag: Optional unique tag
            width: Panel width
            height: Panel height
            max_lines: Maximum number of log lines to keep
        """
        super().__init__("Application Logs", tag, width, height)
        self.max_lines = max_lines
        self.log_lines: List[str] = []

        # UI element tags
        self.log_text_tag = dpg.generate_uuid()
        self.level_filter_tag = dpg.generate_uuid()
        self.auto_scroll_tag = dpg.generate_uuid()

    def render_content(self):
        """Render log panel content."""
        # Controls
        with dpg.group(horizontal=True):
            dpg.add_text("Filter:", color=Colors.TEXT_SECONDARY)
            dpg.add_combo(
                tag=self.level_filter_tag,
                items=["All", "DEBUG", "INFO", "WARNING", "ERROR"],
                default_value="All",
                width=100,
            )

            dpg.add_spacer(width=20)

            dpg.add_checkbox(
                tag=self.auto_scroll_tag,
                label="Auto-scroll",
                default_value=True,
            )

            dpg.add_spacer(width=20)

            dpg.add_button(label="Clear", callback=self._clear_logs)

        dpg.add_separator()
        dpg.add_spacer(height=5)

        # Log display
        with dpg.child_window(height=-1, border=True):
            dpg.add_text("", tag=self.log_text_tag, wrap=0)

    def add_log(self, level: str, message: str, timestamp: Optional[datetime] = None):
        """
        Add a log entry.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            message: Log message
            timestamp: Optional timestamp
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Format log line
        time_str = timestamp.strftime("%H:%M:%S")
        log_line = f"[{time_str}] [{level}] {message}"

        # Add to log lines
        self.log_lines.append(log_line)

        # Trim if exceeds max lines
        if len(self.log_lines) > self.max_lines:
            self.log_lines = self.log_lines[-self.max_lines:]

        # Update display
        self._update_display()

    def _update_display(self):
        """Update log display."""
        if not dpg.does_item_exist(self.log_text_tag):
            return

        # Get filter
        level_filter = dpg.get_value(self.level_filter_tag) if dpg.does_item_exist(self.level_filter_tag) else "All"

        # Filter logs
        filtered_lines = self.log_lines
        if level_filter != "All":
            filtered_lines = [line for line in self.log_lines if f"[{level_filter}]" in line]

        # Update text
        log_text = "\n".join(filtered_lines)
        dpg.set_value(self.log_text_tag, log_text)

        # Auto-scroll if enabled
        if dpg.does_item_exist(self.auto_scroll_tag) and dpg.get_value(self.auto_scroll_tag):
            # Scroll to bottom (DearPyGui doesn't have direct scroll API, but setting value triggers it)
            pass

    def _clear_logs(self):
        """Clear all logs."""
        self.log_lines = []
        self._update_display()

    def update(self, data: Any):
        """Update log panel."""
        # Logs are added via add_log method, not through update
        pass
