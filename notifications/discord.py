"""Discord notification handler."""

import time
import requests
from typing import Optional, Dict

from core.logger import get_logger

logger = get_logger(__name__)


class DiscordNotifier:
    """Handles sending notifications to Discord via Webhooks."""

    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord Webhook URL
        """
        self.webhook_url = webhook_url
        self.last_alert_time: Dict[str, float] = {}
        self.throttle_interval = 60  # Min seconds between identical alerts

    def send_message(self, message: str, title: Optional[str] = None, color: Optional[int] = None):
        """
        Send a simple message to Discord.

        Args:
            message: Message content
            title: Optional title for embed
            color: Optional color code (integer)
        """
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return

        try:
            payload = {}
            
            if title:
                # Use embed for cleaner look
                embed = {
                    "title": title,
                    "description": message,
                    "color": color or 3447003,  # Default Blue
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
                payload["embeds"] = [embed]
            else:
                payload["content"] = message

            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logger.debug("Discord notification sent")

        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send Discord notification", error=str(e))

    def send_trade_alert(self, 
                        symbol: str, 
                        side: str, 
                        price: float, 
                        rsi: float, 
                        reason: str,
                        margin_used: Optional[float] = None,
                        remaining_margin: Optional[float] = None,
                        strategy_name: Optional[str] = None,
                        pnl: Optional[float] = None,
                        funding_charges: Optional[float] = None,
                        trading_fees: Optional[float] = None,
                        market_price: Optional[float] = None,
                        lot_size: Optional[int] = None):
        """
        Send a formatted trade alert with ANSI color codes.

        Args:
            symbol: Trading symbol (e.g. BTCUSD)
            side: Trade side (LONG/SHORT)
            price: Entry price
            rsi: RSI value
            reason: Trigger reason
            margin_used: Margin used directly for this trade
            remaining_margin: Remaining wallet balance
            strategy_name: Name of the strategy executing the trade
            pnl: Realized profit/loss (for exit signals)
            funding_charges: Total funding fees paid/received
            trading_fees: Commission/trading fees
            market_price: Actual market price (LTP) if different from order/signal price
            lot_size: Number of contracts/lots in the order
        """
        title = f"🚀 TRADING SIGNAL: {side} {symbol}"
        color = 5763719 if "LONG" in side.upper() else 15548997  # Green for Long, Red for Short
        
        # ANSI Color Codes
        # \u001b[1;37m = Bold White
        # \u001b[0;36m = Cyan
        # \u001b[0;33m = Yellow
        # \u001b[0;35m = Magenta
        # \u001b[0;31m = Red
        # \u001b[0m = Reset
        
        message = ""
        if strategy_name:
            message += f"Strategy: \u001b[1;37m{strategy_name}\u001b[0m\n"

        message += (
            f"Price: \u001b[0;36m${price:,.2f}\u001b[0m\n"
        )

        # Show Market Price if available and significantly different (> 0.05% diff)
        # OR if strictly requested to show context
        if market_price and market_price > 0:
            diff = abs(price - market_price)
            pct_diff = (diff / market_price) * 100
            
            # If price (HA) and market_price are different, show Market Price
            # We want to show it e.g. "Market Price: $22.28"
            if pct_diff > 0.01: # Show if diff > 0.01%
                message += f"Market Price: \u001b[0;36m${market_price:,.2f}\u001b[0m\n"

        message += (
            f"RSI: \u001b[0;33m{rsi:.2f}\u001b[0m\n"
        )
        
        # Show lot size if available
        if lot_size is not None:
            message += f"Lot Size: \u001b[0;36m{lot_size}\u001b[0m contracts\n"
        
        # Color-code [DISABLED] tag in reason if present
        if "[DISABLED]" in reason:
            reason = reason.replace("[DISABLED]", "\u001b[0;31m[DISABLED]\u001b[0m")
        
        message += f"Reason: {reason}\n"
        message += f"Time: {time.strftime('%H:%M:%S UTC')}"
        
        if margin_used is not None:
            message += f"\nMargin Used: \u001b[0;35m${margin_used:,.2f}\u001b[0m"
        
        # Show PnL, funding, and fees only for exit signals
        if "EXIT" in side.upper():
            if pnl is not None:
                # Color code: green for profit, red for loss
                pnl_color = "0;32" if pnl >= 0 else "0;31"
                message += f"\nP&L: \u001b[{pnl_color}m${pnl:+,.2f}\u001b[0m"
            
            if funding_charges is not None:
                message += f"\nFunding: ${funding_charges:+,.4f}"
            
            if trading_fees is not None:
                message += f"\nFees: ${trading_fees:,.4f}"
            
        if remaining_margin is not None:
            message += f"\nRemaining Wallet: \u001b[0;36m${remaining_margin:,.2f}\u001b[0m"
        
        # Wrap in ANSI code block for Discord
        formatted_message = f"```ansi\n{message}\n```"
        
        # Send as embed with color
        try:
            embed = {
                "title": title,
                "description": formatted_message,
                "color": color,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            
            payload = {"embeds": [embed]}
            
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logger.debug("Discord trade alert sent with colors")

        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send Discord notification", error=str(e))

    def send_status_message_with_color(self, title: str, message: str, order_placement_enabled: Optional[bool] = None):
        """
        Send a status message with ANSI color codes for better formatting.
        
        Args:
            title: Message title
            message: Message content (can include ANSI color codes)
            order_placement_enabled: If provided, will color-code the order placement status
        """
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return

        try:
            # Determine embed color based on order placement status
            if order_placement_enabled is not None:
                embed_color = 5763719 if order_placement_enabled else 15548997  # Green if enabled, Red if disabled
            else:
                embed_color = 3447003  # Default Blue
            
            # Format message with ANSI color codes
            # Discord supports ANSI in code blocks with ```ansi
            formatted_message = f"```ansi\n{message}\n```"
            
            embed = {
                "title": title,
                "description": formatted_message,
                "color": embed_color,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
            
            payload = {"embeds": [embed]}
            
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            response.raise_for_status()
            logger.debug("Discord status message sent with color")

        except requests.RequestException as e:
            logger.error("Discord connection failed", error=str(e))
        except Exception as e:
            logger.error("Failed to send Discord notification", error=str(e))
