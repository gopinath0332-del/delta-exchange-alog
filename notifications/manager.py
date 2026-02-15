"""Notification manager."""

import time
import requests
from typing import Optional

from core.config import Config
from core.logger import get_logger
from .discord import DiscordNotifier
from .email import EmailNotifier

logger = get_logger(__name__)


class NotificationManager:
    """Manages all notification channels."""

    def __init__(self, config: Config):
        """
        Initialize Notification Manager.

        Args:
            config: Application configuration
        """
        self.config = config
        
        # Initialize Discord for regular alerts
        self.discord: Optional[DiscordNotifier] = None
        if config.discord_enabled and config.discord_webhook_url:
            self.discord = DiscordNotifier(config.discord_webhook_url)
            logger.info("Discord notifications enabled")
        
        # Initialize separate Discord for error alerts (if configured)
        self.discord_error: Optional[DiscordNotifier] = None
        if config.discord_enabled and config.discord_error_webhook_url:
            self.discord_error = DiscordNotifier(config.discord_error_webhook_url)
            logger.info("Discord error notifications enabled (separate webhook)")
        elif config.discord_enabled and config.discord_webhook_url:
            # Fallback to main webhook if error webhook not configured
            self.discord_error = self.discord
            logger.info("Discord error notifications will use main webhook")
            
        # Initialize Email
        self.email: Optional[EmailNotifier] = None
        if config.email_enabled:
            self.email = EmailNotifier(config)
            logger.info("Email notifications enabled")

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
        Send trade alert to all enabled channels.

        Args:
            symbol: Trading symbol
            side: LONG or SHORT
            price: Entry price
            rsi: RSI value
            reason: Explanation string
        """
        # Send to Discord
        if self.discord:
            self.discord.send_trade_alert(symbol, side, price, rsi, reason, margin_used, remaining_margin, strategy_name, pnl, funding_charges, trading_fees, market_price, lot_size)
            
        # Send to Email (if configured)
        if self.email:
            self.email.send_trade_alert(symbol, side, price, rsi, reason, margin_used, remaining_margin, strategy_name, pnl, funding_charges, trading_fees, market_price, lot_size)
            
        logger.info(f"Alert sent: {side} {symbol} @ {price} (RSI: {rsi:.2f})")

    def send_error(self, title: str, error: str):
        """Send error alert to error webhook (or main webhook if not configured)."""
        if self.discord_error:
            # Add ANSI red color to error text
            colored_error = f"\u001b[0;31mError:\u001b[0m {error}"
            formatted_message = f"```ansi\n{colored_error}\n```"
            
            # Send as embed
            try:
                embed = {
                    "title": f"⚠️ {title}",
                    "description": formatted_message,
                    "color": 15158332,  # Red
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                }
                
                payload = {"embeds": [embed]}
                
                response = requests.post(self.discord_error.webhook_url, json=payload, timeout=5)
                response.raise_for_status()
                logger.debug("Discord error alert sent with color")

            except requests.RequestException as e:
                logger.error("Discord connection failed", error=str(e))
            except Exception as e:
                logger.error("Failed to send Discord error notification", error=str(e))

    def send_status_message(self, title: str, message: str, order_placement_enabled: Optional[bool] = None):
        """
        Send status message to all enabled channels.
        
        Args:
            title: Message title
            message: Message content
            order_placement_enabled: If provided, will color-code Discord message based on order placement status
        """
        # Send to Discord with color support
        if self.discord:
            # Use colored version if order_placement_enabled is provided
            if hasattr(self.discord, 'send_status_message_with_color'):
                self.discord.send_status_message_with_color(title, message, order_placement_enabled)
            else:
                # Fallback to regular message
                color = 3447003  # Default Blue
                if order_placement_enabled is not None:
                    color = 5763719 if order_placement_enabled else 15548997
                self.discord.send_message(message, title=title, color=color)
            
        # Send to Email
        if self.email:
            self.email.send_status_message(title, message)
            
        logger.info(f"Status message sent: {title} - {message}")
