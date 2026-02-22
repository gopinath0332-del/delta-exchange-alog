"""Error alerting handler for critical log messages."""

import logging
import os
import sys
from datetime import datetime
from typing import Dict, Optional

import requests


class ErrorAlertHandler(logging.Handler):
    """
    Custom logging handler that sends alerts for ERROR and CRITICAL messages.
    
    Supports Discord webhooks and email notifications with throttling to prevent spam.
    """

    def __init__(
        self,
        discord_webhook_url: Optional[str] = None,
        alert_throttle_seconds: int = 300,  # 5 minutes default
        min_level: int = logging.ERROR,
    ):
        """
        Initialize the error alert handler.

        Args:
            discord_webhook_url: Discord webhook URL for alerts
            alert_throttle_seconds: Minimum seconds between alerts for same error
            min_level: Minimum log level to trigger alerts (default: ERROR)
        """
        super().__init__()
        self.discord_webhook_url = discord_webhook_url
        self.alert_throttle_seconds = alert_throttle_seconds
        self.min_level = min_level
        
        # Track last alert time for each error type to prevent spam
        self._last_alert_times: Dict[str, datetime] = {}
        
        # Set handler level
        self.setLevel(min_level)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record by sending alerts.

        Args:
            record: Log record to process
        """
        try:
            # Check if we should throttle this alert
            if self._should_throttle(record):
                return

            # Send Discord alert if configured
            if self.discord_webhook_url:
                self._send_discord_alert(record)

            # Update last alert time
            self._update_alert_time(record)

        except Exception:
            # Don't let alert failures break logging
            self.handleError(record)

    def _should_throttle(self, record: logging.LogRecord) -> bool:
        """
        Check if this alert should be throttled.

        Args:
            record: Log record to check

        Returns:
            True if alert should be throttled
        """
        # Create a key based on logger name and message
        alert_key = f"{record.name}:{record.levelname}:{record.getMessage()[:100]}"
        
        last_alert_time = self._last_alert_times.get(alert_key)
        if last_alert_time is None:
            return False

        # Check if enough time has passed since last alert
        time_since_last = datetime.now() - last_alert_time
        return time_since_last.total_seconds() < self.alert_throttle_seconds

    def _update_alert_time(self, record: logging.LogRecord) -> None:
        """
        Update the last alert time for this error type.

        Args:
            record: Log record
        """
        alert_key = f"{record.name}:{record.levelname}:{record.getMessage()[:100]}"
        self._last_alert_times[alert_key] = datetime.now()

    def _send_discord_alert(self, record: logging.LogRecord) -> None:
        """
        Send alert to Discord webhook.

        Args:
            record: Log record to send
        """
        try:
            # Format timestamp
            timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")

            # Determine color based on level
            color_map = {
                "ERROR": 0xFF0000,  # Red
                "CRITICAL": 0x8B0000,  # Dark red
                "WARNING": 0xFFA500,  # Orange
            }
            color = color_map.get(record.levelname, 0xFF0000)

            # Build embed
            embed = {
                "title": f"🚨 {record.levelname} Alert",
                "description": record.getMessage(),
                "color": color,
                "fields": [
                    {"name": "Logger", "value": record.name, "inline": True},
                    {"name": "Level", "value": record.levelname, "inline": True},
                    {"name": "Time", "value": timestamp, "inline": True},
                ],
                "footer": {"text": "Delta Exchange Trading Platform"},
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Add exception info if present
            if record.exc_info:
                exc_text = self.format(record)
                # Limit exception text to avoid Discord message limits
                if len(exc_text) > 1000:
                    exc_text = exc_text[:1000] + "...\n[Truncated]"
                embed["fields"].append(
                    {"name": "Exception", "value": f"```\n{exc_text}\n```", "inline": False}
                )

            # Send to Discord
            payload = {
                "embeds": [embed],
                "username": "Trading Bot Alerts",
            }

            response = requests.post(
                self.discord_webhook_url,
                json=payload,
                timeout=5,
            )
            response.raise_for_status()

        except Exception as e:
            # Log the error but don't raise to avoid breaking the application
            print(f"Failed to send Discord alert: {e}", file=sys.stderr)

    def _send_email_alert(self, record: logging.LogRecord) -> None:
        """
        Send alert via email.

        Args:
            record: Log record to send
        """
        # TODO: Implement email alerting
        # This would integrate with the existing email notification system
        pass


def create_error_alert_handler(
    discord_webhook_url: Optional[str] = None,
    alert_throttle_seconds: int = 300,
) -> Optional[ErrorAlertHandler]:
    """
    Create an error alert handler if Discord webhook is configured.

    Args:
        discord_webhook_url: Discord webhook URL
        alert_throttle_seconds: Throttle time in seconds

    Returns:
        ErrorAlertHandler instance or None if not configured
    """
    if not discord_webhook_url:
        return None

    return ErrorAlertHandler(
        discord_webhook_url=discord_webhook_url,
        alert_throttle_seconds=alert_throttle_seconds,
    )


# Example usage
if __name__ == "__main__":
    import sys
    
    # Setup basic logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Create alert handler using the dedicated error webhook (DISCORD_ERROR_WEBHOOK_URL),
    # NOT the general trade-notification webhook (DISCORD_WEBHOOK_URL).
    alert_handler = ErrorAlertHandler(
        discord_webhook_url=os.getenv("DISCORD_ERROR_WEBHOOK_URL"),
        alert_throttle_seconds=10,  # Short throttle for testing
    )
    
    # Add to root logger
    logger = logging.getLogger()
    logger.addHandler(alert_handler)
    
    # Test alerts
    test_logger = logging.getLogger("test.module")
    
    print("Testing error alerts...")
    test_logger.error("Test error message", extra={"user_id": 123})
    
    print("Testing critical alert...")
    test_logger.critical("Critical system failure", extra={"component": "database"})
    
    print("Testing throttling (should not send)...")
    test_logger.error("Test error message", extra={"user_id": 123})
    
    print("Done!")
