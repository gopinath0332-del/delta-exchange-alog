---
trigger: always_on
---

# Delta Exchange Algo Trading Bot — Agent Rules

## 1. Configuration (Always Check First)

- **ALL** application configuration lives in `config/.env` (secrets, API keys, flags) and `config/settings.yaml` (YAML structured settings like strategies, Firestore, backtesting, risk management, GUI).
- Never hardcode API keys, credentials, webhook URLs, leverage, or order sizes. Always read from `.env`.
- Environments: `DELTA_ENVIRONMENT=testnet` → debug logs, testnet API. `DELTA_ENVIRONMENT=production` → INFO logs, live API.
- Symbol-specific overrides follow the pattern `LEVERAGE_{BASE_ASSET}`, `TARGET_MARGIN_{BASE_ASSET}`, `ENABLE_ORDER_PLACEMENT_{BASE_ASSET}` (e.g., `LEVERAGE_BTC`, `ENABLE_ORDER_PLACEMENT_RIVER`).
- `ENABLE_ORDER_PLACEMENT_{BASE_ASSET}=false` disables live order placement for that coin while keeping alerts active.
- Error alerting uses **two separate Discord webhooks**: `DISCORD_WEBHOOK_URL` (trade alerts) and `DISCORD_ERROR_WEBHOOK_URL` (ERROR/CRITICAL level logs only). Never mix these up.

---

## 2. Project Structure

```
delta-exchange-alog/
├── api/                  # Exchange API clients
│   ├── rest_client.py    # Main REST API wrapper (DeltaRestClient)
│   ├── rate_limiter.py   # Rate limiting (150 req / 5 min)
│   └── websocket_client.py
├── core/                 # Core application logic
│   ├── config.py         # Config class (reads .env + settings.yaml) — single global instance via get_config()
│   ├── runner.py         # Strategy execution loop (run_strategy_terminal)
│   ├── trading.py        # Order execution & journaling (execute_strategy_signal, get_trade_config, calculate_position_size)
│   ├── logger.py         # Logging setup (setup_logging, get_logger)
│   ├── error_alerts.py   # ErrorAlertHandler — Discord alerts for ERROR/CRITICAL log events
│   ├── exceptions.py     # Custom exception hierarchy
│   ├── firestore_client.py # Trade journaling to Firestore (journal_trade)
│   ├── candle_aggregator.py # 1h→3h candle aggregation
│   └── candle_utils.py
├── strategies/           # Strategy implementations
│   ├── donchian_strategy.py
│   ├── ema_cross_strategy.py
│   ├── cci_ema_strategy.py
│   ├── rsi_50_ema_strategy.py
│   ├── rsi_200_ema_strategy.py
│   ├── rsi_supertrend_strategy.py
│   ├── double_dip_rsi.py
│   └── macd_psar_100ema_strategy.py
├── notifications/        # Notification subsystem
│   ├── manager.py        # NotificationManager (Discord + Email)
│   ├── discord.py        # DiscordNotifier
│   └── email.py          # EmailNotifier
├── service/              # Systemd service files (one per bot instance)
├── scripts/              # Utility scripts
├── pine/                 # PineScript source files
├── tests/                # Pytest tests
├── docs/                 # Architecture & feature documentation
└── config/
    ├── .env              # Environment secrets (DO NOT COMMIT)
    └── settings.yaml     # App settings (strategies, Firestore, backtesting etc.)
```

---

## 3. Strategy Rules

### Adding a New Strategy

1. Create `strategies/<name>_strategy.py` with a class implementing:
   - `check_signals(df, current_time_ms, **kwargs) -> (action, reason)` – returns action string or None.
   - `update_position_state(action, current_time_ms, indicators, exec_price, reason)` – updates internal state.
   - `run_backtest(df)` – warmup historical backtest on startup.
   - `reconcile_position(size, entry_price)` – syncs strategy state with live exchange position.
   - `indicator_label` attribute (e.g. `"RSI"`, `"CCI"`, `"Upper/Lower"`) for dashboard display.
   - `enable_partial_tp` boolean attribute.
2. Register the strategy in `core/runner.py` `run_strategy_terminal()` under the strategy name mapping (if/elif block, lines ~58–100).
3. Add strategy config to `config/settings.yaml` under `strategies:`.
4. Create a systemd service file in `service/delta-bot-<name>.service` copying an existing template.
5. Update `README.md` with the new strategy, its parameters, and how to run it.

### Candle Types

- Strategies can use **Heikin Ashi** or **Standard** candles; controlled by `candle_type` parameter in `run_strategy_terminal()`.
- Heikin Ashi transformation is applied in `core/runner.py` (lines ~270–310). **Do NOT report HA prices as market prices.** Always capture `market_price = float(df['close'].iloc[-1])` from raw candles before the HA transform and pass it separately to alerts.
- 3-hour candles are synthesized by fetching 1h candles and calling `aggregate_candles_to_3h()` from `core/candle_aggregator.py`.

### Signal Action Names (Must Match Exactly)

These are the valid action strings returned by strategies and handled by `execute_strategy_signal()`:

- `ENTRY_LONG` – Open a long position
- `ENTRY_SHORT` – Open a short position
- `EXIT_LONG` – Close long position fully
- `EXIT_SHORT` – Close short position fully
- `EXIT_LONG_PARTIAL` / `EXIT_SHORT_PARTIAL` – Close 50% of a directional position
- `PARTIAL_EXIT` – Close 50% of current position (direction determined from live exchange position)

Never invent new action names without registering them in `core/trading.py` `execute_strategy_signal()`.

### Position Sizing (Dynamic)

- All entries use **dynamic position sizing** via `calculate_position_size()` in `core/trading.py`.
- Formula: `(TARGET_MARGIN_{ASSET} * LEVERAGE_{ASSET}) / (current_price * contract_value)`
- If `enable_partial_tp=True`, the size is rounded to an even number (minimum 2 contracts).
- Partial exits close exactly 50% of the current live position fetched from the exchange at the time of exit.

---

## 4. API Client Rules

### DeltaRestClient (`api/rest_client.py`)

- Use `client.get_products()` → calls `/v2/products` (public). Resolves symbol → product_id.
- Use `client.get_positions(product_id=pid)` → calls `/v2/positions/margined` (authenticated).
- Use `client.place_order(product_id, size, side, order_type="market_order")` for all live orders.
- Use `client._make_direct_request(endpoint, params)` only for public endpoints not wrapped by `delta-rest-client` (e.g. `/v2/history/candles`, `/v2/products`).
- Use `client._make_auth_request(method, endpoint, params, data)` for authenticated endpoints not in the library.

### Retry / Backoff

- `_make_direct_request()` applies exponential backoff for HTTP 400, 429, 500, 502, 503, 504.
- Retry settings come from `.env`: `API_MAX_RETRIES` (default 4), `API_BACKOFF_BASE_SEC` (default 2), `API_BACKOFF_MAX_SEC` (default 60).
- HTTP 400 from `/v2/products` usually indicates **exchange overload**, not a code bug. The bot will retry then raise `APIError`.
- On receiving an `APIError` in the strategy loop, the runner backs off for **5 minutes** (`time.sleep(300)`) if the message contains "retries" or "400".

### Rate Limiter

- Global rate limit: **150 requests per 5-minute window** (enforced via `RateLimiter` in `api/rate_limiter.py`).
- Do not bypass the rate limiter. Always call API methods via `_make_request()`, `_make_direct_request()`, or `_make_auth_request()`.

---

## 5. Notifications Rules

### Discord

- **Trade alerts** → `notifier.send_trade_alert(...)` → goes to `DISCORD_WEBHOOK_URL`.
- **Error/Critical alerts** → logged at ERROR/CRITICAL level → `ErrorAlertHandler` sends to `DISCORD_ERROR_WEBHOOK_URL` automatically.
- **Status messages** (bot start/stop) → `notifier.send_status_message(...)` → goes to `DISCORD_WEBHOOK_URL`.
- **Manual errors** (e.g. order failures) → `notifier.send_error(...)` → goes to `DISCORD_ERROR_WEBHOOK_URL`.
- Alert throttling: ERROR alerts deduplicate within **300 seconds** per error key. Each process has its own handler (no cross-process dedup).

### Email

- Email notifications use Gmail SMTP via `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_RECIPIENTS` from `.env`.

---

## 6. Logging Rules

- Always get a per-module logger: `logger = get_logger(__name__)` at the top of every Python file.
- Never use `print()` for application messages in production code (only for dashboard output in `runner.py`).
- Log levels: `DEBUG` for detailed trace, `INFO` for lifecycle events, `WARNING` for recoverable issues / external transient failures, `ERROR` for actionable failures, `CRITICAL` for fatal issues.
- Any `logger.error()` or `logger.critical()` call will **automatically trigger a Discord alert** to `DISCORD_ERROR_WEBHOOK_URL` (via `ErrorAlertHandler` added in `core/logger.py`).
- Log files: rotating at `LOG_MAX_BYTES` (default 500MB) with `LOG_BACKUP_COUNT` backups.

---

## 7. Trade Journaling (Firestore)

- All trades are journaled to Firestore via `journal_trade()` in `core/firestore_client.py`.
- Called automatically inside `execute_strategy_signal()` after order placement and notification.
- Config: `firestore.enabled`, `firestore.service_account_path`, `firestore.collection_name` in `settings.yaml`.
- Service account JSON path: `config/firestore-service-account.json` (default, relative to project root).
- Each entry generates a `trade_id` = `{symbol}_{strategy}_{timestamp}_{uuid}`. Exits attempt to reuse the same ID to link entry ↔ exit, but this is best-effort (fallback creates a new one).
- Journaling failures do **not** abort trade execution — they are logged as errors only.
- Computed fields stored: `days_held`, `pnl_percentage`, `entry_price`, `exit_price`, `execution_price`, `pnl`, `funding_charges`, `trading_fees`, `margin_used`.

---

## 8. Exception Hierarchy

All custom exceptions are in `core/exceptions.py`:

```
DeltaExchangeError
├── APIError            — General API failures (wraps requests errors)
│   ├── AuthenticationError — 401 Unauthorized
│   └── RateLimitError      — 429 Rate limit
├── DataError           — Data fetch/parse issues
├── ValidationError     — Config or input validation failures
├── TradingError        — Order placement issues
│   ├── InsufficientFundsError
│   └── InvalidOrderError
├── StrategyError       — Strategy logic failures
└── BacktestError       — Backtesting errors
```

- Always raise the most specific exception.
- Wrap `requests` errors in `APIError` (already done inside REST client methods).

---

## 9. Deployment (Systemd Service)

- Each bot instance runs as a separate systemd service in `service/delta-bot-<name>.service`.
- All services run `start.py` or `run_terminal.py` with symbol and strategy arguments.
- To add a new bot:
  1. Create `service/delta-bot-<name>.service` based on an existing template.
  2. Add `.env` symbol-specific settings (`LEVERAGE_<ASSET>`, `TARGET_MARGIN_<ASSET>`, `ENABLE_ORDER_PLACEMENT_<ASSET>`).
  3. Register strategy name in `core/runner.py`.
  4. Deploy via: `sudo systemctl enable delta-bot-<name>` and `sudo systemctl start delta-bot-<name>`.
- Each process has an **independent** `ErrorAlertHandler` — error throttling is per-process.

---

## 10. Code & Documentation Standards

- **Always add detailed comments** wherever logic is non-obvious. This is mandatory for all new code.
- **Always update `README.md`** when adding a feature, strategy, configuration key, or changing an existing behavior.
- **Always update the relevant `docs/*.md`** file when changing documented behavior (e.g. `docs/ERROR_ALERTING.md`, `docs/LOG_MANAGER.md`).
- Use type annotations for all function signatures.
- Use `Optional[X]` for nullable parameters, not `X | None` (for Python 3.9 compatibility).
- Imports: stdlib → third-party → local (separated by blank lines).
- Tests live in `tests/`; run with `pytest` (config in `pyproject.toml`). Write tests for any new utility functions.
- Lint: `ruff` / `mypy` configured in `pyproject.toml`. Run `make lint` before finalizing changes.

---

## 11. Common Gotchas & Anti-Patterns

| ❌ Anti-Pattern                                               | ✅ Correct Approach                                                                           |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Use HA candle close as market price in alerts                 | Capture `market_price` from raw `df['close']` before HA transform                             |
| Return action string directly without matching exec handler   | Ensure action is registered in `execute_strategy_signal()`                                    |
| Hardcode order size                                           | Use `calculate_position_size()` with `TARGET_MARGIN_{ASSET}`                                  |
| Send ERROR logs to trade webhook                              | Use `DISCORD_ERROR_WEBHOOK_URL` for errors, `DISCORD_WEBHOOK_URL` for trades                  |
| Call `client.get_products()` per loop iteration unnecessarily | Cache product list; re-fetch only when needed                                                 |
| Exit more contracts than position size after partial exits    | Always fetch live position size before placing exit orders                                    |
| `logger.info()` inside `except` for real failures             | Use `logger.error()` or `logger.warning()` appropriately                                      |
| Modify `.env` keys without updating `core/config.py`          | Always add new `.env` keys to the corresponding `_init_*_config()` method in `core/config.py` |
| Create a new strategy without a systemd service file          | Always create a matching `service/delta-bot-<name>.service`                                   |
