"""Structured logging configuration using structlog."""

import logging
import sys
from pathlib import Path
from typing import Optional

import structlog
from structlog.types import Processor


def setup_logging(
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_max_bytes: int = 10485760,  # 10MB
    log_backup_count: int = 5,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Path to log file (optional)
        log_max_bytes: Maximum size of log file before rotation
        log_backup_count: Number of backup log files to keep
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Create logs directory if it doesn't exist
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure structlog processors for human-readable output
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

    # Add console renderer for human-readable output
    if sys.stderr.isatty():
        # Use colored output for terminal
        processors.append(structlog.dev.ConsoleRenderer())
    else:
        # Use key-value output for non-terminal (e.g., file)
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
    )

    # Add file handler if log file is specified
    if log_file:
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_file, maxBytes=log_max_bytes, backupCount=log_backup_count
        )
        file_handler.setLevel(numeric_level)

        # Use key-value format for file logs
        file_formatter = logging.Formatter("%(message)s")
        file_handler.setFormatter(file_formatter)

        # Add handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance for the specified module.

    Args:
        name: Name of the logger (typically __name__)

    Returns:
        Configured structlog logger instance
    """
    return structlog.get_logger(name)


# Example usage and testing
if __name__ == "__main__":
    # Setup logging with file output
    setup_logging(log_level="DEBUG", log_file="logs/test.log")

    # Get logger
    logger = get_logger(__name__)

    # Test different log levels
    logger.debug("Debug message", key="value", number=42)
    logger.info("Info message", status="success")
    logger.warning("Warning message", alert="check this")
    logger.error("Error message", error_code=500)

    # Test with exception
    try:
        raise ValueError("Test exception")
    except Exception:
        logger.exception("Exception occurred", context="testing")
