# Delta Exchange Crypto Trading Analysis Platform

A comprehensive Python-based crypto trading analysis platform with Delta Exchange futures API integration, supporting backtesting, paper trading, and live trading with a terminal interface.

## Features

- **Multiple Trading Modes**: Backtesting, Paper Trading, and Live Trading
- **Delta Exchange Integration**: Official `delta-rest-client` library with rate limiting
- **Closed Candle Logic**: Standardized signal generation on confirmed candle closes (eliminates backtest vs. live discrepancies)
- **Firestore Trade Journaling**: Comprehensive trade tracking with auto-calculated analytics (PnL %, days held, status tracking)
- **Structured Logging**: Human-readable logs using `structlog`
- **Modular Architecture**: Clean separation of concerns for easy extension
- **Multiple Timeframes**: 5m, 15m, 1h, 3h, 4h, 1d (configurable)
- **Strategy State Persistence**: Local JSON-based state storage to preserve trade flags (milestones, partial exits) across restarts (NEW)
- **Notifications**: Discord webhooks and Email alerts with color-coded status messages
- **PDF Reports**: Professional trading reports with charts
- **Premium Strategies**: Multiple strategies with ATR-based trailing stops and partial exits
  - Double-Dip RSI (BTCUSD) - Long/Short with RSI levels
  - CCI-EMA (BTCUSD) - CCI crossover with 50 EMA filter
  - RSI-50-EMA (XRPUSD) - RSI + EMA confirmation
  - MACD-PSAR-100EMA (XRPUSD) - MACD histogram with PSAR filter
  - RSI-200-EMA (ETHUSD) - RSI crossover with 200 EMA trend filter
  - RSI-Supertrend (RIVERUSD) - RSI crossover with Supertrend exit
  - Donchian Channel (RIVERUSD, PIPPINUSD) - Breakout strategy with 100 EMA trend filter and ATR trailing stop
  - **Donchian Channel (BIOUSD)** - 4H Standard, 5x leverage, $50 target margin
  - **Donchian Channel (BERAUSD)** - 1H Heikin Ashi, 5x leverage, $50 target margin
  - **Donchian Channel (PAXGUSD)** - 1H Heikin Ashi, 5x leverage, $30 target margin (NEW)
  - **EMA Cross (BTCUSD)** - 10/20 EMA crossover with position flipping
- **Dynamic Configuration**: Asset-specific order sizing and leverage via env vars
- **Terminal Interface**: Robust CLI dashboard with live strategy monitoring and position tracking

## Project Structure

```
delta-exchange-alog/
├── config/              # Configuration files
│   ├── .env.example    # Environment variables template
│   └── settings.yaml   # Trading parameters and strategy configs
├── core/               # Core infrastructure
│   ├── config.py       # Configuration management
│   ├── logger.py       # Structured logging
│   ├── runner.py       # Strategy execution engine
│   ├── trading.py      # Order execution and trade management
│   ├── firestore_client.py # Firestore trade journaling (NEW)
│   ├── candle_utils.py # Closed candle detection utilities
│   ├── candle_aggregator.py # Multi-timeframe candle aggregation
│   └── exceptions.py   # Custom exceptions
├── api/                # Delta Exchange API integration
│   ├── rest_client.py  # REST API wrapper
│   ├── websocket_client.py  # WebSocket client
│   └── rate_limiter.py # Rate limiting
├── data/               # Data management
│   ├── models.py       # Pydantic data models
│   ├── fetcher.py      # Historical data fetcher
│   ├── storage.py      # Data persistence
│   ├── preprocessor.py # Data processing
│   └── state/          # Persistent strategy state (JSON) - NEW
├── strategies/         # Trading strategies (all use closed candle logic)
│   ├── double_dip_rsi.py      # Double-Dip RSI strategy (BTCUSD)
│   ├── cci_ema_strategy.py    # CCI + 50 EMA strategy (BTCUSD)
│   ├── rsi_50_ema_strategy.py # RSI + 50 EMA strategy (XRPUSD)
│   ├── macd_psar_100ema_strategy.py # MACD + PSAR + 100 EMA (XRPUSD)
│   ├── rsi_200_ema_strategy.py # RSI + 200 EMA strategy (ETHUSD)
│   ├── rsi_supertrend_strategy.py # RSI + Supertrend strategy (RIVERUSD)
│   ├── donchian_strategy.py   # Donchian Channel strategy (RIVERUSD, PIPPINUSD, BIOUSD, BERAUSD)
│   ├── ema_cross_strategy.py  # EMA Cross strategy (BTCUSD) - NEW
│   └── examples/       # Example strategies
├── backtesting/        # Backtesting engine
├── trading/            # Live trading engine
├── notifications/      # Alert system
│   ├── manager.py      # Notification orchestration
│   └── discord.py      # Discord webhook integration
├── reporting/          # PDF report generation
├── terminal/           # Terminal interface
├── service/            # Systemd service files for deployment
└── tests/              # Unit and integration tests
```

## Installation

### Prerequisites

- Python 3.9 or higher
- Delta Exchange account (testnet or production)

### Setup

1. **Clone the repository**:

   ```bash
   cd /Users/admin/Projects/delta-exchange-alog
   ```

2. **Create virtual environment**:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   # or
   venv\\Scripts\\activate  # On Windows
   ```

3. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:

   ```bash
   cp config/.env.example config/.env
   # Edit config/.env with your API credentials
   ```

5. **Get API credentials**:
   - Testnet: https://testnet.delta.exchange/app/account/manageapikeys
   - Production: https://www.delta.exchange/app/account/manageapikeys

## Configuration

### Environment Variables (.env)

```env
# Delta Exchange API
DELTA_API_KEY=your_api_key_here
DELTA_API_SECRET=your_api_secret_here
DELTA_ENVIRONMENT=testnet  # or production
DELTA_BASE_URL=https://cdn-ind.testnet.deltaex.org

# Trading Configuration
ENABLE_ORDER_PLACEMENT=false # Set to true to enable real order placement
DEFAULT_HISTORICAL_DAYS=30   # Days of data to load for analysis

# Discord Notifications
DISCORD_WEBHOOK_URL=your_webhook_url
DISCORD_ENABLED=true

# Email Notifications
EMAIL_ENABLED=true
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
EMAIL_RECIPIENTS=recipient@example.com

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# API Retry / Backoff (exchange overload protection)
# When busy, retries: 2s → 4s → 8s → 16s (+ jitter)
API_MAX_RETRIES=4
API_BACKOFF_BASE_SEC=2
API_BACKOFF_MAX_SEC=60

# Symbol Specific Order Settings
# Dynamic Position Sizing (Recommended)
TARGET_MARGIN_XRP=40  # Target margin in USD for position sizing (default: 40)
TARGET_MARGIN_BTC=40
LEVERAGE_XRP=5
LEVERAGE_BTC=5

# Legacy Order Size Configuration (Deprecated for entry orders)
# ORDER_SIZE is still read for backwards compatibility but not used for entry orders
# Position sizes are now calculated dynamically based on TARGET_MARGIN
# ORDER_SIZE_XRP=10  # Deprecated: Use TARGET_MARGIN_XRP instead
# ORDER_SIZE_BTC=1   # Deprecated: Use TARGET_MARGIN_BTC instead

# Firestore Trade Journaling (optional)
# See Firebase Admin SDK setup below
FIREBASE_PROJECT_ID=crypto-journal-b2298
```

### Dynamic Position Sizing

The platform now uses **dynamic position sizing** based on target margin allocation instead of fixed order sizes.

**How it works:**

- Position size is calculated as: `(TARGET_MARGIN * leverage) / (price * contract_value)`
- When partial take-profit is enabled, position size is rounded to the nearest even number
- This ensures consistent margin usage across different price levels
- Notifications display the calculated lot size for transparency

**Configuration:**

```env
# Set target margin per asset (in USD)
TARGET_MARGIN_BTC=40   # Use $40 margin for BTC positions
TARGET_MARGIN_XRP=50   # Use $50 margin for XRP positions
LEVERAGE_BTC=5         # 5x leverage
```

**Example Calculation:**

```
Price: $100,000
Leverage: 5x
Target Margin: $40
Contract Value: 0.001 BTC

Position Size = (40 * 5) / (100000 * 0.001) = 200 / 100 = 2 contracts
```

**Benefits:**

- ✅ Consistent risk management across price movements
- ✅ Automatic adjustment for different asset prices
- ✅ Even number handling for clean partial exits
- ✅ Configurable per asset
- ✅ **Target margin is shown in trade alerts (Discord + Email)** so you immediately see the capital allocation used at entry
- ✅ **Target margin is shown in startup messages** so you can verify the correct margin is loaded when a service starts

> [!NOTE]
> The old `ORDER_SIZE_{ASSET}` configuration is deprecated for entry orders but still supported for backwards compatibility. It is recommended to migrate to `TARGET_MARGIN_{ASSET}` for better risk management.

### Volatility-Based Position Sizing (ATR)

The platform supports **volatility-based position sizing** using the Average True Range (ATR). This allows the bot to adjust the number of contracts based on market volatility, keeping the risk (dollar loss per unit of volatility move) constant.

**How it works:**

- When enabled, position size is calculated as: `TARGET_MARGIN / (ATR * ATR_MULTIPLIER * contract_value)`
- This allocates `TARGET_MARGIN` of capital for every `(ATR * ATR_MULTIPLIER)` move in price.
- If volatility (ATR) is high, the position size decreases. If volatility is low, the position size increases.

**Configuration:**

You can set global defaults in `config/settings.yaml`:

```yaml
risk_management:
  position_sizing_type: "margin" # Default sizing method: "margin" or "atr"
  atr_margin_multiplier: 2.0 # Multiplier for ATR unit
```

**Symbol-Specific Overrides:**

- **Capital & Sizing**: `leverage`, `target_margin`, `position_sizing_type`, `atr_margin_multiplier`, and `atr_margin_cap_multiplier` are all managed within the `multi_coin` section of `config/settings.yaml`.
- **Precedence**: Settings in `settings.yaml` take precedence over environment variables in `.env`. If a symbol is defined in `multi_coin`, the bot will ignore its corresponding `.env` keys (like `TARGET_MARGIN_BTC`).

Example `config/settings.yaml`:

```yaml
multi_coin:
  donchian_channel:
    symbols:
      - symbol: SLVONUSD
        leverage: 5
        target_margin: 50
        position_sizing_type: "atr"
        atr_margin_multiplier: 2.0
        atr_margin_cap_multiplier: 1.5 # Optional: Defaults to 1.5 if omitted
```

**ATR Safety Cap:**

To prevent excessive risk in low-volatility (flat) markets, the bot enforces a **Safety Cap**.
- **Default Multiplier**: 1.5x
- **Logic**: The actual margin used for a trade will never exceed `target_margin * atr_margin_cap_multiplier`.
- **Example**: If your target margin is $50 and the cap is 1.5x, the bot will never use more than $75 of collateral, even if the ATR formula suggests a much larger position.

Example `config/.env` (Fallback only):

```env
# Only used if missing from settings.yaml
TARGET_MARGIN_SLVON=30
LEVERAGE_SLVON=10
```

> [!TIP]
> Environment variables (e.g., `POSITION_SIZING_TYPE_PIPPIN`) are still supported for backward compatibility but using `settings.yaml` is recommended for centralizing configuration.

**Benefits:**

- ✅ **Constant Risk Units**: Normalize risk across various market conditions.
- ✅ **Volatility Aware**: Automatically scales down in high-volatility environments.
- ✅ **Coin-Specific Flags**: Enable it only for the coins you want.
- ✅ **Consistent with TradingView**: Mimics advanced Pine Script risk management strategies.

---

````

### Notifications

All alerts are sent to **Discord** (via webhook embeds with ANSI colour codes) and **Email** (HTML).

#### Trade Alert (Entry Signal)

Displayed whenever a new position is opened:

| Field | Description |
|---|---|
| Strategy | Strategy name |
| Price | Execution / fill price |
| Market Price | Raw candlestick LTP (shown if different from signal price, e.g. Heikin Ashi) |
| RSI | RSI value at signal time |
| **Stop Loss** | Hard stop loss price (for entry signals) |
| Lot Size | Number of contracts placed |
| **Target Margin** | Configured `TARGET_MARGIN_{ASSET}` from `.env` — shows the capital allocation for this trade |
| Reason | Signal trigger description |
| Margin Used | Estimated USD margin consumed by the order |
| Remaining Wallet | Available balance after the trade |

#### Trade Alert (Exit / Partial Exit Signal)

Displayed whenever a position is closed or partially exited. All entry fields above are shown **except** Target Margin and Lot Size. Additional exit-only fields:

| Field | Description |
|---|---|
| P&L | Realised profit / loss (green if positive, red if negative) |
| Funding | Funding fees paid / received |
| Fees | Exchange trading commission |
| Remaining Wallet | Available balance after the exit |

#### Startup Message (Service Start)

Sent to Discord when any bot service starts. Lets you verify the configuration loaded correctly:

| Field | Description |
|---|---|
| Host | Hostname of the machine running the service |
| Candle Type | `Heikin Ashi` or `Standard` |
| Order Placement | `ENABLED` (green) or `DISABLED` (red) |
| Order Size | Legacy order size (deprecated) |
| Leverage | Leverage multiplier |
| **Target Margin** | Configured `TARGET_MARGIN_{ASSET}` from `.env` — confirms the capital allocation at startup |
| Wallet Balance | Current available balance at launch |

### API Resilience: Exponential Backoff

When **Delta Exchange is busy or overloaded** (HTTP 400/429/5xx), the bot automatically retries with exponential backoff instead of immediately raising an error every second.

**How it works:**

| Retry | Wait (approx) |
|-------|----------------|
| 1st   | 2s + jitter    |
| 2nd   | 4s + jitter    |
| 3rd   | 8s + jitter    |
| 4th   | 16s + jitter   |
| Give up → 5 min cooldown |   |

- **Jitter**: up to +1s random added to each wait (prevents thundering-herd when many strategies retry together)
- **Non-retryable**: HTTP 401 (auth errors) are raised immediately — no retry
- **After all retries**: the strategy loop backs off 5 minutes before the next full cycle

**Configuration** (in `config/.env`):

```env
API_MAX_RETRIES=4        # Number of retry attempts
API_BACKOFF_BASE_SEC=2   # Initial wait in seconds
API_BACKOFF_MAX_SEC=60   # Maximum single wait cap
```

> [!TIP]
> If you want faster recovery on a stable connection, set `API_MAX_RETRIES=2` and `API_BACKOFF_BASE_SEC=1`.
> For more patience during sustained outages, try `API_BACKOFF_MAX_SEC=120`.

### Firestore Trade Journaling (Optional)

All trades are automatically journaled to Google Cloud Firestore for historical analysis and performance tracking.

#### Setup

1. **Firebase Console**:
   - Go to [Firebase Console](https://console.firebase.google.com/)
   - Select your project (or create a new one)
   - Navigate to **Project Settings** → **Service Accounts**
   - Click **"Generate New Private Key"** → Download the JSON file
   - Save it to `config/[your-service-account-file].json`

2. **Configuration** (`config/settings.yaml`):

```yaml
firestore:
  enabled: true # Enable/disable trade journaling
  service_account_path: "config/your-firebase-adminsdk-file.json"
  collection_name: "trades" # Firestore collection name
````

3. **Install Firebase Admin SDK**:

```bash
pip install firebase-admin
```

#### Trade Data Model

**Single-Document Per Trade**: Each trade is represented by ONE document that evolves through its lifecycle (entry → exit), not separate documents for entry and exit.

**Document ID**: Uses `trade_id` (format: `{symbol}_{strategy}_{timestamp}_{uuid}`)

**Status Lifecycle**:

- `OPEN`: Trade entered, position is open
- `PARTIAL_CLOSED`: Partial exit executed
- `CLOSED`: Trade fully closed

#### Complete Trade Document Schema

```javascript
{
  // Document ID = trade_id
  "trade_id": "BTCUSD_Double Dip RSI_20260131073858_be807a48",
  "status": "CLOSED",  // OPEN → PARTIAL_CLOSED → CLOSED

  // Core Information
  "symbol": "BTCUSD",
  "strategy_name": "Double Dip RSI",
  "mode": "live",  // or "paper"
  "product_id": 1,
  "order_size": 2,
  "leverage": 5,

  // Entry Data (created on entry)
  "entry_timestamp": Timestamp(2026, 1, 31, 7, 38, 59),
  "entry_action": "ENTRY_LONG",
  "entry_side": "buy",
  "entry_price": 95500.00,
  "entry_execution_price": 95508.50,
  "entry_rsi": 56.80,
  "entry_reason": "RSI crossover above 50",
  "entry_order_id": "ORD123",
  "margin_used": 38200.00,

  // Exit Data (populated on exit)
  "exit_timestamp": Timestamp(2026, 1, 31, 8, 15, 23),
  "exit_action": "EXIT_LONG",
  "exit_side": "sell",
  "exit_price": 97800.00,
  "exit_execution_price": 97792.25,
  "exit_rsi": 41.20,
  "exit_reason": "Profit target hit",
  "exit_order_id": "ORD124",

  // Financial Metrics
  "pnl": 4584.50,
  "pnl_percentage": 50.00,  // Auto-calculated: ((exit-entry)/entry * 100) * leverage
  "funding_charges": -15.75,
  "trading_fees": 28.90,
  "remaining_margin": 16339.85,

  // Analytics (Auto-calculated)
  "days_held": 0.46  // Auto-calculated: (exit_timestamp - entry_timestamp) in days
}
```

**Key Features**:

- ✅ **One Document Per Trade**: Clean data model without duplicates
- ✅ **Auto-Calculated Fields**: `pnl_percentage` and `days_held` automatically computed
- ✅ **Status Tracking**: Easy filtering by OPEN/CLOSED trades
- ✅ **Complete Trade Journey**: All entry and exit data in one place

#### Querying Your Trades

**Get All Open Positions**:

```javascript
db.collection("trades")
  .where("status", "==", "OPEN")
  .where("mode", "==", "live")
  .get();
```

**Calculate Total PnL**:

```javascript
db.collection("trades")
  .where("status", "==", "CLOSED")
  .where("mode", "==", "live")
  .get()
  .then((snapshot) => {
    let totalPnL = 0;
    snapshot.forEach((doc) => (totalPnL += doc.data().pnl || 0));
    console.log("Total PnL:", totalPnL);
  });
```

**Get Trade by ID**:

```javascript
db.collection("trades")
  .doc("BTCUSD_Double Dip RSI_20260131073858_be807a48")
  .get();
```

#### Viewing Your Trades

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Navigate to **Firestore Database**
3. Select the `trades` collection
4. View individual trade documents with timestamps and all trade data

> [!NOTE]
> Firestore journaling failures are logged but will never interrupt trade execution. The service degrades gracefully if Firestore is unavailable.

### Strategy State Persistence

The platform includes a local persistence mechanism to ensure that strategy-specific trade flags (like Milestone Hits and Partial Exits) are preserved even if the bot application restarts.

#### How it Works

1.  **Action Persistence**: Every time a strategy executes an action (e.g., hits a 50% profit milestone or performs a partial take-profit), it saves its current state to a JSON file in `data/state/`.
2.  **Restart Recovery**: On startup, the strategy reconciles its position with the exchange. If it finds an active trade, it loads the corresponding state file to restore all previously hit milestones.
3.  **Isolation**: State files are named by symbol (e.g., `ARCUSD_donchian_channel_state.json`), ensuring that different coins in multi-coin mode do not interfere with each other.
4.  **Automatic Cleanup**: When a position is closed on the exchange, the state file is automatically deleted to stay clean for the next trade.

#### Benefits

- ✅ **No Duplicate Signals**: Prevents the bot from re-firing a "Partial Exit" signal every time you restart.
- ✅ **Perfect Continuity**: Allows the bot to remember exactly which milestones were already captured, even if the "warmup" backtest misses them due to slight price discrepancies.
- ✅ **Offline Tolerance**: If a milestone is missed while the bot is offline, the persistence layer ensures the bot knows it still needs to fire that exit on the next cycle.

> [!TIP]
> **Git Protection**: The `data/state/` directory is automatically ignored by Git (via `.gitignore`) to prevent your private trade state from being committed to the repository.

### Trading Settings (settings.yaml)

```yaml
timeframes:
  - 5m
  - 15m
  - 1h
  - 4h
  - 1d

backtesting:
  initial_capital: 10000
  commission_maker: 0.0004 # 0.04%
  commission_taker: 0.0006 # 0.06%
  slippage: 0.0001 # 0.01%
```

### MAE / MFE Backtest Metrics

Every backtest now computes **Maximum Adverse Excursion (MAE)** and **Maximum Favorable Excursion (MFE)** for each individual trade.

| Metric | What it means |
|--------|--------------|
| **MAE %** | Largest price move *against* the position during the trade lifetime, expressed as % of entry price. High MAE = the trade took heavy heat before resolving. Use this to tune stop-loss levels. |
| **MFE %** | Largest price move *in favour* of the position during the trade lifetime (best unrealised profit seen). High MFE with low final return = profit was available but not captured. Use this to tune take-profit levels. |

#### Where they appear in the HTML report

1. **Trades tab** — `MAE %` (orange) and `MFE %` (blue) columns added to the trade list table.
2. **Metrics tab** — A new "MAE / MFE Analysis" section in the Detailed Strategy Metrics table with Avg MAE %, Max MAE %, Avg MFE %, and Max MFE % broken out by All / Long / Short.
3. **Overview tab** — A MAE/MFE **scatter chart** (X = MFE%, Y = MAE%):
   - 🟢 Green dots = winning trades
   - 🔴 Red dots = losing trades
   - Dashed diagonal line = where MAE == MFE
   - Trades **below the diagonal** (MFE > MAE) indicate setups with genuine follow-through.

#### Interpretation guide

- **High MFE, low return** → your exits are too early; widen TP or trail more aggressively.
- **High MAE, winning trade** → the trade barely survived; your stop may be too tight or entry timing off.
- **Low MFE, losing trade** → the setup had no edge; the trade moved against you from the start.

---

### HTML Report — Additional Charts

The Overview tab of the HTML report also includes three additional Plotly charts:

| Chart | What it shows |
|-------|---------------|
| **Monthly Returns Heatmap** | Year × Month grid; green = profitable month, red = losing. Helps spot seasonal patterns. |
| **Weekly Equity Candlestick** | Equity curve resampled to weekly OHLC bars with blue entry (▲) and orange exit (×) trade markers overlaid. |
| **Win/Loss Streak Chart** | Horizontal bars showing each consecutive run of wins (green) or losses (red) in chronological order; useful for spotting clustering of bad trades. |


  max_leverage: 10
```

## Available Strategies

### 1. EMA Crossover Strategy (BTCUSD)

- **Timeframe**: 1 hour with Heikin Ashi candles
- **Entry**: EMA crossover signals
- **Exit**: Supertrend flip or partial TP/ATR trail stop
- **Features**: Dynamic position sizing, partial profit taking

### 2. RSI-200 EMA Strategy (ETHUSD)

- **Timeframe**: 1 hour with Heikin Ashi candles
- **Entry Long**: RSI crosses above 70 & close above EMA 200
- **Exit**: Price closes below EMA 200 or partial TP/ATR trail stop
- **Features**: Partial profit taking, ATR trailing stop

### 3. RSI-Supertrend Strategy (RIVERUSD)

- **Timeframe**: 1 hour with Standard candles
- **Type**: Long-only strategy
- **Entry**: RSI crosses above 50
- **Exit**: Supertrend flips from bullish to bearish
- **Indicators**:
  - RSI (14 period)
  - Supertrend (ATR Length: 10, Multiplier: 2.0)
- **Features**:
  - ATR calculated using RMA (Running Moving Average / Wilder's smoothing)
  - Clean backtest with position tracking
  - Dashboard with real-time P&L for open positions

**Configuration** (`config/.env`):

```env
TARGET_MARGIN_RIVER=40  # Use $40 margin for positions
LEVERAGE_RIVER=5
ENABLE_ORDER_PLACEMENT_RIVER=true
```

> [!NOTE]
> Environment variables use `RIVER` as the base asset name (not `RIVERUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

**Strategy Parameters** (`config/settings.yaml`):

```yaml
rsi_supertrend:
  rsi_length: 14
  rsi_long_level: 50.0
  atr_length: 10
  atr_multiplier: 2.0
```

### 4. Donchian Channel Strategy (RIVERUSD)

- **Timeframe**: 1 hour with **Heikin Ashi** candles
- **Type**: Both long and short breakout strategy
- **Entry Long**: Price breaks above upper Donchian channel (20-period highest high) **AND** price > 100 EMA
- **Entry Short**: Price breaks below lower Donchian channel (10-period lowest low) **AND** price < 100 EMA
- **Exit**: Price breaks opposite channel OR trailing stop hit
- **Indicators**:
  - Upper Channel (20-period highest high)
  - Lower Channel (10-period lowest low)
  - **100 EMA (NEW)** - Trend filter for entry confirmation
  - ATR (16 period, EMA-based)
- **Features**:
  - **EMA Trend Filter** - Confirms trend direction before entry (reduces false breakouts)
  - ATR trailing stop (2× ATR from current price)
  - Partial TP (50% exit at 4× ATR, **enabled by default**)
  - Dynamic trailing stop that ratchets with price movement
  - Closed candle logic for breakout confirmation
  - Both long and short trading (configurable via `trade_mode`)

**Configuration** (`config/.env`):

```env
TARGET_MARGIN_RIVER=40  # Use $40 margin for positions
LEVERAGE_RIVER=5
ENABLE_ORDER_PLACEMENT_RIVER=true
```

> [!NOTE]
> Environment variables use `RIVER` as the base asset name (not `RIVERUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

**Strategy Parameters** (`config/settings.yaml`):

```yaml
donchian_channel:
  trade_mode: "Both" # "Long", "Short", or "Both"
  enter_period: 20 # Enter channel (highest high period)
  exit_period: 10 # Exit channel (lowest low period)
  atr_period: 16 # ATR calculation period
  atr_mult_tp: 4.0 # ATR multiplier for take profit
  atr_mult_trail: 2.0 # ATR multiplier for trailing stop
  enable_partial_tp: true # Enable 50% partial TP (updated default)
  partial_pct: 0.5 # 50% partial exit when enabled
  bars_per_day: 24 # For 1H timeframe
  min_long_days: 0 # Minimum long duration (0 = no requirement)
  # NEW: EMA Trend Filter
  ema_length: 100 # EMA period for entry filter
  ema_source: "close" # Source for EMA calculation
  # NEW: Fixed Stop Loss
  stop_loss_pct: 0.50 # Optional: Fixed stop loss % (e.g. 0.50 = 50% of margin)
```

**Entry Logic**:

1. **Long**: Breakout above 20-period high **AND** close > 100 EMA (confirms uptrend)
2. **Short**: Breakdown below 10-period low **AND** close < 100 EMA (confirms downtrend)

**Exit Logic**:

1. **Trailing Stop**: 2× ATR from current price (ratchets with favorable price movement)
2. **50% Partial TP**: At entry ± 4× ATR (now enabled by default)
3. **Channel Exit**: Price breaks opposite channel level

**Strategy Logic Summary**:

| Action | Price Source | Logic Type | Key Indicator |
| :--- | :--- | :--- | :--- |
| **Entries** | Closed Candle | Trend Following | Donchian High/Low + EMA |
| **Channel Exits** | Closed Candle | Trend Reversal | Donchian Low/High |
| **Trailing SL** | Closed Candle | Ratchet | ATR Multiplier |
| **Partial TP** | **Live Price** | Target Hit | ATR Multiplier |
| **Milestone Exit**| **Live / Exch PnL**| Scale Out | PnL % + Leverage |

**Benefits of EMA Filter**:

- ✅ Reduces false breakouts in sideways markets
- ✅ Improves win rate by confirming trend direction
- ✅ Filters counter-trend trades
- ✅ Works bidirectionally (long above EMA, short below EMA)

### 5. Donchian Channel Strategy (PIPPINUSD)

Same strategy as above (RIVERUSD), configured for the PIPPINUSD trading pair.

**Configuration** (`config/.env`):

```env
TARGET_MARGIN_PIPPIN=50  # Use $50 margin for positions
LEVERAGE_PIPPIN=5
ENABLE_ORDER_PLACEMENT_PIPPIN=true
```

> [!NOTE]
> Environment variables use `PIPPIN` as the base asset name (not `PIPPINUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

### 6. Donchian Channel Strategy (BIOUSD)

Same Donchian Channel strategy, configured for the **BIOUSD** futures pair.

- **Timeframe**: 4H with **Standard** candles
- **Leverage**: 5x
- **Target Margin**: $50
- **Strategy ID**: 11 (`--strategy 11`)
- **Service File**: `service/delta-bot-bio.service`

**Configuration** (`config/.env`):

```env
# BIOUSD — base asset key is 'BIO' (code strips 'USD' from symbol)
TARGET_MARGIN_BIO=50   # Use $50 margin for positions
LEVERAGE_BIO=5
ENABLE_ORDER_PLACEMENT_BIO=true
```

> [!NOTE]
> Environment variables use `BIO` as the base asset name (not `BIOUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

**Running manually**:

```bash
python3 run_terminal.py --strategy 11 --non-interactive
```

**Deploying as a systemd service**:

```bash
sudo cp service/delta-bot-bio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable delta-bot-bio
sudo systemctl start delta-bot-bio
sudo systemctl status delta-bot-bio
```

### 7. Donchian Channel Strategy (BERAUSD)

Same Donchian Channel strategy, configured for the **BERAUSD** futures pair.

- **Timeframe**: 1H with **Heikin Ashi** candles
- **Leverage**: 5×
- **Target Margin**: $50
- **Strategy ID**: 12 (`--strategy 12`)
- **Service File**: `service/delta-bot-bera.service`

**Configuration** (`config/.env`):

```env
# BERAUSD — base asset key is 'BERA' (code strips 'USD' from symbol)
TARGET_MARGIN_BERA=50   # Use $50 margin for positions
LEVERAGE_BERA=5
ENABLE_ORDER_PLACEMENT_BERA=true
```

> [!NOTE]
> Environment variables use `BERA` as the base asset name (not `BERAUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

**Running manually**:

```bash
python3 run_terminal.py --strategy 12 --non-interactive
```

**Deploying as a systemd service**:

```bash
sudo cp service/delta-bot-bera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable delta-bot-bera
sudo systemctl start delta-bot-bera
sudo systemctl status delta-bot-bera
```

### 8. Donchian Channel Strategy (PAXGUSD)

Same Donchian Channel strategy, configured for the **PAXGUSD** (PAX Gold) futures pair.

- **Timeframe**: 1H with **Heikin Ashi** candles
- **Leverage**: 5×
- **Target Margin**: $30
- **Strategy ID**: 13 (`--strategy 13`)
- **Service File**: `service/delta-bot-paxg.service`

**Configuration** (`config/.env`):

```env
# PAXGUSD — base asset key is 'PAXG' (code strips 'USD' from symbol)
TARGET_MARGIN_PAXG=30   # Use $30 margin for positions
LEVERAGE_PAXG=5
ENABLE_ORDER_PLACEMENT_PAXG=true
```

> [!NOTE]
> Environment variables use `PAXG` as the base asset name (not `PAXGUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

**Running manually**:

```bash
python3 run_terminal.py --strategy 13 --non-interactive
```

**Deploying as a systemd service**:

```bash
sudo cp service/delta-bot-paxg.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable delta-bot-paxg
sudo systemctl start delta-bot-paxg
sudo systemctl status delta-bot-paxg
```

### 8. EMA Cross Strategy (BTCUSD)

- **Timeframe**: 4 hours with **Standard** candles
- **Type**: Both long and short crossover strategy
- **Entry Long**: Fast EMA (10) crosses above Slow EMA (20)
- **Entry Short**: Fast EMA (10) crosses below Slow EMA (20)
- **Exit**: Opposite crossover signal
- **Indicators**:
  - Fast EMA (10 period)
  - Slow EMA (20 period)
- **Features**:
  - **Position Flipping** - Can close and reverse on the same bar (configurable)
  - Both long and short trading (configurable via `trade_mode`)
  - Simple and clean trend-following logic
  - Closed candle logic for signal confirmation

**Configuration** (`config/.env`):

```env
TARGET_MARGIN_BTC=40  # Use $40 margin for positions
LEVERAGE_BTC=5
ENABLE_ORDER_PLACEMENT_BTC=true  # Set to true for live trading
```

> [!NOTE]
> Environment variables use `BTC` as the base asset name (not `BTCUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

**Strategy Parameters** (`config/settings.yaml`):

```yaml
ema_cross:
  trade_mode: "Both" # "Long", "Short", "Both"
  fast_ema_length: 10 # Fast EMA period
  slow_ema_length: 20 # Slow EMA period
  allow_flip: true # Allow same-bar close & reverse
```

**Entry Logic**:

1. **Long**: Fast EMA crosses above Slow EMA (bullish crossover)
2. **Short**: Fast EMA crosses below Slow EMA (bearish crossover)

**Exit Logic**:

1. **Long Exit**: Fast EMA crosses below Slow EMA
2. **Short Exit**: Fast EMA crosses above Slow EMA

**Allow Flip Behavior**:

- When `allow_flip: true` - Can close existing position and immediately open opposite direction
- When `allow_flip: false` - Only enters new positions when flat (no position)

## Closed Candle Logic

All trading strategies use **closed candle logic** for signal generation, ensuring consistency between backtesting and live trading.

### How It Works

- **Entry/Exit Signals**: Generated only after a candle completes (closes)
- **Indicator Calculations**: Based on confirmed closed candle data
- **Trailing Stops**: Level calculated from closed candle ATR, hit detection in real-time
- **Timeframe Support**: Works across all timeframes (5m, 15m, 1h, 3h, 4h, 1d)

### Benefits

✅ **Backtest Alignment** - Live trading matches backtesting results exactly  
✅ **No False Signals** - Eliminates premature entries from developing candle wicks  
✅ **Stable Calculations** - ATR-based stops use confirmed values, not fluctuating mid-candle data  
✅ **Real-Time Protection** - Trailing stops still protect positions immediately while using stable levels

### Implementation

```python
from core.candle_utils import get_closed_candle_index

# Determine closed candle index
closed_idx = get_closed_candle_index(df, current_time_ms, timeframe)

# Use closed candle for signal generation
closed_candle = df.iloc[closed_idx]
if closed_candle['rsi'] > 70:  # Signal based on confirmed data
    enter_long()
```

All strategies automatically use this logic - no configuration needed!

## Usage

### Quick Start

```python
from core.config import get_config
from core.logger import setup_logging, get_logger
from api.rest_client import DeltaRestClient

# Setup
setup_logging(log_level="INFO")
logger = get_logger(__name__)
config = get_config()

# Initialize API client
client = DeltaRestClient(config)

# Fetch historical data (using DEFAULT_HISTORICAL_DAYS)
candles = client.get_historical_candles(
    symbol="BTCUSD",
    resolution="1h"
)

logger.info("Fetched candles", count=len(candles))
```

### Terminal Mode

```bash
# Fetch historical data
python main.py fetch-data --symbol BTCUSD --timeframe 1h --days 30

# Run backtest
python main.py backtest --strategy double-dip --symbol BTCUSD

# Start live trading (paper mode)
python main.py live --strategy double-dip --symbol BTCUSD --paper --candle-type heikin-ashi

# Start Terminal for RS-50-EMA (XRPUSD)
python run_terminal.py --strategy 4

# Generate report
python main.py report --backtest-id latest --output report.pdf
```

## Development Status

### ✅ Completed

- [x] Core infrastructure (config, logging, exceptions)
- [x] Delta Exchange REST API integration
- [x] Rate limiting and error handling
- [x] Pydantic data models
- [x] Configuration management
- [x] Project structure
- [x] Live trading engine (Terminal Based)
- [x] **Closed Candle Logic Standardization** - All strategies use confirmed candle closes for signal generation
- [x] **Candle Utilities Module** - Centralized closed candle detection for all timeframes
- [x] Strategy framework with multiple implementations:
  - [x] Double-Dip RSI (BTCUSD) - Long/Short with ATR-based TP and trailing stops
  - [x] CCI-EMA (BTCUSD) - CCI crossover with EMA trend filter
  - [x] RSI-50-EMA (XRPUSD) - RSI + EMA with fresh signal detection
  - [x] MACD-PSAR-100EMA (XRPUSD) - MACD histogram with PSAR filter
  - [x] RSI-200-EMA (ETHUSD) - RSI crossover with 200 EMA and ATR-based exits
  - [x] RSI-Supertrend (RIVERUSD) - RSI crossover with Supertrend exit (RMA-based ATR)
  - [x] Donchian Channel (RIVERUSD, PIPPINUSD, PIUSD, BERAUSD, PAXGUSD) - Breakout with ATR trailing stop
- [x] **3-Hour Candle Aggregation** - Local candle aggregation for custom timeframes
- [x] **Position Reconciliation** - Automatic sync with exchange on restart
- [x] **ATR-based Risk Management** - Dynamic trailing stops and partial exits
- [x] Asset-specific order configuration
- [x] Notifications (Discord/Email) with color-coded status messages and error alerts
- [x] Terminal interface with live position tracking and PnL display

### 🚧 In Progress

- [ ] WebSocket client for live data streaming
- [ ] Advanced data storage (SQLite/CSV with historical replay)
- [ ] Portfolio optimization and multi-strategy allocation
- [ ] PDF report generation with performance analytics
- [ ] Web dashboard UI
- [ ] Backtesting engine enhancements (slippage modeling, realistic fill simulation)

## API Reference

### DeltaRestClient

```python
from api.rest_client import DeltaRestClient

client = DeltaRestClient(config)

# Market data
products = client.get_products()
ticker = client.get_ticker("BTCUSD")
orderbook = client.get_l2_orderbook(product_id=1)
candles = client.get_historical_candles("BTCUSD", "1h", days=30)

# Account
balance = client.get_wallet_balance()
positions = client.get_positions()
orders = client.get_live_orders()

# Trading (check ENABLE_ORDER_PLACEMENT)
order = client.place_order(
    product_id=1,
    size=10,
    side="buy",
    order_type="limit_order",
    limit_price="50000"
)
client.cancel_order(product_id=1, order_id=order['id'])
```

## Delta Exchange Fees

- **Maker Fee**: 0.04%
- **Taker Fee**: 0.06%
- **Settlement Fee**: 0.06%

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=api --cov=data

# Run specific test file
pytest tests/unit/test_config.py -v
```

## Logging

Logs are written to both console and file in human-readable format:

```
2024-11-30T18:00:00.123456 [info     ] Delta REST client initialized base_url=https://cdn-ind.testnet.deltaex.org environment=testnet
2024-11-30T18:00:01.234567 [info     ] Fetching historical candles days=30 resolution=1h symbol=BTCUSD
2024-11-30T18:00:02.345678 [info     ] Completed fetching historical candles symbol=BTCUSD total_candles=720
```

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests
4. Submit a pull request

## License

MIT License

## Support

For issues and questions:

- Delta Exchange API Docs: https://docs.delta.exchange/
- Delta Exchange Support: https://www.delta.exchange/support

## Roadmap

### Completed ✅

- [x] Advanced technical indicators (MACD, RSI, CCI, EMA, PSAR, ATR, Donchian Channels)
- [x] Multiple strategy support (9 strategies implemented)
- [x] Closed candle logic standardization
- [x] ATR-based risk management (trailing stops, partial exits)
- [x] Position reconciliation on restart
- [x] Color-coded Discord notifications

### Planned 🎯

- [ ] WebSocket live data streaming
- [ ] Walk-forward analysis
- [ ] Risk management dashboard (web UI)
- [ ] Mobile notifications (Telegram, push notifications)
- [ ] Cloud deployment support (Docker, Kubernetes)
- [ ] Multi-strategy portfolio optimization
- [ ] Advanced backtesting (Monte Carlo simulation, realistic slippage)
- [ ] Performance analytics dashboard

## Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of this software. Always test strategies thoroughly in a testnet environment before using real funds.
