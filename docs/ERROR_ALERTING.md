# Error Alerting System

## Overview

The log manager includes an automated error alerting system that sends notifications to Discord (and optionally email) when ERROR or CRITICAL log messages occur. This helps you monitor your trading application in real-time and respond quickly to issues.

## Features

- **Automatic Discord Notifications**: Sends rich embedded messages to Discord for errors
- **Alert Throttling**: Prevents spam by limiting alerts for the same error
- **Configurable Severity**: Only alerts on ERROR and CRITICAL messages by default
- **Rich Context**: Includes logger name, timestamp, and full exception tracebacks
- **Production-Ready**: Handles failures gracefully without breaking your application

## Configuration

### Environment Variables

Add these to your `config/.env` file:

```bash
# Error Alerting
ENABLE_ERROR_ALERTS=true                    # Enable/disable error alerts
DISCORD_ENABLED=true                        # Enable Discord notifications

# Two separate webhooks are used:
# - DISCORD_WEBHOOK_URL         → general trade notifications (entries, exits, etc.)
# - DISCORD_ERROR_WEBHOOK_URL   → ERROR/CRITICAL application alerts only
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_TRADE_WEBHOOK_URL
DISCORD_ERROR_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ERROR_WEBHOOK_URL

ALERT_THROTTLE_SECONDS=300                  # Minimum seconds between same alerts (5 minutes)

# Logging
LOG_LEVEL=INFO                              # Or DEBUG for development
LOG_FILE=logs/trading.log
LOG_MAX_BYTES=524288000                     # 500MB
LOG_BACKUP_COUNT=5
```

### Getting a Discord Webhook URL

1. Open your Discord server
2. Go to Server Settings → Integrations → Webhooks
3. Click "New Webhook"
4. Name it (e.g., "Trading Bot Alerts")
5. Select the channel for alerts
6. Copy the Webhook URL
7. Add it to your `.env` file

## How It Works

### Alert Triggering

The system automatically sends alerts when:

- An ERROR level log message is recorded
- A CRITICAL level log message is recorded
- An exception is logged with `logger.exception()`

### Alert Throttling

To prevent spam, the system throttles duplicate alerts:

- Each unique error (based on logger name, level, and message) is tracked
- If the same error occurs within the throttle period (default: 5 minutes), subsequent alerts are suppressed
- After the throttle period expires, the next occurrence will trigger an alert

### Discord Message Format

Alerts appear as rich embedded messages with:

- **Title**: 🚨 ERROR Alert or 🚨 CRITICAL Alert
- **Description**: The log message
- **Fields**:
  - Logger name
  - Log level
  - Timestamp
  - Exception traceback (if applicable)
- **Color**: Red for ERROR, Dark red for CRITICAL

## Usage Examples

### Basic Error Logging

```python
from core.logger import get_logger

logger = get_logger(__name__)

# This will trigger a Discord alert
logger.error("Failed to connect to exchange",
             endpoint="wss://api.delta.exchange",
             error="Connection timeout",
             retry_count=3)
```

### Exception Logging

```python
from core.logger import get_logger

logger = get_logger(__name__)

try:
    result = risky_operation()
except Exception:
    # This will trigger a Discord alert with full traceback
    logger.exception("Operation failed",
                     operation="place_order",
                     order_id="12345")
```

### Using LogManager

```python
from core.logger import LogManager

log_mgr = LogManager("trading.executor")

# This will trigger a Discord alert
log_mgr.log_failure("Execute Trade",
                     error="Insufficient funds",
                     symbol="BTCUSD",
                     required=1000,
                     available=500)
```

## Alert Examples

### Simple Error Alert

```
🚨 ERROR Alert

Failed to connect to exchange

Logger: api.websocket_client
Level: ERROR
Time: 2025-12-06 18:30:15

endpoint=wss://api.delta.exchange
error=Connection timeout
retry_count=3
```

### Exception Alert with Traceback

````
🚨 CRITICAL Alert

Database connection lost

Logger: trading.database
Level: CRITICAL
Time: 2025-12-06 18:30:15

Exception:
```python
Traceback (most recent call last):
  File "/app/trading/database.py", line 45, in connect
    conn = psycopg2.connect(dsn)
psycopg2.OperationalError: could not connect to server
````

````

## Best Practices

### 1. Use Appropriate Log Levels

Only use ERROR and CRITICAL for issues that need immediate attention:

```python
# Good - will trigger alert
logger.error("Payment processing failed", transaction_id=tx_id)

# Bad - will trigger unnecessary alerts
logger.error("User clicked button")  # This should be INFO
````

### 2. Include Context

Always include relevant context in your error messages:

```python
# Good - provides actionable information
logger.error("Order rejected",
             symbol="BTCUSD",
             reason="Insufficient funds",
             required=1000,
             available=500)

# Bad - not enough information
logger.error("Order failed")
```

### 3. Handle Sensitive Data

Never log sensitive information:

```python
# BAD - logs API secret
logger.error("Authentication failed", api_secret=secret)

# GOOD - logs safe information
logger.error("Authentication failed", api_key_prefix=secret[:8])
```

### 4. Monitor Alert Volume

If you're receiving too many alerts:

- Increase `ALERT_THROTTLE_SECONDS`
- Review your error handling logic
- Consider if some ERRORs should be WARNINGs

## Disabling Alerts

### Temporarily Disable

Set in your `.env`:

```bash
ENABLE_ERROR_ALERTS=false
```

### Disable for Specific Environments

```python
# In your code
from core.config import get_config

config = get_config()

# Only enable alerts in production
enable_alerts = config.environment == "production"

setup_logging(
    ...
    enable_error_alerts=enable_alerts,
)
```

## Troubleshooting

### Alerts Not Sending

1. **Check Discord webhook URL**:

   ```bash
   curl -X POST -H "Content-Type: application/json" \
        -d '{"content": "Test message"}' \
        YOUR_WEBHOOK_URL
   ```

2. **Check configuration**:

   ```python
   from core.config import get_config
   config = get_config()
   print(f"Alerts enabled: {config.enable_error_alerts}")
   print(f"Discord enabled: {config.discord_enabled}")
   # discord_error_webhook_url is used exclusively for ERROR/CRITICAL alerts
   print(f"Error Webhook URL: {config.discord_error_webhook_url[:50]}...")
   ```

3. **Check logs**: Look for error alert handler errors in your logs

### Too Many Alerts

1. Increase throttle time:

   ```bash
   ALERT_THROTTLE_SECONDS=600  # 10 minutes
   ```

2. Review log levels - are you using ERROR when you should use WARNING?

3. Add error handling to prevent repeated failures

### Alert Formatting Issues

- Discord has a 2000 character limit for embed descriptions
- Long exception tracebacks are automatically truncated
- If you need full tracebacks, check the log file

## Advanced Configuration

### Custom Alert Handler

You can create a custom alert handler:

```python
from core.error_alerts import ErrorAlertHandler

class CustomAlertHandler(ErrorAlertHandler):
    def _send_discord_alert(self, record):
        # Custom Discord formatting
        super()._send_discord_alert(record)

    def _send_email_alert(self, record):
        # Implement email alerting
        pass
```

### Multiple Alert Channels

```python
# Send to different Discord channels based on severity
critical_handler = ErrorAlertHandler(
    discord_webhook_url=CRITICAL_WEBHOOK_URL,
    min_level=logging.CRITICAL,
)

error_handler = ErrorAlertHandler(
    discord_webhook_url=ERROR_WEBHOOK_URL,
    min_level=logging.ERROR,
)

logger = logging.getLogger()
logger.addHandler(critical_handler)
logger.addHandler(error_handler)
```

## Monitoring Recommendations

1. **Create a dedicated Discord channel** for alerts
2. **Set up mobile notifications** for the alerts channel
3. **Review alerts daily** to identify patterns
4. **Adjust throttling** based on alert volume
5. **Document common alerts** and their solutions

## Future Enhancements

Planned features:

- Email alerting support
- Slack integration
- PagerDuty integration
- Alert aggregation and summaries
- Custom alert templates
- Alert routing based on error type
