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
  - **EMA Cross (BTCUSD)** - 10/20 EMA crossover with position flipping (NEW)
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
│   └── preprocessor.py # Data processing
├── strategies/         # Trading strategies (all use closed candle logic)
│   ├── double_dip_rsi.py      # Double-Dip RSI strategy (BTCUSD)
│   ├── cci_ema_strategy.py    # CCI + 50 EMA strategy (BTCUSD)
│   ├── rsi_50_ema_strategy.py # RSI + 50 EMA strategy (XRPUSD)
│   ├── macd_psar_100ema_strategy.py # MACD + PSAR + 100 EMA (XRPUSD)
│   ├── rsi_200_ema_strategy.py # RSI + 200 EMA strategy (ETHUSD)
│   ├── rsi_supertrend_strategy.py # RSI + Supertrend strategy (RIVERUSD)
│   ├── donchian_strategy.py   # Donchian Channel strategy (RIVERUSD, PIPPINUSD)
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

# Symbol Specific Order Settings
# Overrides default order size (1) and leverage (5)
ORDER_SIZE_XRP=10
LEVERAGE_XRP=5
ORDER_SIZE_BTC=1
LEVERAGE_BTC=5

# Firestore Trade Journaling (optional)
# See Firebase Admin SDK setup below
FIREBASE_PROJECT_ID=crypto-journal-b2298
```

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
```

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

risk_management:
  max_position_size: 0.1 # 10% of capital
  max_daily_loss: 0.02 # 2%
  max_drawdown: 0.15 # 15%
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
ORDER_SIZE_RIVER=4
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
ORDER_SIZE_RIVER=4
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
```

**Entry Logic**:

1. **Long**: Breakout above 20-period high **AND** close > 100 EMA (confirms uptrend)
2. **Short**: Breakdown below 10-period low **AND** close < 100 EMA (confirms downtrend)

**Exit Logic**:

1. **50% Partial TP**: At entry ± 4× ATR (now enabled by default)
2. **Trailing Stop**: 2× ATR from current price (ratchets with favorable price movement)
3. **Channel Exit**: Price breaks opposite channel level

**Benefits of EMA Filter**:

- ✅ Reduces false breakouts in sideways markets
- ✅ Improves win rate by confirming trend direction
- ✅ Filters counter-trend trades
- ✅ Works bidirectionally (long above EMA, short below EMA)

### 5. Donchian Channel Strategy (PIPPINUSD)

Same strategy as above (RIVERUSD), configured for the PIPPINUSD trading pair.

**Configuration** (`config/.env`):

```env
ORDER_SIZE_PIPPIN=100
LEVERAGE_PIPPIN=5
ENABLE_ORDER_PLACEMENT_PIPPIN=true
```

> [!NOTE]
> Environment variables use `PIPPIN` as the base asset name (not `PIPPINUSD`) because the code automatically strips "USD" from trading symbols when parsing configuration.

### 6. EMA Cross Strategy (BTCUSD)

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
ORDER_SIZE_BTC=2
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
  - [x] Donchian Channel (RIVERUSD, PIPPINUSD) - Breakout with ATR trailing stop
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
- [x] Multiple strategy support (8 strategies implemented)
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
