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
                        remaining_margin: Optional[float] = None):
        """
        Send a formatted trade alert.

        Args:
            symbol: Trading symbol (e.g. BTCUSD)
            side: Trade side (LONG/SHORT)
            price: Entry price
            rsi: RSI value
            reason: Trigger reason
        """
        title = f"🚀 TRADING SIGNAL: {side} {symbol}"
        color = 5763719 if side.upper() == "LONG" else 15548997  # Green for Long, Red for Short
        
        message = (
            f"**Price:** ${price:,.2f}\n"
            f"**RSI:** {rsi:.2f}\n"
            f"**Reason:** {reason}\n"
            f"**Time:** {time.strftime('%H:%M:%S UTC')}"
        )
        
        if margin_used is not None:
            message += f"\n**Margin Used:** ${margin_used:,.2f}"
            
        if remaining_margin is not None:
            message += f"\n**Remaining Wallet:** ${remaining_margin:,.2f}"
        
        self.send_message(message, title=title, color=color)
