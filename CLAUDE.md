# CLAUDE.md — Delta Exchange Algo Trading Platform

Python 3.9+ algorithmic trading platform for Delta Exchange crypto futures. Supports backtesting, paper trading, and live trading with 8 strategies, Discord/email alerts, and Firestore trade journaling.

## Common Commands

```bash
# Run
python start.py                  # Interactive menu
python run_terminal.py           # Headless multi-symbol trading
python run_backtest.py           # Run backtests
python main.py live --strategy donchian-channel --symbol BTCUSD --paper

# Test
make test                        # pytest tests/ -v
make test-cov                    # With coverage (htmlcov/index.html)

# Code quality
make format                      # black + isort (line-length=100)
make lint                        # flake8 + bandit
make type-check                  # mypy
make pre-commit                  # All hooks
```

## Architecture

```
core/           # Config (singleton), logger (structlog), runner, trading execution, candle utils
api/            # DeltaRestClient wrapper with rate limiting (150 req/5min) and retry logic
strategies/     # 8 strategy implementations (donchian, rsi_200_ema, double_dip_rsi, etc.)
backtest/       # Engine, data loader, metrics (Sharpe/Sortino/drawdown), HTML reporter
data/           # Pydantic models (OHLCCandle, Order, Position), fetcher, storage
notifications/  # Discord webhooks + email SMTP alerts
reporting/      # PDF report generation
config/         # .env (secrets), settings.yaml (strategy params)
```

### Key Patterns

- **Closed candle logic**: Strategies only signal on confirmed candle closes via `get_closed_candle_index()` — prevents false signals from developing candles
- **Singleton config**: Always use `get_config()`, never instantiate `Config` directly
- **Structured logging**: `logger = get_logger(__name__)` then `logger.info("msg", key=value)`
- **Signal pipeline**: Strategy signal → `execute_strategy_signal()` → REST API order → Firestore journal → Discord/email alert
- **Thread-safe multi-symbol**: Shared `DeltaRestClient` with `RateLimiter` (threading.Lock); per-symbol threads use `cycle_lock`

### Strategy Interface

All strategies implement:
- `__init__()` — load config from `settings.yaml`
- `_update_bars_per_day(timeframe)` — dynamic timeframe handling
- `check_signals(df, current_time_ms)` → `(action, reason)` where action is `ENTRY_LONG`, `EXIT_LONG`, `PARTIAL_EXIT`, etc.
- `update_position_state(action, ...)` — track position, entry price, TP/SL levels
- `run_backtest(df)` — iterate historical data, return trade list
- `reconcile_position(...)` — sync internal state with exchange

## Configuration

**Hierarchy**: Environment variables (.env) override YAML defaults (settings.yaml).

- `config/.env` — API keys, per-symbol leverage/margin (`LEVERAGE_BTC=5`, `TARGET_MARGIN_BTC=40`), `ENABLE_ORDER_PLACEMENT_*`, Discord/email config
- `config/settings.yaml` — strategy parameters, timeframes, multi-coin definitions, backtest settings
- Access: `config = get_config()` then `config.settings.get("strategies", {}).get("donchian_channel", {})`

## Coding Conventions

- **Formatting**: Black + isort, line length 100
- **Naming**: PascalCase classes, snake_case functions, UPPER_SNAKE_CASE constants, `_leading_underscore` private
- **Imports**: stdlib → third-party → local, blank lines between groups
- **Type hints**: On all function signatures
- **Docstrings**: Google-style with Args/Returns/Raises
- **Error handling**: Use custom exceptions from `core/exceptions.py` (`APIError`, `TradingError`, `StrategyError`, etc.) — never bare `except:`
- **Logging**: Always structured with key-value pairs: `logger.error("msg", symbol="BTC", status=500)`

## Gotchas

- **Rate limits**: Delta allows 150 req/5min — all calls must go through `DeltaRestClient` which enforces this
- **Product IDs**: Many API endpoints need integer `product_id`, not just symbol string
- **Candle pagination**: Delta returns max 2000 candles/request — `get_historical_candles()` auto-paginates
- **Testnet default**: Ensure `DELTA_ENVIRONMENT=testnet` in `.env` to avoid production accidents
- **Timeframe format**: Use `5m`, `15m`, `1h`, `4h`, `1d` — not `5min` or `1hour`
- **Partial TP**: Position sizes round to even numbers when `enable_partial_tp=true` (for 50% splits)
- **Order safety**: `ENABLE_ORDER_PLACEMENT_{SYMBOL}=false` by default — must explicitly enable per symbol
