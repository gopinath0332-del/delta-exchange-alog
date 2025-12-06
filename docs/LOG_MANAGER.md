# Log Manager Documentation

## Overview

The enhanced log manager provides comprehensive logging capabilities for the Delta Exchange trading application with human-readable formatting for both console and file outputs.

## Features

- **Human-Readable Formatting**: Logs are formatted in an easy-to-read format with timestamps, log levels, and logger names
- **Colored Console Output**: Terminal output uses colors to distinguish different log levels (when outputting to a TTY)
- **File Logging with Rotation**: Automatic log file rotation based on size limits
- **Structured Logging**: Uses `structlog` for structured, contextual logging
- **Multiple Log Levels**: Support for DEBUG, INFO, WARNING, ERROR, and CRITICAL levels
- **Exception Tracking**: Automatic exception logging with full tracebacks
- **LogManager Class**: Convenient wrapper class for common logging operations

## Usage

### Basic Logger

```python
from core.logger import get_logger, setup_logging

# Setup logging (typically done once at application startup)
setup_logging(
    log_level="INFO",
    log_file="logs/trading.log",
    log_max_bytes=10485760,  # 10MB
    log_backup_count=5,
    human_readable=True
)

# Get a logger instance
logger = get_logger(__name__)

# Log messages with context
logger.info("User logged in", user_id=123, ip="192.168.1.1")
logger.warning("High memory usage", usage_percent=85, threshold=80)
logger.error("Failed to connect", error="Connection timeout", retry_count=3)

# Log exceptions
try:
    result = risky_operation()
except Exception:
    logger.exception("Operation failed", operation="risky_operation")
```

### LogManager Class

The `LogManager` class provides additional convenience methods:

```python
from core.logger import LogManager, setup_logging

# Setup logging
setup_logging(log_level="INFO", log_file="logs/trading.log")

# Create a log manager
log_mgr = LogManager("trading.strategy")

# Log operations
log_mgr.log_operation("Place Order", symbol="BTCUSD", quantity=0.5, price=45000)
log_mgr.log_success("Place Order", order_id="12345", filled_price=45010)
log_mgr.log_failure("Fetch Market Data", error="Connection timeout", retry_count=3)

# Standard logging methods
log_mgr.info("Strategy initialized", strategy="momentum")
log_mgr.warning("Low liquidity detected", symbol="ETHUSD")
log_mgr.error("Order rejected", reason="Insufficient funds")
```

## Log Format

### Console Output (with colors in terminal)

```
2025-12-06T12:14:57.268540Z [debug    ] Debug message                  [__main__] key=value number=42
2025-12-06T12:14:57.269102Z [info     ] Info message                   [__main__] status=success user=admin
2025-12-06T12:14:57.269312Z [warning  ] Warning message                [__main__] alert='check this' threshold=90
2025-12-06T12:14:57.269450Z [error    ] Error message                  [__main__] endpoint=/api/trade error_code=500
```

### File Output

```
[2025-12-06 17:44:20.055] [DEBUG   ] [__main__                      ] 2025-12-06T12:14:20.054772Z [debug    ] Debug message                  [__main__] key=value number=42
[2025-12-06 17:44:20.055] [INFO    ] [__main__                      ] 2025-12-06T12:14:20.055567Z [info     ] Info message                   [__main__] status=success user=admin
[2025-12-06 17:44:20.055] [WARNING ] [__main__                      ] 2025-12-06T12:14:20.055813Z [warning  ] Warning message                [__main__] alert='check this' threshold=90
```

## Configuration

### Environment Variables

Configure logging through environment variables or the `config/.env` file:

```bash
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE=logs/trading.log   # Path to log file
LOG_MAX_BYTES=10485760      # Max file size before rotation (10MB)
LOG_BACKUP_COUNT=5          # Number of backup files to keep
```

### Programmatic Configuration

```python
from core.logger import setup_logging

setup_logging(
    log_level="DEBUG",           # Set to DEBUG for verbose logging
    log_file="logs/app.log",     # Custom log file path
    log_max_bytes=20971520,      # 20MB before rotation
    log_backup_count=10,         # Keep 10 backup files
    human_readable=True          # Use human-readable format
)
```

## Log Levels

- **DEBUG**: Detailed information for diagnosing problems
- **INFO**: General informational messages about application progress
- **WARNING**: Warning messages for potentially harmful situations
- **ERROR**: Error messages for serious problems
- **CRITICAL**: Critical messages for very serious errors

## Best Practices

1. **Use Structured Context**: Always include relevant context as keyword arguments

   ```python
   logger.info("Order placed", symbol="BTCUSD", quantity=0.5, price=45000)
   ```

2. **Use Appropriate Log Levels**: Choose the right level for your message

   - DEBUG: Detailed diagnostic information
   - INFO: Normal application flow
   - WARNING: Unexpected but recoverable situations
   - ERROR: Errors that need attention
   - CRITICAL: System-critical failures

3. **Log Exceptions Properly**: Use `logger.exception()` to capture full tracebacks

   ```python
   try:
       process_order()
   except Exception:
       logger.exception("Failed to process order", order_id=order_id)
   ```

4. **Use Descriptive Logger Names**: Use `__name__` to create hierarchical logger names

   ```python
   logger = get_logger(__name__)  # Creates logger with module path
   ```

5. **Avoid Logging Sensitive Data**: Never log passwords, API secrets, or personal data

   ```python
   # BAD
   logger.info("User login", password=password)

   # GOOD
   logger.info("User login", user_id=user_id)
   ```

## Log File Rotation

Log files automatically rotate when they reach the configured size limit:

- `trading.log` - Current log file
- `trading.log.1` - Most recent backup
- `trading.log.2` - Second most recent backup
- ... up to `LOG_BACKUP_COUNT` files

## Examples

### Trading Application Example

```python
from core.logger import LogManager, setup_logging

# Initialize logging
setup_logging(log_level="INFO", log_file="logs/trading.log")

# Create logger for trading module
log_mgr = LogManager("trading.executor")

# Log trade execution
log_mgr.log_operation(
    "Execute Trade",
    symbol="BTCUSD",
    side="BUY",
    quantity=0.5,
    price=45000
)

try:
    order = execute_trade(symbol="BTCUSD", side="BUY", quantity=0.5)
    log_mgr.log_success(
        "Execute Trade",
        order_id=order.id,
        filled_price=order.filled_price,
        status=order.status
    )
except Exception as e:
    log_mgr.log_failure(
        "Execute Trade",
        error=str(e),
        symbol="BTCUSD"
    )
```

### API Client Example

```python
from core.logger import get_logger

logger = get_logger(__name__)

def fetch_market_data(symbol: str):
    logger.info("Fetching market data", symbol=symbol)

    try:
        response = api_client.get_ticker(symbol)
        logger.debug("Market data received", symbol=symbol, data=response)
        return response
    except ConnectionError as e:
        logger.error("Connection failed", symbol=symbol, error=str(e))
        raise
    except Exception as e:
        logger.exception("Unexpected error fetching market data", symbol=symbol)
        raise
```

## Testing

Run the logger test script to verify functionality:

```bash
python3 core/logger.py
```

This will:

1. Test all log levels (DEBUG, INFO, WARNING, ERROR)
2. Test the LogManager class
3. Test exception logging
4. Create a test log file at `logs/test.log`

## Troubleshooting

### Logs not appearing in file

- Check that the log file path is writable
- Verify `LOG_LEVEL` is set appropriately
- Ensure `setup_logging()` is called before any logging

### Colors not showing in terminal

- Colors only appear when outputting to a TTY (terminal)
- Piping output or redirecting to a file will disable colors automatically

### Log files growing too large

- Adjust `LOG_MAX_BYTES` to a smaller value
- Reduce `LOG_BACKUP_COUNT` to keep fewer backup files
- Consider using a higher log level (INFO instead of DEBUG)
