# Delta Exchange Crypto Trading Analysis Platform

A comprehensive Python-based crypto trading analysis platform with Delta Exchange futures API integration, supporting backtesting, paper trading, and live trading with a terminal interface.

## Features

- **Multiple Trading Modes**: Backtesting, Paper Trading, and Live Trading
- **Delta Exchange Integration**: Official `delta-rest-client` library with rate limiting
- **Closed Candle Logic**: Standardized signal generation on confirmed candle closes (eliminates backtest vs. live discrepancies)
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
  - Donchian Channel (RIVERUSD) - Long-only breakout with ATR trailing stop
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
│   ├── candle_utils.py # Closed candle detection utilities (NEW)
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
│   ├── donchian_strategy.py   # Donchian Channel strategy (RIVERUSD)
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

#### Trade Data Schema

Each trade is stored with comprehensive data:

- **Metadata**: `timestamp`, `symbol`, `strategy_name`, `mode` (live/paper)
- **Action**: `action` (ENTRY_LONG, EXIT_LONG, etc.), `side` (buy/sell)
- **Pricing**: `price` (candle close), `entry_price`, `exit_price`, `execution_price`
- **Position**: `order_size`, `leverage`, `is_entry`, `is_partial_exit`
- **Financials**: `pnl`, `funding_charges`, `trading_fees`, `margin_used`, `remaining_margin`
- **Indicators**: `rsi`, `reason` (trade trigger)
- **Exchange**: `product_id`, `order_id`

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

- **Timeframe**: 1 hour with Heikin Ashi candles
- **Type**: Long-only breakout strategy
- **Entry**: Price breaks above upper Donchian channel (20-period highest high)
- **Exit**: Price breaks below lower Donchian channel (10-period lowest low) OR trailing stop hit
- **Indicators**:
  - Upper Channel (20-period highest high)
  - Lower Channel (10-period lowest low)
  - ATR (16 period, EMA-based)
- **Features**:
  - ATR trailing stop (2× ATR below current price)
  - Optional partial TP (50% exit at 4× ATR, disabled by default)
  - Dynamic trailing stop that ratchets up with price
  - Closed candle logic for breakout confirmation

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
  enter_period: 20 # Enter channel (highest high period)
  exit_period: 10 # Exit channel (lowest low period)
  atr_period: 16 # ATR calculation period
  atr_mult_tp: 4.0 # ATR multiplier for take profit
  atr_mult_trail: 2.0 # ATR multiplier for trailing stop
  enable_partial_tp: false # Disable partial TP by default
  partial_pct: 0.5 # 50% partial exit when enabled
  bars_per_day: 24 # For 1H timeframe
  min_long_days: 2 # Minimum long duration (tracking only)
```

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
  - [x] Donchian Channel (RIVERUSD) - Long-only breakout with ATR trailing stop
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
- [x] Multiple strategy support (7 strategies implemented)
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
