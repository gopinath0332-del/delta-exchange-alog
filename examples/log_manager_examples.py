"""Example usage of the enhanced log manager in a trading context."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.logger import LogManager, get_logger, setup_logging


def example_basic_logging():
    """Example of basic logging usage."""
    print("\n" + "=" * 80)
    print("Example 1: Basic Logging")
    print("=" * 80 + "\n")

    logger = get_logger("trading.example")

    # Log different levels with context
    logger.debug("Initializing trading session", session_id="abc123", user="trader1")
    logger.info("Market data received", symbol="BTCUSD", price=45000, volume=1234.56)
    logger.warning(
        "High volatility detected", symbol="ETHUSD", volatility=0.15, threshold=0.10
    )
    logger.error(
        "Order rejected", symbol="BTCUSD", reason="Insufficient funds", required=1000, available=500
    )


def example_log_manager():
    """Example of LogManager usage for operations."""
    print("\n" + "=" * 80)
    print("Example 2: LogManager for Trading Operations")
    print("=" * 80 + "\n")

    log_mgr = LogManager("trading.executor")

    # Successful trade execution
    log_mgr.log_operation(
        "Execute Buy Order",
        symbol="BTCUSD",
        quantity=0.5,
        price=45000,
        order_type="LIMIT",
    )
    log_mgr.log_success(
        "Execute Buy Order",
        order_id="ORD-12345",
        filled_price=45010,
        filled_quantity=0.5,
        commission=2.25,
    )

    # Failed trade execution
    log_mgr.log_operation(
        "Execute Sell Order",
        symbol="ETHUSD",
        quantity=2.0,
        price=3000,
        order_type="MARKET",
    )
    log_mgr.log_failure(
        "Execute Sell Order",
        error="Market closed",
        symbol="ETHUSD",
        retry_after=3600,
    )


def example_strategy_logging():
    """Example of logging in a trading strategy."""
    print("\n" + "=" * 80)
    print("Example 3: Strategy Execution Logging")
    print("=" * 80 + "\n")

    strategy_logger = get_logger("trading.strategy.momentum")

    # Strategy initialization
    strategy_logger.info(
        "Strategy initialized",
        strategy="Momentum",
        symbols=["BTCUSD", "ETHUSD"],
        timeframe="1h",
        lookback_period=20,
    )

    # Signal generation
    strategy_logger.info(
        "Buy signal generated",
        symbol="BTCUSD",
        price=45000,
        rsi=35.5,
        macd_signal="bullish",
        confidence=0.85,
    )

    # Position management
    strategy_logger.info(
        "Position opened",
        symbol="BTCUSD",
        side="LONG",
        entry_price=45010,
        quantity=0.5,
        stop_loss=44000,
        take_profit=47000,
    )

    # Risk management
    strategy_logger.warning(
        "Stop loss triggered",
        symbol="BTCUSD",
        entry_price=45010,
        exit_price=44005,
        pnl=-502.50,
        pnl_percent=-2.23,
    )


def example_error_handling():
    """Example of error and exception logging."""
    print("\n" + "=" * 80)
    print("Example 4: Error Handling and Exception Logging")
    print("=" * 80 + "\n")

    api_logger = get_logger("trading.api")

    # Connection error
    api_logger.error(
        "WebSocket connection failed",
        endpoint="wss://api.delta.exchange",
        error="Connection timeout",
        retry_count=3,
        next_retry_in=30,
    )

    # Exception with traceback
    try:
        # Simulate an error
        price = None
        profit = 1000 / price  # This will raise TypeError
    except Exception:
        api_logger.exception(
            "Failed to calculate profit",
            operation="calculate_pnl",
            position_id="POS-789",
            entry_price=45000,
        )


def example_data_fetching():
    """Example of logging data fetching operations."""
    print("\n" + "=" * 80)
    print("Example 5: Data Fetching and Processing")
    print("=" * 80 + "\n")

    data_logger = LogManager("trading.data")

    # Fetch historical data
    data_logger.log_operation(
        "Fetch Historical Candles",
        symbol="BTCUSD",
        timeframe="1h",
        start_date="2024-01-01",
        end_date="2024-12-06",
    )
    data_logger.log_success(
        "Fetch Historical Candles",
        candles_fetched=8760,
        data_size_mb=2.5,
        duration_ms=1250,
    )

    # Process market data
    data_logger.info(
        "Market data processed",
        symbol="BTCUSD",
        records=8760,
        missing_data_points=5,
        data_quality=0.9994,
    )

    # Cache update
    data_logger.info(
        "Cache updated",
        cache_type="market_data",
        symbols=["BTCUSD", "ETHUSD", "BNBUSD"],
        cache_size_mb=15.3,
        ttl_seconds=300,
    )


def example_performance_monitoring():
    """Example of logging performance metrics."""
    print("\n" + "=" * 80)
    print("Example 6: Performance Monitoring")
    print("=" * 80 + "\n")

    perf_logger = get_logger("trading.performance")

    # Strategy performance
    perf_logger.info(
        "Daily performance summary",
        date="2024-12-06",
        total_trades=15,
        winning_trades=9,
        losing_trades=6,
        win_rate=0.60,
        total_pnl=1250.75,
        max_drawdown=-350.00,
        sharpe_ratio=1.85,
    )

    # System performance
    perf_logger.info(
        "System metrics",
        cpu_usage_percent=45.2,
        memory_usage_mb=512,
        active_connections=3,
        messages_per_second=125,
        latency_ms=15.3,
    )

    # Performance warning
    perf_logger.warning(
        "High latency detected",
        endpoint="market_data",
        latency_ms=250,
        threshold_ms=100,
        recommendation="Check network connection",
    )


def main():
    """Run all examples."""
    # Setup logging with human-readable format
    setup_logging(
        log_level="DEBUG",
        log_file="logs/examples.log",
        human_readable=True,
    )

    print("\n" + "=" * 80)
    print("Enhanced Log Manager - Trading Examples")
    print("=" * 80)

    # Run all examples
    example_basic_logging()
    example_log_manager()
    example_strategy_logging()
    example_error_handling()
    example_data_fetching()
    example_performance_monitoring()

    print("\n" + "=" * 80)
    print("All examples completed!")
    print("Check logs/examples.log for file output")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
