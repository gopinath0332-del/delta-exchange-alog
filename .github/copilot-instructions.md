# Delta Exchange Trading Platform - AI Agent Instructions

## Project Overview

Python-based crypto trading analysis platform for Delta Exchange futures with backtesting, paper trading, and live trading capabilities. Built with modular architecture separating core infrastructure, API integration, data management, strategies, and trading engines.

**Status**: Foundation complete (v0.1.0). Core infrastructure operational; trading engines, strategies, and UI pending implementation.

## Architecture & Key Patterns

### Configuration Management (`core/config.py`)

- **Singleton pattern**: Use `get_config()` to access the global config instance—never instantiate `Config` directly
- **Hierarchical config**: Environment variables (`.env`) override YAML defaults (`settings.yaml`)
- **Pydantic validation**: All config sections use Pydantic models with strict validation
- Environment detection via `config.is_testnet()` / `config.is_production()`
- Access nested configs: `config.backtesting.initial_capital`, `config.risk_management.max_leverage`

### Logging (`core/logger.py`)

- **Structured logging with structlog**: Always use key-value pairs for context
- Get logger: `logger = get_logger(__name__)`
- Log pattern: `logger.info("Fetching data", symbol="BTCUSD", timeframe="1h", days=30)`
- Setup once in main: `setup_logging(log_level=config.log_level, log_file=config.log_file)`
- Logs auto-rotate at 10MB (configurable in `.env`)

### API Client (`api/rest_client.py`)

- **Wrapper over delta-rest-client**: All API calls go through `DeltaRestClient`
- **Built-in rate limiting**: 150 requests per 5 minutes enforced automatically via `RateLimiter`
- **Pagination handling**: `get_historical_candles()` auto-paginates (Delta limit: 2000 candles/request)
- Error hierarchy: `APIError` → `AuthenticationError`, `RateLimitError`
- Direct requests for missing endpoints: Use `_make_direct_request(endpoint, params)` pattern

### Data Models (`data/models.py`)

- **Pydantic v2**: All domain models validated with field constraints
- Key models: `OHLCCandle`, `Order`, `Position`, `Trade`, `Signal`
- Enums for constants: `OrderSide`, `OrderType`, `OrderStatus`, `TradingMode`
- Models auto-validate: `high >= low`, `prices > 0`, `volume >= 0`
- Computed properties: `Position.pnl`, `Order.remaining_quantity`, `Trade.net_value`

### Exception Handling (`core/exceptions.py`)

- Base: `DeltaExchangeError` for all custom exceptions
- API: `APIError`, `AuthenticationError`, `RateLimitError` (capture status code & response)
- Trading: `TradingError`, `InsufficientFundsError`, `InvalidOrderError` (capture order_id)
- Domain: `DataError`, `ValidationError`, `StrategyError`, `BacktestError`

## Critical Development Workflows

### Setting Up Environment

```bash
# 1. Create virtual environment (required)
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp config/.env.example config/.env
# Edit .env with Delta Exchange API keys from testnet.delta.exchange

# 4. Verify setup
python main.py fetch-data --symbol BTCUSD --timeframe 1h --days 1
```

### Running Commands

- **Fetch data**: `python main.py fetch-data --symbol BTCUSD --timeframe 1h --days 30`
- **Backtest**: `python main.py backtest --strategy moving_average --symbol BTCUSD` (not implemented)
- **Live trade**: `python main.py live --strategy rsi --symbol BTCUSD --paper` (not implemented)
- **GUI**: `python main.py --gui` (not implemented)

### Testing (when implemented)

- Run tests: `pytest`
- Coverage: `pytest --cov=core --cov=api --cov=data`
- Target: >80% coverage per TODO.md

## Project-Specific Conventions

### Code Quality & Linting

- **Zero linting errors**: All generated/updated code must be lint-free before completion
- **Type hints**: Use type hints for all function signatures (args and return types)
- **Docstrings**: Google-style docstrings for all public functions/classes
- **PEP 8 compliance**: Follow PEP 8 style guide (line length, spacing, imports)
- **Import organization**: Standard library → third-party → local (with blank lines between groups)
- **No unused imports/variables**: Clean up all unused code
- **Proper error handling**: Always use specific exception types, avoid bare `except:`

### File Organization

- **Flat module structure**: Each module (`core/`, `api/`, `data/`) is a package with `__init__.py`
- **No nested subpackages**: Avoid `api/endpoints/rest.py`—use `api/rest_client.py`
- **Examples in subdirs**: `strategies/examples/`, `tests/unit/`, `tests/integration/`

### Naming Conventions

- Classes: `PascalCase` (e.g., `DeltaRestClient`, `RateLimiter`)
- Functions/methods: `snake_case` (e.g., `get_historical_candles`, `wait_if_needed`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_HISTORICAL_DAYS`)
- Private methods: `_leading_underscore` (e.g., `_make_request`, `_load_settings`)

### Timeframe Conventions

- Supported: `5m`, `15m`, `1h`, `4h`, `1d` (defined in `settings.yaml`)
- Resolution parameter uses same format for Delta API
- Default: `1h` for most operations

### Delta Exchange Specifics

- **Testnet URL**: `https://cdn-ind.testnet.deltaex.org`
- **Production URL**: `https://api.india.delta.exchange`
- **Rate limits**: 150 connections per 5 minutes per IP
- **Fees**: Maker 0.04%, Taker 0.06%, Settlement 0.06%
- **Max candles**: 2000 per API request (pagination required)
- **Product ID**: Integer identifier for trading pairs (symbol alone insufficient)

## Implementation Patterns

### Code Quality Checklist

Before completing any code generation/modification:
1. ✓ Type hints on all parameters and return values
2. ✓ Complete docstrings with Args/Returns/Raises sections
3. ✓ No unused imports or variables
4. ✓ Proper exception handling (specific types)
5. ✓ Structured logging with key-value pairs
6. ✓ PEP 8 compliant (imports grouped, line length <100)
7. ✓ No linting errors or warnings

### Adding API Methods

```python
from typing import Any, Dict

def get_something(self, param: str) -> Dict[str, Any]:
    """
    Fetch something from the API.

    Args:
        param: Description of parameter

    Returns:
        Dictionary containing the result

    Raises:
        APIError: If the request fails
    """
    logger.debug("Fetching something", param=param)
    response = self._make_request(self.client.method_name, param)
    return response.get('result', {})
```

### Direct API Requests (for missing endpoints)

```python
params = {'resolution': resolution, 'symbol': symbol}
response = self._make_direct_request("/v2/history/candles", params=params)
candles = response.get('result', [])
```

### Creating New Data Models

```python
from datetime import datetime
from pydantic import BaseModel, Field

class NewModel(BaseModel):
    """
    Description of the model.

    Attributes:
        field: Description of field
        timestamp: When the data was recorded
    """
    field: float = Field(gt=0)  # Validation constraint
    timestamp: datetime

    @property
    def computed_value(self) -> float:
        """
        Calculate computed value from field.

        Returns:
            Double the field value
        """
        return self.field * 2

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
```

### Configuration Extension

Add to `settings.yaml` for domain configs, `.env` for secrets. Access via:
```python
from typing import Any
from core.config import get_config

config = get_config()
value: Any = config.settings.get("new_section", {}).get("key", default)
```

### Exception Handling Pattern

```python
from core.exceptions import APIError, RateLimitError
from core.logger import get_logger

logger = get_logger(__name__)

try:
    result = client.get_something()
except RateLimitError as e:
    logger.warning("Rate limit hit", error=str(e))
    # Handle rate limit
except APIError as e:
    logger.error("API error", error=str(e), status_code=e.status_code)
    raise
except Exception as e:
    logger.exception("Unexpected error", error=str(e))
    raise
```

## Active Development Areas (TODO.md Order)

1. **Data infrastructure** (HIGH): `data/storage.py` (SQLite + SQLAlchemy), `data/fetcher.py`, `data/preprocessor.py`
2. **WebSocket client** (HIGH): `api/websocket_client.py` for real-time feeds
3. **Strategy framework** (HIGH): `strategies/base.py` + `indicators.py` + examples using `ta` library
4. **Backtesting engine** (HIGH): Event-driven in `backtesting/engine.py` with portfolio/metrics
5. **Live trading** (MEDIUM): `trading/live_engine.py` with order/position/risk managers
6. **Notifications** (MEDIUM): Discord (`notifications/discord.py`) and Email (`notifications/email.py`)
7. **Reporting** (LOW): PDF generation with ReportLab + matplotlib charts
8. **Interfaces** (LOW): Terminal (rich/plotext) and GUI (dearpygui)

## Key Dependencies

- **delta-rest-client**: Official SDK for REST API (do not bypass for authenticated endpoints)
- **structlog**: Structured logging (always use key-value logging)
- **pydantic**: Data validation (v2.x with Field validators)
- **ta**: Technical indicators (preferred over pandas-ta)
- **sqlalchemy**: Database ORM (for `data/storage.py` when implementing)
- **dearpygui**: GUI framework (OpenGL-based, requires graphics support)

## Common Pitfalls

- **Don't instantiate Config**: Use `get_config()` singleton
- **Don't bypass rate limiting**: Always use `_make_request()` in `DeltaRestClient`
- **Don't mix timeframe formats**: Stick to `5m`, `1h`, `1d` (not `5min`, `1hour`)
- **Candle pagination**: Delta returns max 2000—implement pagination for >2000
- **Product ID required**: Many endpoints need product_id integer, not just symbol string
- **Testnet by default**: Ensure `.env` has `DELTA_ENVIRONMENT=testnet` to avoid production accidents

## Quick Reference

- **Config access**: `config = get_config()` → `config.backtesting.initial_capital`
- **Logging**: `logger.info("message", key=value, another_key=value2)`
- **API call**: `client = DeltaRestClient(config)` → `client.get_ticker("BTCUSD")`
- **Data model**: `candle = OHLCCandle(timestamp=..., open=..., high=..., ...)`
- **Error handling**: Catch specific exceptions (`APIError`, `RateLimitError`, etc.)
