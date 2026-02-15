"""
Database repository for trades and candles.

Uses asyncpg for async PostgreSQL/TimescaleDB operations.
"""

from datetime import datetime
from decimal import Decimal
from typing import List

import asyncpg

from finstream_common.config import get_settings
from finstream_common.logging import get_logger
from finstream_common.metrics import get_metrics
from finstream_common.models import Trade, Candle, Quote

logger = get_logger(__name__)
metrics = get_metrics()
settings = get_settings()


class TradeRepository:
    """
    Repository for persisting trades and candles to TimescaleDB.
    """
    
    def __init__(self, dsn: str | None = None) -> None:
        """
        Initialize repository.
        
        Args:
            dsn: Database connection string
        """
        self.dsn = dsn or settings.timescale_url
        self.pool: asyncpg.Pool | None = None
    
    async def connect(self) -> None:
        """Create connection pool."""
        logger.info("connecting_to_database", dsn=self.dsn[:30] + "...")
        
        self.pool = await asyncpg.create_pool(
            dsn=self.dsn,
            min_size=5,
            max_size=settings.timescale_pool_size,
            command_timeout=30,
        )
        
        logger.info("database_connected")
    
    async def close(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("database_disconnected")
    
    async def insert_trades(self, trades: List[Trade]) -> int:
        """
        Batch insert trades.
        
        Args:
            trades: List of trades to insert
            
        Returns:
            Number of inserted trades
        """
        if not trades:
            return 0
        
        query = """
            INSERT INTO trades (symbol, timestamp, trade_id, price, quantity, side, exchange)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (symbol, timestamp, trade_id) DO NOTHING
        """
        
        records = [
            (
                trade.symbol,
                trade.timestamp,
                trade.trade_id,
                float(trade.price),
                trade.quantity,
                trade.side.value,
                trade.exchange,
            )
            for trade in trades
        ]
        
        try:
            async with self.pool.acquire() as conn:
                await conn.executemany(query, records)
            
            metrics.db_queries.labels(
                operation="insert",
                table="trades",
            ).inc()
            
            return len(trades)
            
        except Exception as e:
            logger.exception("trade_insert_error", error=str(e))
            raise
    
    async def insert_candle(self, candle: Candle) -> None:
        """
        Insert or update a candle.
        
        Args:
            candle: Candle to insert
        """
        query = """
            INSERT INTO candles (timestamp, symbol, interval, open, high, low, close, volume, trade_count, vwap)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (timestamp, symbol, interval) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                trade_count = EXCLUDED.trade_count,
                vwap = EXCLUDED.vwap
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    candle.timestamp,
                    candle.symbol,
                    candle.interval,
                    float(candle.open),
                    float(candle.high),
                    float(candle.low),
                    float(candle.close),
                    candle.volume,
                    candle.trade_count,
                    float(candle.vwap) if candle.vwap else None,
                )
            
            metrics.db_queries.labels(
                operation="upsert",
                table="candles",
            ).inc()
            
        except Exception as e:
            logger.exception("candle_insert_error", error=str(e))
            raise
    
    async def insert_quote(self, quote: Quote) -> None:
        """
        Insert a quote.
        
        Args:
            quote: Quote to insert
        """
        query = """
            INSERT INTO quotes (timestamp, symbol, bid_price, bid_size, ask_price, ask_size, exchange)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """
        
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    query,
                    quote.timestamp,
                    quote.symbol,
                    float(quote.bid_price),
                    quote.bid_size,
                    float(quote.ask_price),
                    quote.ask_size,
                    quote.exchange,
                )
            
            metrics.db_queries.labels(
                operation="insert",
                table="quotes",
            ).inc()
            
        except Exception as e:
            logger.exception("quote_insert_error", error=str(e))
            raise
    
    async def get_latest_trades(
        self,
        symbol: str,
        limit: int = 100,
    ) -> List[dict]:
        """
        Get latest trades for a symbol.
        
        Args:
            symbol: Trading symbol
            limit: Maximum number of trades
            
        Returns:
            List of trade dictionaries
        """
        query = """
            SELECT timestamp, trade_id, symbol, price, quantity, side, exchange
            FROM trades
            WHERE symbol = $1
            ORDER BY timestamp DESC
            LIMIT $2
        """
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, symbol, limit)
            
            metrics.db_queries.labels(
                operation="select",
                table="trades",
            ).inc()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.exception("get_trades_error", error=str(e))
            raise
    
    async def get_candles(
        self,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 500,
    ) -> List[dict]:
        """
        Get candles for a symbol.
        
        Args:
            symbol: Trading symbol
            interval: Candle interval
            start_time: Start timestamp
            end_time: End timestamp
            limit: Maximum number of candles
            
        Returns:
            List of candle dictionaries
        """
        query = """
            SELECT timestamp, symbol, interval, open, high, low, close, volume, trade_count, vwap
            FROM candles
            WHERE symbol = $1 AND interval = $2
        """
        params = [symbol, interval]
        
        if start_time:
            query += f" AND timestamp >= ${len(params) + 1}"
            params.append(start_time)
        
        if end_time:
            query += f" AND timestamp <= ${len(params) + 1}"
            params.append(end_time)
        
        query += f" ORDER BY timestamp DESC LIMIT ${len(params) + 1}"
        params.append(limit)
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
            
            metrics.db_queries.labels(
                operation="select",
                table="candles",
            ).inc()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            logger.exception("get_candles_error", error=str(e))
            raise
    
    async def get_market_stats(self, symbol: str) -> dict | None:
        """
        Get market statistics for a symbol using continuous aggregate.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Market stats dictionary
        """
        query = """
            SELECT 
                symbol,
                close as current_price,
                high as high_price,
                low as low_price,
                vwap,
                volume as total_volume,
                trade_count,
                timestamp
            FROM candles_1m
            WHERE symbol = $1
            ORDER BY timestamp DESC
            LIMIT 1
        """
        
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, symbol)
            
            if row:
                return dict(row)
            return None
            
        except Exception as e:
            logger.exception("get_market_stats_error", error=str(e))
            return None
    
    async def health_check(self) -> bool:
        """Check database connection health."""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False
