"""Notification manager."""

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
                        strategy_name: Optional[str] = None):
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
            self.discord.send_trade_alert(symbol, side, price, rsi, reason, margin_used, remaining_margin, strategy_name)
            
        # Send to Email (if configured)
        if self.email:
            self.email.send_trade_alert(symbol, side, price, rsi, reason, margin_used, remaining_margin, strategy_name)
            
        logger.info(f"Alert sent: {side} {symbol} @ {price} (RSI: {rsi:.2f})")

    def send_error(self, title: str, error: str):
        """Send error alert to error webhook (or main webhook if not configured)."""
        if self.discord_error:
            self.discord_error.send_message(f"**Error:** {error}", title=f"⚠️ {title}", color=15158332) # Red

    def send_status_message(self, title: str, message: str):
        """
        Send status message to all enabled channels.
        
        Args:
            title: Message title
            message: Message content
        """
        # Send to Discord (Blue color)
        if self.discord:
            self.discord.send_message(message, title=title, color=3447003)
            
        # Send to Email
        if self.email:
            self.email.send_status_message(title, message)
            
        logger.info(f"Status message sent: {title} - {message}")
