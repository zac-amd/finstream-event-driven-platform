"""
OHLCV Candle Aggregator

Computes Open-High-Low-Close-Volume candles from trade stream.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict
from dataclasses import dataclass, field

from finstream_common.models import Trade, Candle
from finstream_common.logging import get_logger
from finstream_common.metrics import get_metrics

logger = get_logger(__name__)
metrics = get_metrics()


# Interval durations in seconds
INTERVAL_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


@dataclass
class CandleBuilder:
    """
    Builds a single candle from trades.
    """
    
    symbol: str
    interval: str
    bucket_start: datetime
    
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int = 0
    trade_count: int = 0
    value_sum: Decimal = field(default_factory=lambda: Decimal("0"))
    
    def add_trade(self, trade: Trade) -> None:
        """Add a trade to this candle."""
        price = trade.price
        
        if self.open is None:
            self.open = price
        
        if self.high is None or price > self.high:
            self.high = price
        
        if self.low is None or price < self.low:
            self.low = price
        
        self.close = price
        self.volume += trade.quantity
        self.trade_count += 1
        self.value_sum += price * trade.quantity
    
    def to_candle(self) -> Candle | None:
        """Convert builder to Candle model."""
        if self.open is None or self.close is None:
            return None
        
        # Calculate VWAP (round to 8 decimal places to match Pydantic model)
        vwap = self.value_sum / self.volume if self.volume > 0 else self.close
        vwap = round(vwap, 8)
        
        return Candle(
            symbol=self.symbol,
            interval=self.interval,
            open=self.open,
            high=self.high or self.open,
            low=self.low or self.open,
            close=self.close,
            volume=self.volume,
            trade_count=self.trade_count,
            vwap=vwap,
            timestamp=self.bucket_start,
        )
    
    @property
    def is_empty(self) -> bool:
        """Check if candle has no trades."""
        return self.trade_count == 0


class CandleAggregator:
    """
    Aggregates trades into OHLCV candles for multiple intervals.
    
    Features:
    - Time-bucketed aggregation
    - Multiple interval support
    - Automatic flushing of completed candles
    - VWAP calculation
    """
    
    def __init__(
        self,
        repository: "TradeRepository",
        intervals: list[str] | None = None,
    ) -> None:
        """
        Initialize aggregator.
        
        Args:
            repository: Database repository for persistence
            intervals: List of candle intervals (e.g., ["1m", "5m"])
        """
        self.repository = repository
        self.intervals = intervals or ["1m", "5m"]
        
        # Current candles being built: {interval: {symbol: CandleBuilder}}
        self._builders: Dict[str, Dict[str, CandleBuilder]] = {
            interval: {} for interval in self.intervals
        }
        
        # Validate intervals
        for interval in self.intervals:
            if interval not in INTERVAL_SECONDS:
                raise ValueError(f"Unknown interval: {interval}")
    
    def _get_bucket_start(self, timestamp: datetime, interval: str) -> datetime:
        """
        Get the start of the time bucket for a timestamp.
        
        Args:
            timestamp: Trade timestamp
            interval: Candle interval
            
        Returns:
            Start of the bucket
        """
        seconds = INTERVAL_SECONDS[interval]
        
        # Truncate to bucket
        epoch = timestamp.timestamp()
        bucket_epoch = (int(epoch) // seconds) * seconds
        
        return datetime.utcfromtimestamp(bucket_epoch)
    
    async def add_trade(self, trade: Trade) -> None:
        """
        Add a trade to all interval aggregations.
        
        Args:
            trade: Trade to add
        """
        for interval in self.intervals:
            bucket_start = self._get_bucket_start(trade.timestamp, interval)
            
            # Get or create builder
            if trade.symbol not in self._builders[interval]:
                self._builders[interval][trade.symbol] = CandleBuilder(
                    symbol=trade.symbol,
                    interval=interval,
                    bucket_start=bucket_start,
                )
            
            builder = self._builders[interval][trade.symbol]
            
            # Check if we need a new candle
            if builder.bucket_start != bucket_start:
                # Flush the old candle
                await self._flush_builder(builder)
                
                # Create new builder
                builder = CandleBuilder(
                    symbol=trade.symbol,
                    interval=interval,
                    bucket_start=bucket_start,
                )
                self._builders[interval][trade.symbol] = builder
            
            # Add trade to builder
            builder.add_trade(trade)
    
    async def _flush_builder(self, builder: CandleBuilder) -> bool:
        """
        Flush a candle builder to the database.
        
        Args:
            builder: CandleBuilder to flush
            
        Returns:
            True if candle was flushed
        """
        if builder.is_empty:
            return False
        
        candle = builder.to_candle()
        if candle is None:
            return False
        
        try:
            await self.repository.insert_candle(candle)
            
            # Update metrics
            metrics.candles_produced.labels(
                symbol=candle.symbol,
                interval=candle.interval,
            ).inc()
            
            metrics.last_candle_timestamp.labels(
                symbol=candle.symbol,
                interval=candle.interval,
            ).set(candle.timestamp.timestamp())
            
            logger.debug(
                "candle_produced",
                symbol=candle.symbol,
                interval=candle.interval,
                open=str(candle.open),
                close=str(candle.close),
                volume=candle.volume,
            )
            
            return True
            
        except Exception as e:
            logger.exception(
                "candle_flush_error",
                symbol=builder.symbol,
                interval=builder.interval,
                error=str(e),
            )
            return False
    
    async def flush_completed(self) -> int:
        """
        Flush all completed candles (where current time > bucket end).
        
        Returns:
            Number of candles flushed
        """
        now = datetime.utcnow()
        flushed = 0
        
        for interval in self.intervals:
            seconds = INTERVAL_SECONDS[interval]
            
            for symbol, builder in list(self._builders[interval].items()):
                bucket_end = builder.bucket_start + timedelta(seconds=seconds)
                
                if now >= bucket_end:
                    if await self._flush_builder(builder):
                        flushed += 1
                    
                    # Create new empty builder for next period
                    new_bucket = self._get_bucket_start(now, interval)
                    self._builders[interval][symbol] = CandleBuilder(
                        symbol=symbol,
                        interval=interval,
                        bucket_start=new_bucket,
                    )
        
        return flushed
    
    async def flush_all(self) -> int:
        """
        Flush all candles (even incomplete ones).
        
        Returns:
            Number of candles flushed
        """
        flushed = 0
        
        for interval in self.intervals:
            for builder in self._builders[interval].values():
                if await self._flush_builder(builder):
                    flushed += 1
            
            self._builders[interval] = {}
        
        return flushed
    
    def get_current_candles(self) -> Dict[str, Dict[str, dict]]:
        """
        Get current in-progress candles.
        
        Returns:
            Dict of interval -> symbol -> candle data
        """
        result = {}
        
        for interval, builders in self._builders.items():
            result[interval] = {}
            for symbol, builder in builders.items():
                if not builder.is_empty:
                    result[interval][symbol] = {
                        "open": str(builder.open),
                        "high": str(builder.high),
                        "low": str(builder.low),
                        "close": str(builder.close),
                        "volume": builder.volume,
                        "trade_count": builder.trade_count,
                        "bucket_start": builder.bucket_start.isoformat(),
                    }
        
        return result
