"""Configuration management for the Delta Exchange trading platform."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .exceptions import ValidationError
from .logger import get_logger

logger = get_logger(__name__)


class BacktestingConfig(BaseModel):
    """Backtesting configuration."""

    initial_capital: float = Field(default=10000, gt=0)
    commission_maker: float = Field(default=0.0004, ge=0)  # 0.04%
    commission_taker: float = Field(default=0.0006, ge=0)  # 0.06%
    slippage: float = Field(default=0.0001, ge=0)  # 0.01%


class RiskManagementConfig(BaseModel):
    """Risk management configuration."""

    max_position_size: float = Field(default=0.1, gt=0, le=1)  # 10% of capital
    max_daily_loss: float = Field(default=0.02, gt=0, le=1)  # 2%
    max_drawdown: float = Field(default=0.15, gt=0, le=1)  # 15%
    max_leverage: int = Field(default=10, gt=0, le=100)


class NotificationsConfig(BaseModel):
    """Notifications configuration."""

    discord_enabled: bool = True
    email_enabled: bool = True
    alert_on_trade: bool = True
    alert_on_error: bool = True
    alert_on_position_open: bool = True
    alert_on_position_close: bool = True


class GUIConfig(BaseModel):
    """GUI configuration."""

    theme: str = "dark"
    window_width: int = Field(default=1400, gt=0)
    window_height: int = Field(default=900, gt=0)
    update_interval: int = Field(default=2000, gt=0)  # milliseconds
    chart_candles: int = Field(default=200, gt=0)
    chart_default_timeframe: str = "1h"
    orderbook_depth: int = Field(default=10, gt=0)
    futures_symbols: List[str] = Field(default_factory=list)  # Loaded from settings.yaml



class TerminalConfig(BaseModel):
    """Terminal configuration."""

    refresh_rate: int = Field(default=1, gt=0)  # seconds
    show_charts: bool = True


class Config:
    """Main configuration class for the trading platform."""

    def __init__(self, env_file: Optional[str] = None, settings_file: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            env_file: Path to .env file (default: config/.env)
            settings_file: Path to settings.yaml file (default: config/settings.yaml)
        """
        self.project_root = Path(__file__).parent.parent

        # Load environment variables
        if env_file is None:
            env_file = str(self.project_root / "config" / ".env")

        if Path(env_file).exists():
            load_dotenv(env_file)
            logger.info("Loaded environment variables", file=str(env_file))
        else:
            logger.warning("Environment file not found", file=str(env_file))

        # Load settings from YAML
        if settings_file is None:
            settings_file = str(self.project_root / "config" / "settings.yaml")

        self.settings = self._load_settings(Path(settings_file))

        # Initialize configuration sections
        self._init_api_config()
        self._init_notification_config()
        self._init_database_config()
        self._init_logging_config()
        self._init_trading_config()
        self._init_firestore_config()  # Initialize Firestore for trade journaling

        logger.info("Configuration initialized successfully")

    def _load_settings(self, settings_file: Path) -> Dict[str, Any]:
        """Load settings from YAML file."""
        if not Path(settings_file).exists():
            logger.warning("Settings file not found, using defaults", file=str(settings_file))
            return {}

        try:
            with open(settings_file, "r") as f:
                settings = yaml.safe_load(f)
                logger.info("Loaded settings from YAML", file=str(settings_file))
                return settings or {}
        except Exception as e:
            logger.error("Failed to load settings file", file=str(settings_file), error=str(e))
            raise ValidationError(f"Failed to load settings: {e}")

    def _init_api_config(self):
        """Initialize API configuration."""
        self.api_key = os.getenv("DELTA_API_KEY", "")
        self.api_secret = os.getenv("DELTA_API_SECRET", "")
        self.environment = os.getenv("DELTA_ENVIRONMENT", "testnet")
        self.base_url = os.getenv("DELTA_BASE_URL", "https://cdn-ind.testnet.deltaex.org")

        # Validate API credentials
        if not self.api_key or not self.api_secret:
            logger.warning("API credentials not set in environment variables")

    def _init_notification_config(self):
        """Initialize notification configuration."""
        self.discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
        self.discord_error_webhook_url = os.getenv("DISCORD_ERROR_WEBHOOK_URL", "")  # Separate webhook for errors
        self.discord_enabled = os.getenv("DISCORD_ENABLED", "true").lower() == "true"

        self.email_enabled = os.getenv("EMAIL_ENABLED", "true").lower() == "true"
        self.email_smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.email_smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.email_use_tls = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
        self.email_username = os.getenv("EMAIL_USERNAME", "")
        self.email_password = os.getenv("EMAIL_PASSWORD", "")
        self.email_from = os.getenv("EMAIL_FROM", self.email_username)
        self.email_recipients = os.getenv("EMAIL_RECIPIENTS", "").split(",")

        # Load notification settings from YAML
        notifications_settings = self.settings.get("notifications", {})
        self.notifications = NotificationsConfig(**notifications_settings)

    def _init_database_config(self):
        """Initialize database configuration."""
        self.db_path = os.getenv("DB_PATH", "data/trading.db")

        # Create database directory if it doesn't exist
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    def _init_logging_config(self):
        """Initialize logging configuration."""
        # Environment-based log level: DEBUG for development, INFO for production
        default_log_level = "DEBUG" if self.environment == "testnet" else "INFO"
        self.log_level = os.getenv("LOG_LEVEL", default_log_level)
        
        self.log_file = os.getenv("LOG_FILE", "logs/trading.log")
        
        # Default to 500MB for log file size
        self.log_max_bytes = int(os.getenv("LOG_MAX_BYTES", "524288000"))  # 500MB
        self.log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
        
        # Error alerting configuration
        self.enable_error_alerts = os.getenv("ENABLE_ERROR_ALERTS", "true").lower() == "true"
        self.alert_throttle_seconds = int(os.getenv("ALERT_THROTTLE_SECONDS", "300"))  # 5 minutes

    def _init_trading_config(self):
        """Initialize trading configuration."""
        # Timeframes
        self.timeframes: List[str] = self.settings.get(
            "timeframes", ["5m", "15m", "1h", "4h", "1d"]
        )

        # Backtesting
        backtesting_settings = self.settings.get("backtesting", {})
        self.backtesting = BacktestingConfig(**backtesting_settings)

        # Risk management
        risk_settings = self.settings.get("risk_management", {})
        self.risk_management = RiskManagementConfig(**risk_settings)

        # GUI
        gui_settings = self.settings.get("gui", {})
        self.gui = GUIConfig(**gui_settings)

        # Terminal
        terminal_settings = self.settings.get("terminal", {})
        self.terminal = TerminalConfig(**terminal_settings)

        # Data fetching
        self.default_historical_days = int(os.getenv("DEFAULT_HISTORICAL_DAYS", "30"))

    def _init_firestore_config(self):
        """Initialize Firestore configuration for trade journaling."""
        from core.firestore_client import initialize_firestore
        
        # Load Firestore settings from YAML
        firestore_settings = self.settings.get("firestore", {})
        
        # Store Firestore configuration
        self.firestore_enabled = firestore_settings.get("enabled", True)
        self.firestore_service_account_path = firestore_settings.get(
            "service_account_path", 
            "config/firestore-service-account.json"
        )
        self.firestore_collection_name = firestore_settings.get("collection_name", "trades")
        
        # Initialize Firestore client
        if self.firestore_enabled:
            # Convert relative path to absolute
            if not os.path.isabs(self.firestore_service_account_path):
                self.firestore_service_account_path = os.path.join(
                    self.project_root, 
                    self.firestore_service_account_path
                )
            
            success = initialize_firestore(
                service_account_path=self.firestore_service_account_path,
                collection_name=self.firestore_collection_name,
                enabled=self.firestore_enabled
            )
            
            if success:
                logger.info("Firestore trade journaling initialized", 
                           collection=self.firestore_collection_name)
            else:
                logger.warning("Firestore trade journaling disabled due to initialization failure")
        else:
            logger.info("Firestore trade journaling is disabled in configuration")

    def is_testnet(self) -> bool:
        """Check if running in testnet mode."""
        return self.environment.lower() == "testnet"

    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"

    def validate(self) -> bool:
        """
        Validate configuration.

        Returns:
            True if configuration is valid

        Raises:
            ValidationError: If configuration is invalid
        """
        errors = []

        # Check API credentials
        if not self.api_key:
            errors.append("DELTA_API_KEY is not set")
        if not self.api_secret:
            errors.append("DELTA_API_SECRET is not set")

        # Check notification settings
        if self.discord_enabled and not self.discord_webhook_url:
            errors.append("Discord is enabled but DISCORD_WEBHOOK_URL is not set")

        if self.email_enabled:
            if not self.email_username:
                errors.append("Email is enabled but EMAIL_USERNAME is not set")
            if not self.email_password:
                errors.append("Email is enabled but EMAIL_PASSWORD is not set")
            if not self.email_recipients or not self.email_recipients[0]:
                errors.append("Email is enabled but EMAIL_RECIPIENTS is not set")

        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error("Configuration validation failed", errors=errors)
            raise ValidationError(error_msg)

        logger.info("Configuration validation successful")
        return True

    def __repr__(self) -> str:
        """Return string representation of configuration."""
        return (
            f"Config(environment={self.environment}, "
            f"base_url={self.base_url}, "
            f"timeframes={self.timeframes})"
        )


# Global configuration instance
_config: Optional[Config] = None


def get_config(env_file: Optional[str] = None, settings_file: Optional[str] = None) -> Config:
    """
    Get or create global configuration instance.

    Args:
        env_file: Path to .env file
        settings_file: Path to settings.yaml file

    Returns:
        Configuration instance
    """
    global _config
    if _config is None:
        _config = Config(env_file=env_file, settings_file=settings_file)
    return _config


if __name__ == "__main__":
    # Test configuration
    from .logger import setup_logging

    setup_logging(log_level="DEBUG")

    config = get_config()
    print(config)
    print(f"Testnet: {config.is_testnet()}")
    print(f"Timeframes: {config.timeframes}")
    print(f"Backtesting: {config.backtesting}")
    print(f"Risk Management: {config.risk_management}")
