# Migrating to LogManager

## Overview

This guide shows how to migrate existing code from using `get_logger()` to using the `LogManager` class for better operation tracking and cleaner code.

## Benefits of LogManager

1. **Operation Tracking**: Built-in methods for logging operation start, success, and failure
2. **Consistent Formatting**: Standardized log messages across the application
3. **Less Boilerplate**: Simpler API for common logging patterns
4. **Better Context**: Automatic status tracking for operations

## Migration Steps

### Step 1: Update Imports

**Before:**

```python
from core.logger import get_logger

logger = get_logger(__name__)
```

**After:**

```python
from core.logger import LogManager

log_mgr = LogManager(__name__)
```

### Step 2: Update Standard Log Calls

**Before:**

```python
logger.info("Fetching market data", symbol=symbol)
logger.error("Connection failed", error=str(e))
```

**After:**

```python
log_mgr.info("Fetching market data", symbol=symbol)
log_mgr.error("Connection failed", error=str(e))
```

### Step 3: Use Operation Methods

**Before:**

```python
logger.info("Placing order", symbol=symbol, quantity=quantity)
try:
    order = place_order(symbol, quantity)
    logger.info("Order placed successfully", order_id=order.id)
except Exception as e:
    logger.error("Order placement failed", error=str(e))
```

**After:**

```python
log_mgr.log_operation("Place Order", symbol=symbol, quantity=quantity)
try:
    order = place_order(symbol, quantity)
    log_mgr.log_success("Place Order", order_id=order.id)
except Exception as e:
    log_mgr.log_failure("Place Order", error=str(e))
```

## Example Migrations

### Example 1: API Client

**Before (`api/rest_client.py`):**

```python
from core.logger import get_logger

logger = get_logger(__name__)

class DeltaRestClient:
    def __init__(self, config):
        logger.info("Initializing REST client", base_url=config.base_url)
        self.config = config

    def get_ticker(self, symbol: str):
        logger.debug("Fetching ticker", symbol=symbol)
        try:
            response = self._make_request(f"/ticker/{symbol}")
            logger.debug("Ticker received", symbol=symbol, price=response['price'])
            return response
        except Exception as e:
            logger.error("Failed to fetch ticker", symbol=symbol, error=str(e))
            raise
```

**After:**

```python
from core.logger import LogManager

log_mgr = LogManager(__name__)

class DeltaRestClient:
    def __init__(self, config):
        log_mgr.info("Initializing REST client", base_url=config.base_url)
        self.config = config

    def get_ticker(self, symbol: str):
        log_mgr.log_operation("Fetch Ticker", symbol=symbol)
        try:
            response = self._make_request(f"/ticker/{symbol}")
            log_mgr.log_success("Fetch Ticker", symbol=symbol, price=response['price'])
            return response
        except Exception as e:
            log_mgr.log_failure("Fetch Ticker", error=str(e), symbol=symbol)
            raise
```

### Example 2: Trading Strategy

**Before:**

```python
from core.logger import get_logger

logger = get_logger(__name__)

class MomentumStrategy:
    def execute_trade(self, signal):
        logger.info("Executing trade", symbol=signal.symbol, side=signal.side)

        try:
            # Place order
            order = self.broker.place_order(
                symbol=signal.symbol,
                side=signal.side,
                quantity=signal.quantity
            )

            logger.info(
                "Trade executed successfully",
                order_id=order.id,
                filled_price=order.filled_price
            )

            return order

        except InsufficientFundsError as e:
            logger.error(
                "Insufficient funds for trade",
                symbol=signal.symbol,
                required=e.required,
                available=e.available
            )
            raise

        except Exception as e:
            logger.error("Trade execution failed", error=str(e))
            raise
```

**After:**

```python
from core.logger import LogManager

log_mgr = LogManager(__name__)

class MomentumStrategy:
    def execute_trade(self, signal):
        log_mgr.log_operation(
            "Execute Trade",
            symbol=signal.symbol,
            side=signal.side,
            quantity=signal.quantity
        )

        try:
            # Place order
            order = self.broker.place_order(
                symbol=signal.symbol,
                side=signal.side,
                quantity=signal.quantity
            )

            log_mgr.log_success(
                "Execute Trade",
                order_id=order.id,
                filled_price=order.filled_price,
                symbol=signal.symbol
            )

            return order

        except InsufficientFundsError as e:
            log_mgr.log_failure(
                "Execute Trade",
                error="Insufficient funds",
                symbol=signal.symbol,
                required=e.required,
                available=e.available
            )
            raise

        except Exception as e:
            log_mgr.log_failure(
                "Execute Trade",
                error=str(e),
                symbol=signal.symbol
            )
            raise
```

### Example 3: Data Fetcher

**Before:**

```python
from core.logger import get_logger

logger = get_logger(__name__)

def fetch_historical_data(symbol: str, days: int):
    logger.info("Fetching historical data", symbol=symbol, days=days)

    start_time = time.time()

    try:
        data = api_client.get_candles(symbol, days=days)

        duration = time.time() - start_time
        logger.info(
            "Historical data fetched",
            symbol=symbol,
            candles=len(data),
            duration_seconds=round(duration, 2)
        )

        return data

    except Exception as e:
        logger.error(
            "Failed to fetch historical data",
            symbol=symbol,
            error=str(e)
        )
        raise
```

**After:**

```python
from core.logger import LogManager

log_mgr = LogManager(__name__)

def fetch_historical_data(symbol: str, days: int):
    log_mgr.log_operation("Fetch Historical Data", symbol=symbol, days=days)

    start_time = time.time()

    try:
        data = api_client.get_candles(symbol, days=days)

        duration = time.time() - start_time
        log_mgr.log_success(
            "Fetch Historical Data",
            symbol=symbol,
            candles=len(data),
            duration_seconds=round(duration, 2)
        )

        return data

    except Exception as e:
        log_mgr.log_failure(
            "Fetch Historical Data",
            error=str(e),
            symbol=symbol
        )
        raise
```

## Migration Checklist

For each module:

- [ ] Update imports from `get_logger` to `LogManager`
- [ ] Rename `logger` variable to `log_mgr`
- [ ] Identify operations (functions/methods that perform actions)
- [ ] Replace operation logging with `log_operation()`, `log_success()`, `log_failure()`
- [ ] Keep standard logging (`info()`, `debug()`, `warning()`, `error()`) for non-operation logs
- [ ] Test the module to ensure logging works correctly

## Modules to Migrate

Priority order:

1. **High Priority** (core functionality):

   - [ ] `api/rest_client.py` - API client operations
   - [ ] `api/websocket_client.py` - WebSocket operations
   - [ ] `main.py` - Main application operations

2. **Medium Priority** (supporting functionality):

   - [ ] `api/rate_limiter.py` - Rate limiting operations
   - [ ] Strategy modules (if any)
   - [ ] Trading execution modules

3. **Low Priority** (configuration/utilities):
   - [ ] `core/config.py` - Configuration loading
   - [ ] Utility modules

## Best Practices

### 1. Use Operation Methods for Actions

Use `log_operation()`, `log_success()`, `log_failure()` for:

- API calls
- Database operations
- File I/O
- Network requests
- Trade execution
- Data processing

### 2. Use Standard Methods for State

Use `info()`, `debug()`, `warning()`, `error()` for:

- State changes
- Configuration loading
- Informational messages
- Warnings
- Errors that aren't part of an operation

### 3. Include Relevant Context

Always include context that helps debugging:

```python
# Good
log_mgr.log_failure("Place Order",
                     error=str(e),
                     symbol=symbol,
                     quantity=quantity,
                     price=price)

# Bad
log_mgr.log_failure("Place Order", error=str(e))
```

### 4. Use Consistent Operation Names

Use clear, action-oriented names:

- "Fetch Market Data" (not "Getting data")
- "Execute Trade" (not "Trading")
- "Connect to WebSocket" (not "Connecting")

## Testing After Migration

After migrating a module:

1. **Run the module** and check logs for proper formatting
2. **Trigger errors** to ensure `log_failure()` works correctly
3. **Check Discord alerts** (if enabled) for error notifications
4. **Verify log file** contains all expected information

## Gradual Migration

You don't need to migrate everything at once:

1. Start with high-priority modules
2. Migrate one module at a time
3. Test thoroughly after each migration
4. Both `get_logger()` and `LogManager` can coexist

## Need Help?

If you encounter issues during migration:

1. Check the [Log Manager Documentation](LOG_MANAGER.md)
2. Review the [examples](../examples/log_manager_examples.py)
3. Look at already-migrated modules for reference
