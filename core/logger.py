"""Enhanced logging configuration with human-readable formatting."""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog
from structlog.types import Processor


class HumanReadableFormatter(logging.Formatter):
    """Custom formatter for human-readable log output to files."""

    # Color codes for terminal output
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",  # Reset
    }

    # ANSI escape sequence pattern for stripping colors
    import re
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def __init__(self, use_colors: bool = False, *args, **kwargs):
        """
        Initialize the formatter.

        Args:
            use_colors: Whether to use ANSI color codes
        """
        super().__init__(*args, **kwargs)
        self.use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record in a human-readable way.

        Args:
            record: Log record to format

        Returns:
            Formatted log string
        """
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Get log level with optional color
        level = record.levelname
        if self.use_colors and level in self.COLORS:
            level = f"{self.COLORS[level]}{level:8s}{self.COLORS['RESET']}"
        else:
            level = f"{level:8s}"

        # Get logger name (shortened if too long)
        logger_name = record.name
        if len(logger_name) > 30:
            logger_name = "..." + logger_name[-27:]

        # Get the message and strip ANSI color codes
        message = record.getMessage()
        if not self.use_colors:
            message = self.ANSI_ESCAPE.sub('', message)

        # Build the base message
        parts = [
            f"[{timestamp}]",
            f"[{level}]",
            f"[{logger_name:30s}]",
            message,
        ]

        # Add exception info if present
        if record.exc_info:
            exc_text = self.formatException(record.exc_info)
            parts.append(f"\n{exc_text}")

        return " ".join(parts)


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_max_bytes: int = 524288000,  # 500MB default
    log_backup_count: int = 5,
    human_readable: bool = True,
    discord_webhook_url: Optional[str] = None,
    alert_throttle_seconds: int = 300,  # 5 minutes
    enable_error_alerts: bool = True,
) -> None:
    """
    Configure enhanced logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (optional)
        log_max_bytes: Maximum size of log file before rotation (default: 500MB)
        log_backup_count: Number of backup log files to keep
        human_readable: Use human-readable formatting (default: True)
        discord_webhook_url: Discord webhook URL for error alerts (optional)
        alert_throttle_seconds: Minimum seconds between alerts for same error
        enable_error_alerts: Enable Discord alerts for ERROR/CRITICAL messages
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure structlog processors
    processors: list[Processor] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if human_readable:
        # Use colored console renderer for human-readable output
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=sys.stderr.isatty(),  # Only use colors if outputting to terminal
            )
        )
    else:
        # Use key-value output for machine parsing
        processors.append(
            structlog.processors.KeyValueRenderer(
                key_order=["timestamp", "level", "event", "logger"], drop_missing=True
            )
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=numeric_level,
        stream=sys.stderr,
        force=True,
    )

    # Add file handler if log file is specified
    if log_file:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file, maxBytes=log_max_bytes, backupCount=log_backup_count
        )
        file_handler.setLevel(numeric_level)

        # Use human-readable formatter for file logs
        if human_readable:
            file_formatter = HumanReadableFormatter(use_colors=False)
        else:
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        file_handler.setFormatter(file_formatter)

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)

    # Add error alert handler if configured
    if enable_error_alerts and discord_webhook_url:
        from .error_alerts import create_error_alert_handler

        alert_handler = create_error_alert_handler(
            discord_webhook_url=discord_webhook_url,
            alert_throttle_seconds=alert_throttle_seconds,
        )
        
        if alert_handler:
            root_logger = logging.getLogger()
            root_logger.addHandler(alert_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance for the specified module.

    Args:
        name: Name of the logger (typically __name__)

    Returns:
        Configured structlog logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User logged in", user_id=123, ip="192.168.1.1")
        >>> logger.error("Failed to connect", error="Connection timeout", retry_count=3)
    """
    return structlog.get_logger(name)


class LogManager:
    """
    Enhanced log manager for centralized logging operations.

    This class provides additional utilities for managing logs across the application.
    """

    def __init__(self, name: str):
        """
        Initialize the log manager.

        Args:
            name: Name of the logger (typically __name__)
        """
        self.logger = get_logger(name)
        self.name = name

    def debug(self, message: str, **kwargs):
        """Log a debug message."""
        self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log an info message."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log a warning message."""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log an error message."""
        self.logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log a critical message."""
        self.logger.critical(message, **kwargs)

    def exception(self, message: str, **kwargs):
        """Log an exception with traceback."""
        self.logger.exception(message, **kwargs)

    def log_operation(self, operation: str, **kwargs):
        """
        Log the start of an operation.

        Args:
            operation: Name of the operation
            **kwargs: Additional context
        """
        self.info(f"Starting: {operation}", **kwargs)

    def log_success(self, operation: str, **kwargs):
        """
        Log successful completion of an operation.

        Args:
            operation: Name of the operation
            **kwargs: Additional context
        """
        self.info(f"Success: {operation}", status="completed", **kwargs)

    def log_failure(self, operation: str, error: str, **kwargs):
        """
        Log failure of an operation.

        Args:
            operation: Name of the operation
            error: Error message
            **kwargs: Additional context
        """
        self.error(f"Failed: {operation}", error=error, **kwargs)


# Example usage and testing
if __name__ == "__main__":
    print("=" * 80)
    print("Testing Enhanced Log Manager")
    print("=" * 80)

    # Setup logging with file output
    setup_logging(log_level="DEBUG", log_file="logs/test.log", human_readable=True)

    # Test basic logger
    print("\n1. Testing basic logger:")
    logger = get_logger(__name__)

    logger.debug("Debug message", key="value", number=42)
    logger.info("Info message", status="success", user="admin")
    logger.warning("Warning message", alert="check this", threshold=90)
    logger.error("Error message", error_code=500, endpoint="/api/trade")

    # Test LogManager
    print("\n2. Testing LogManager:")
    log_mgr = LogManager("trading.strategy")

    log_mgr.log_operation("Place Order", symbol="BTCUSD", quantity=0.5, price=45000)
    log_mgr.log_success("Place Order", order_id="12345", filled_price=45010)

    log_mgr.log_operation("Fetch Market Data", symbol="ETHUSD")
    log_mgr.log_failure(
        "Fetch Market Data", error="Connection timeout", retry_count=3, timeout=30
    )

    # Test with exception
    print("\n3. Testing exception logging:")
    try:
        result = 10 / 0
    except Exception as e:
        logger.exception("Division error occurred", operation="calculate", dividend=10, divisor=0)

    # Test long logger names
    print("\n4. Testing long logger names:")
    long_logger = get_logger("very.long.module.name.that.exceeds.thirty.characters.easily")
    long_logger.info("Message from long logger name", test="truncation")

    print("\n" + "=" * 80)
    print("Check logs/test.log for file output")
    print("=" * 80)
