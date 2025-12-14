"""Main entry point for the Delta Exchange trading platform."""

import argparse
import sys
from pathlib import Path

from core.config import get_config
from core.exceptions import DeltaExchangeError
from core.logger import get_logger, setup_logging

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def setup_environment():
    """Set up logging and configuration."""
    config = get_config()

    # Setup logging with error alerting
    setup_logging(
        log_level=config.log_level,
        log_file=config.log_file,
        log_max_bytes=config.log_max_bytes,
        log_backup_count=config.log_backup_count,
        discord_webhook_url=config.discord_webhook_url if config.discord_enabled else None,
        alert_throttle_seconds=config.alert_throttle_seconds,
        enable_error_alerts=config.enable_error_alerts,
    )

    logger = get_logger(__name__)
    logger.info("Delta Exchange Trading Platform", version="0.1.0", environment=config.environment)

    return config, logger


def cmd_fetch_data(args, config, logger):
    """Fetch historical data command."""
    from api.rest_client import DeltaRestClient

    logger.info(
        "Fetching historical data", symbol=args.symbol, timeframe=args.timeframe, days=args.days
    )

    client = DeltaRestClient(config)

    # Fetch current ticker data
    try:
        # Use the official delta-rest-client library method
        ticker = client.get_ticker(args.symbol)

        logger.debug("Raw ticker data", ticker=ticker)

        # Print ALL ticker fields to see what's available
        print(f"\n{'='*60}")
        print(f"DEBUG: All Ticker Fields for {args.symbol}")
        print(f"{'='*60}")
        for key, value in ticker.items():
            print(f"{key}: {value}")
        print(f"{'='*60}\n")

        # Extract price data - trying common field names
        current_price = (
            ticker.get("close")
            or ticker.get("mark_price")
            or ticker.get("last_price")
            or ticker.get("price")
            or 0
        )

        print(f"\n{'='*60}")
        print(f"Current Market Data for {args.symbol}")
        print(f"{'='*60}")

        if current_price > 0:
            print(f"Last Traded Price: ${current_price:,.2f}")

            if ticker.get("mark_price"):
                print(f"Mark Price: ${ticker['mark_price']:,.2f}")
            if ticker.get("open_interest"):
                print(f"Open Interest: {ticker['open_interest']:,.0f}")
            if ticker.get("volume"):
                print(f"24h Volume: {ticker['volume']:,.2f}")
            if ticker.get("turnover"):
                print(f"24h Turnover: ${ticker['turnover']:,.2f}")
            if ticker.get("funding_rate"):
                print(f"Funding Rate: {ticker['funding_rate']:.6f}")

            logger.info("Current market data", symbol=args.symbol, price=current_price)
        else:
            print(f"No live price data available")
            print(f"Available ticker fields: {list(ticker.keys())}")

        print(f"{'='*60}\n")

    except Exception as e:
        logger.warning("Failed to fetch ticker data", symbol=args.symbol, error=str(e))
        print(f"Warning: Could not fetch current price for {args.symbol}")
        import traceback

        logger.debug("Ticker fetch error details", traceback=traceback.format_exc())

    # Fetch historical candles
    candles = client.get_historical_candles(
        symbol=args.symbol, resolution=args.timeframe, days=args.days
    )

    logger.info("Data fetched successfully", count=len(candles))

    # TODO: Save to database/CSV
    print(f"\nFetched {len(candles)} candles for {args.symbol} ({args.timeframe})")


def cmd_backtest(args, config, logger):
    """Run backtest command."""
    logger.info(
        "Running backtest", strategy=args.strategy, symbol=args.symbol, timeframe=args.timeframe
    )

    # TODO: Implement backtesting
    print("Backtesting not yet implemented")


def cmd_live(args, config, logger):
    """Start live trading command."""
    mode = "paper" if args.paper else "live"
    logger.info("Starting live trading", strategy=args.strategy, symbol=args.symbol, mode=mode)

    # TODO: Implement live trading
    print(f"Live trading ({mode} mode) not yet implemented")


def cmd_report(args, config, logger):
    """Generate a report."""
    logger.info("Generating report", backtest_id=args.backtest_id, output=args.output)

    # TODO: Implement report generation
    print("Report generation not yet implemented")


def cmd_gui(args, config, logger):
    """Launch GUI command."""
    logger.info("Launching GUI")

    # Pre-flight checks before attempting to import DearPyGui
    import platform
    import os
    
    # Check for display on macOS
    if platform.system() == "Darwin":
        try:
            from AppKit import NSScreen
            screens = NSScreen.screens()
            if not screens or len(screens) == 0:
                print("\n" + "="*70)
                print("ERROR: No display detected")
                print("="*70)
                print("\nThe GUI cannot run without a display.")
                print("Please ensure you're running this on a Mac with an active display.")
                print("\nAlternatively, use terminal mode:")
                print("  python3 main.py fetch-data --symbol BTCUSD --timeframe 1h")
                print("="*70 + "\n")
                return
        except ImportError:
            logger.warning("Could not import AppKit to check display - proceeding anyway")
    
    try:
        from gui.main_window import run_gui

        print("\nInitializing GUI...")
        print("Note: If the application crashes, it may be due to OpenGL/display issues.")
        print("In that case, please use terminal mode instead.\n")
        
        run_gui(config)
        
    except ImportError as e:
        logger.error("Failed to import GUI module", error=str(e))
        print(f"\nError: GUI dependencies not installed.")
        print(f"Please install with: pip install dearpygui")
        print(f"Details: {e}\n")
    except Exception as e:
        logger.exception("GUI error", error=str(e))
        print(f"\nError launching GUI: {e}")
        print("\nThis may be due to:")
        print("  • OpenGL/graphics driver issues")
        print("  • Display compatibility problems")
        print("  • DearPyGui not compatible with your system")
        print("\nPlease use terminal mode instead:")
        print("  python3 main.py fetch-data --symbol BTCUSD")
        print()




def main():
    """Run the main application entry point."""
    parser = argparse.ArgumentParser(description="Delta Exchange Crypto Trading Analysis Platform")

    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Fetch data command
    fetch_parser = subparsers.add_parser("fetch-data", help="Fetch historical data")
    fetch_parser.add_argument("--symbol", required=True, help="Trading symbol (e.g., BTCUSD)")
    fetch_parser.add_argument("--timeframe", default="1h", help="Timeframe (5m, 15m, 1h, 4h, 1d)")
    fetch_parser.add_argument("--days", type=int, default=30, help="Number of days")

    # Backtest command
    backtest_parser = subparsers.add_parser("backtest", help="Run backtest")
    backtest_parser.add_argument("--strategy", required=True, help="Strategy name")
    backtest_parser.add_argument("--symbol", required=True, help="Trading symbol")
    backtest_parser.add_argument("--timeframe", default="1h", help="Timeframe")
    backtest_parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    backtest_parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")

    # Live trading command
    live_parser = subparsers.add_parser("live", help="Start live trading")
    live_parser.add_argument("--strategy", required=True, help="Strategy name")
    live_parser.add_argument("--symbol", required=True, help="Trading symbol")
    live_parser.add_argument("--paper", action="store_true", help="Paper trading mode")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate report")
    report_parser.add_argument("--backtest-id", default="latest", help="Backtest ID")
    report_parser.add_argument("--output", default="report.pdf", help="Output file")

    args = parser.parse_args()

    try:
        # Setup environment
        config, logger = setup_environment()

        # Handle GUI mode
        if args.gui:
            cmd_gui(args, config, logger)
            return

        # Handle commands
        if args.command == "fetch-data":
            cmd_fetch_data(args, config, logger)
        elif args.command == "backtest":
            cmd_backtest(args, config, logger)
        elif args.command == "live":
            cmd_live(args, config, logger)
        elif args.command == "report":
            cmd_report(args, config, logger)
        else:
            parser.print_help()

    except DeltaExchangeError as e:
        if 'logger' in locals():
            logger.error("Application error", error=str(e))
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        if 'logger' in locals():
            logger.info("Application interrupted by user")
        print("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        if 'logger' in locals():
            logger.exception("Unexpected error", error=str(e))
        print(f"Unexpected error: {e}", file=sys.stderr)
        # Check if traceback is needed
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
