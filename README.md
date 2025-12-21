# Delta Exchange Crypto Trading Analysis Platform

A comprehensive Python-based crypto trading analysis platform with Delta Exchange futures API integration, supporting backtesting, paper trading, and live trading with a terminal interface.

## Features

- **Multiple Trading Modes**: Backtesting, Paper Trading, and Live Trading
- **Delta Exchange Integration**: Official `delta-rest-client` library with rate limiting
- **Structured Logging**: Human-readable logs using `structlog`
- **Modular Architecture**: Clean separation of concerns for easy extension
- **Multiple Timeframes**: 5m, 15m, 1h, 4h, 1d (configurable)
- **Notifications**: Discord webhooks and Email alerts
- **PDF Reports**: Professional trading reports with charts
- **Premium Strategies**: Includes RS-50-EMA (XRPUSD) and Double-Dip RSI.
- **Dynamic Configuration**: Asset-specific order sizing and leverage via env vars.
- **Terminal Interface**: Robust CLI dashboard with live strategy monitoring

## Project Structure

```
delta-exchange-alog/
├── config/              # Configuration files
│   ├── .env.example    # Environment variables template
│   └── settings.yaml   # Trading parameters
├── core/               # Core infrastructure
│   ├── config.py       # Configuration management
│   ├── logger.py       # Structured logging
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
├── strategies/         # Trading strategies
│   ├── base.py         # Base strategy class
│   ├── indicators.py   # Technical indicators
│   └── examples/       # Example strategies
├── backtesting/        # Backtesting engine
├── trading/            # Live trading engine
├── notifications/      # Alert system
├── reporting/          # PDF report generation
├── terminal/           # Terminal interface
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
```

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
- [x] Live trading engine (Terminal Based)
- [x] Strategy framework (Double Dip RSI, CCI+EMA, RS-50-EMA)
- [x] Asset-specific order configuration
- [x] Notifications (Discord/Email)
- [x] Terminal interface

### 🚧 In Progress

- [ ] WebSocket client for live data
- [ ] Data storage (SQLite/CSV)
- [ ] Data preprocessing
- [ ] Portfolio optimization
- [ ] PDF report generation

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

- [ ] Advanced technical indicators (MACD, Bollinger Bands)
- [ ] Multiple strategy support
- [ ] Walk-forward analysis
- [ ] Risk management dashboard
- [ ] Mobile notifications
- [ ] Cloud deployment support

## Disclaimer

This software is for educational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of this software. Always test strategies thoroughly in a testnet environment before using real funds.
