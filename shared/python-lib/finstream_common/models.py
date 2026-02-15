"""
Pydantic models for FinStream events and entities.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

import orjson
from pydantic import BaseModel, Field, field_validator


def orjson_dumps(v: Any, *, default: Any) -> str:
    """Custom JSON serializer using orjson for performance."""
    return orjson.dumps(v, default=default).decode()


class BaseEvent(BaseModel):
    """Base class for all events with common fields."""

    class Config:
        json_encoders = {
            Decimal: str,
            datetime: lambda v: v.isoformat(),
        }
        populate_by_name = True

    def to_json(self) -> bytes:
        """Serialize to JSON bytes for Kafka."""
        return orjson.dumps(self.model_dump(mode="json"))

    @classmethod
    def from_json(cls, data: bytes) -> "BaseEvent":
        """Deserialize from JSON bytes."""
        return cls.model_validate(orjson.loads(data))


# =============================================================================
# ENUMS
# =============================================================================


class OrderSide(str, Enum):
    """Order side - buy or sell."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    """Order status."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class AlertType(str, Enum):
    """Alert type."""

    PRICE_SPIKE = "PRICE_SPIKE"
    VOLUME_ANOMALY = "VOLUME_ANOMALY"
    SPREAD_ANOMALY = "SPREAD_ANOMALY"
    CUSTOM = "CUSTOM"


class AlertSeverity(str, Enum):
    """Alert severity level."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CandleInterval(str, Enum):
    """Candle interval."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


# =============================================================================
# EVENTS
# =============================================================================


class Trade(BaseEvent):
    """
    Trade event representing a single executed trade.

    Attributes:
        trade_id: Unique identifier for the trade
        symbol: Trading symbol (e.g., AAPL, GOOGL)
        price: Execution price
        quantity: Number of shares/units traded
        side: Buy or sell
        exchange: Exchange where trade occurred
        timestamp: When the trade occurred
        trace_id: Distributed tracing ID
    """

    trade_id: str = Field(default_factory=lambda: f"T-{uuid4().hex[:12].upper()}")
    symbol: str = Field(..., min_length=1, max_length=10)
    price: Decimal = Field(..., gt=0, decimal_places=8)
    quantity: int = Field(..., gt=0)
    side: OrderSide
    exchange: str = Field(default="NASDAQ")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Ensure symbol is uppercase."""
        return v.upper().strip()

    @property
    def notional(self) -> Decimal:
        """Calculate notional value (price * quantity)."""
        return self.price * self.quantity


class Quote(BaseEvent):
    """
    Quote event representing bid/ask prices.

    Attributes:
        symbol: Trading symbol
        bid_price: Best bid price
        bid_size: Size at best bid
        ask_price: Best ask price
        ask_size: Size at best ask
        exchange: Exchange providing the quote
        timestamp: Quote timestamp
    """

    symbol: str = Field(..., min_length=1, max_length=10)
    bid_price: Decimal = Field(..., ge=0, decimal_places=8)
    bid_size: int = Field(..., ge=0)
    ask_price: Decimal = Field(..., ge=0, decimal_places=8)
    ask_size: int = Field(..., ge=0)
    exchange: str = Field(default="NASDAQ")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("symbol", mode="before")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Ensure symbol is uppercase."""
        return v.upper().strip()

    @property
    def spread(self) -> Decimal:
        """Calculate bid-ask spread."""
        return self.ask_price - self.bid_price

    @property
    def spread_pct(self) -> Decimal:
        """Calculate spread as percentage of mid price."""
        mid = (self.bid_price + self.ask_price) / 2
        if mid == 0:
            return Decimal(0)
        return (self.spread / mid) * 100

    @property
    def mid_price(self) -> Decimal:
        """Calculate mid price."""
        return (self.bid_price + self.ask_price) / 2


class Order(BaseEvent):
    """
    Order event representing a trading order.

    Attributes:
        order_id: Unique order identifier
        symbol: Trading symbol
        order_type: Type of order (market, limit, etc.)
        side: Buy or sell
        price: Limit price (optional for market orders)
        quantity: Order quantity
        filled_quantity: Quantity filled so far
        status: Current order status
        timestamp: Order creation timestamp
        trace_id: Distributed tracing ID
    """

    order_id: str = Field(default_factory=lambda: f"O-{uuid4().hex[:12].upper()}")
    symbol: str = Field(..., min_length=1, max_length=10)
    order_type: OrderType
    side: OrderSide
    price: Decimal | None = Field(default=None, ge=0, decimal_places=8)
    quantity: int = Field(..., gt=0)
    filled_quantity: int = Field(default=0, ge=0)
    status: OrderStatus = Field(default=OrderStatus.PENDING)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    trace_id: str | None = None

    @field_validator("symbol", mode="before")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Ensure symbol is uppercase."""
        return v.upper().strip()

    @property
    def remaining_quantity(self) -> int:
        """Calculate remaining quantity to fill."""
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        """Check if order is complete (filled or cancelled)."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )


class Candle(BaseEvent):
    """
    OHLCV candlestick data.

    Attributes:
        symbol: Trading symbol
        interval: Candle interval (1m, 5m, etc.)
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Total volume
        trade_count: Number of trades in candle
        vwap: Volume-weighted average price
        timestamp: Candle start timestamp
    """

    symbol: str = Field(..., min_length=1, max_length=10)
    interval: str = Field(..., pattern=r"^(1m|5m|15m|1h|4h|1d)$")
    open: Decimal = Field(..., ge=0, decimal_places=8)
    high: Decimal = Field(..., ge=0, decimal_places=8)
    low: Decimal = Field(..., ge=0, decimal_places=8)
    close: Decimal = Field(..., ge=0, decimal_places=8)
    volume: int = Field(..., ge=0)
    trade_count: int = Field(..., ge=0)
    vwap: Decimal | None = Field(default=None, ge=0, decimal_places=8)
    timestamp: datetime

    @field_validator("symbol", mode="before")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Ensure symbol is uppercase."""
        return v.upper().strip()

    @property
    def range(self) -> Decimal:
        """Calculate high-low range."""
        return self.high - self.low

    @property
    def body(self) -> Decimal:
        """Calculate candle body (close - open)."""
        return self.close - self.open

    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish (close > open)."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Check if candle is bearish (close < open)."""
        return self.close < self.open


class Alert(BaseEvent):
    """
    Alert event for anomalies and notifications.

    Attributes:
        alert_id: Unique alert identifier
        alert_type: Type of alert
        symbol: Related trading symbol
        severity: Alert severity level
        message: Human-readable alert message
        details: Additional alert details
        timestamp: When alert was triggered
    """

    alert_id: str = Field(default_factory=lambda: f"A-{uuid4().hex[:12].upper()}")
    alert_type: AlertType
    symbol: str = Field(..., min_length=1, max_length=10)
    severity: AlertSeverity
    message: str
    details: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("symbol", mode="before")
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Ensure symbol is uppercase."""
        return v.upper().strip()


# =============================================================================
# AGGREGATES / VALUE OBJECTS
# =============================================================================


class MarketStats(BaseModel):
    """Market statistics for a symbol."""

    symbol: str
    current_price: Decimal
    high_price: Decimal
    low_price: Decimal
    vwap: Decimal
    total_volume: int
    trade_count: int
    price_change: Decimal
    price_change_pct: Decimal
    timestamp: datetime


class SymbolInfo(BaseModel):
    """Symbol reference data."""

    symbol: str
    name: str
    exchange: str
    asset_type: str
    currency: str = "USD"
    is_active: bool = True
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.01")
