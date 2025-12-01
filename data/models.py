"""Data models for the trading platform using Pydantic."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    """Order side enumeration."""

    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enumeration."""

    MARKET = "market_order"
    LIMIT = "limit_order"
    STOP_MARKET = "stop_market_order"
    STOP_LIMIT = "stop_limit_order"


class OrderStatus(str, Enum):
    """Order status enumeration."""

    OPEN = "open"
    PENDING = "pending"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"


class TradingMode(str, Enum):
    """Trading mode enumeration."""

    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class OHLCCandle(BaseModel):
    """OHLC candle data model."""

    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    symbol: Optional[str] = None
    timeframe: Optional[str] = None

    @field_validator("high")
    @classmethod
    def validate_high(cls, v, info):
        """Validate that high is >= low."""
        if "low" in info.data and v < info.data["low"]:
            raise ValueError("High must be >= low")
        return v

    @field_validator("low")
    @classmethod
    def validate_low(cls, v, info):
        """Validate that low is <= high."""
        if "high" in info.data and v > info.data["high"]:
            raise ValueError("Low must be <= high")
        return v

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class Ticker(BaseModel):
    """Ticker data model."""

    symbol: str
    timestamp: datetime
    price: float = Field(gt=0)
    bid: Optional[float] = Field(default=None, gt=0)
    ask: Optional[float] = Field(default=None, gt=0)
    volume_24h: Optional[float] = Field(default=None, ge=0)
    high_24h: Optional[float] = Field(default=None, gt=0)
    low_24h: Optional[float] = Field(default=None, gt=0)
    change_24h: Optional[float] = None

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class Position(BaseModel):
    """Position data model."""

    symbol: str
    product_id: int
    size: float  # Can be negative for short positions
    entry_price: float = Field(gt=0)
    current_price: Optional[float] = Field(default=None, gt=0)
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    margin: Optional[float] = Field(default=None, ge=0)
    leverage: Optional[int] = Field(default=None, gt=0)
    liquidation_price: Optional[float] = Field(default=None, gt=0)
    timestamp: datetime

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.size > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.size < 0

    @property
    def pnl(self) -> float:
        """Calculate total P&L."""
        unrealized = self.unrealized_pnl or 0
        realized = self.realized_pnl or 0
        return unrealized + realized

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class Order(BaseModel):
    """Order data model."""

    order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    symbol: str
    product_id: int
    side: OrderSide
    order_type: OrderType
    price: Optional[float] = Field(default=None, gt=0)
    quantity: float = Field(gt=0)
    filled_quantity: float = Field(default=0, ge=0)
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime
    filled_timestamp: Optional[datetime] = None
    average_fill_price: Optional[float] = Field(default=None, gt=0)
    commission: Optional[float] = Field(default=None, ge=0)

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_open(self) -> bool:
        """Check if order is open."""
        return self.status in [OrderStatus.OPEN, OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED]

    @property
    def remaining_quantity(self) -> float:
        """Calculate remaining quantity to be filled."""
        return self.quantity - self.filled_quantity

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class Trade(BaseModel):
    """Trade execution data model."""

    trade_id: str
    order_id: str
    symbol: str
    product_id: int
    side: OrderSide
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    commission: float = Field(ge=0)
    timestamp: datetime
    is_maker: bool = False

    @property
    def total_value(self) -> float:
        """Calculate total trade value."""
        return self.price * self.quantity

    @property
    def net_value(self) -> float:
        """Calculate net value after commission."""
        return self.total_value - self.commission

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class Product(BaseModel):
    """Product (trading instrument) data model."""

    product_id: int
    symbol: str
    description: Optional[str] = None
    contract_type: Optional[str] = None
    settling_asset: Optional[str] = None
    tick_size: Optional[float] = Field(default=None, gt=0)
    contract_value: Optional[float] = Field(default=None, gt=0)
    max_leverage: Optional[int] = Field(default=None, gt=0)
    is_active: bool = True

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class WalletBalance(BaseModel):
    """Wallet balance data model."""

    asset: str
    balance: float = Field(ge=0)
    available_balance: float = Field(ge=0)
    locked_balance: float = Field(default=0, ge=0)
    timestamp: datetime

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class Signal(BaseModel):
    """Trading signal data model."""

    timestamp: datetime
    symbol: str
    signal_type: str  # 'buy', 'sell', 'hold'
    strength: float = Field(ge=0, le=1)  # 0 to 1
    price: Optional[float] = Field(default=None, gt=0)
    strategy_name: str
    metadata: Optional[dict] = None

    class Config:
        """Pydantic model configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
