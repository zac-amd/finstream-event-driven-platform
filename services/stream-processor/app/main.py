"""
FinStream Stream Processor - Main Application

Consumes trades from Kafka, computes OHLCV candles, stores in TimescaleDB.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from finstream_common.config import get_settings
from finstream_common.kafka import KafkaConsumer
from finstream_common.logging import setup_logging, get_logger
from finstream_common.metrics import setup_metrics, get_metrics
from finstream_common.tracing import setup_tracing
from finstream_common.models import Trade

from app.aggregator import CandleAggregator
from app.repository import TradeRepository

# Initialize
settings = get_settings()
setup_logging(service_name="stream-processor", settings=settings)
setup_tracing(service_name="stream-processor", settings=settings)
metrics = setup_metrics(service_name="stream-processor", settings=settings)
logger = get_logger(__name__)


class StreamProcessorService:
    """
    Main service that processes trade stream and computes aggregations.
    """
    
    def __init__(self) -> None:
        self.consumer: KafkaConsumer | None = None
        self.repository: TradeRepository | None = None
        self.aggregator: CandleAggregator | None = None
        self._running = False
        self._tasks: list[asyncio.Task] = []
        
        # Statistics
        self.trades_processed = 0
        self.candles_produced = 0
        self.last_trade_time: datetime | None = None
    
    async def start(self) -> None:
        """Start the stream processor service."""
        logger.info("starting_stream_processor")
        
        # Initialize repository
        self.repository = TradeRepository()
        await self.repository.connect()
        
        # Initialize aggregator
        self.aggregator = CandleAggregator(
            repository=self.repository,
            intervals=["1m", "5m"],
        )
        
        # Initialize Kafka consumer
        self.consumer = KafkaConsumer(
            topics=[settings.topic_trades],
            group_id="stream-processor-group",
        )
        await self.consumer.start()
        
        self._running = True
        
        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._trade_consumer_loop()),
            asyncio.create_task(self._candle_flush_loop()),
        ]
        
        logger.info("stream_processor_started")
    
    async def stop(self) -> None:
        """Stop the stream processor service."""
        logger.info("stopping_stream_processor")
        
        self._running = False
        
        # Cancel tasks
        for task in self._tasks:
            task.cancel()
        
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Flush remaining candles
        if self.aggregator:
            await self.aggregator.flush_all()
        
        # Stop Kafka consumer
        if self.consumer:
            await self.consumer.stop()
        
        # Close repository
        if self.repository:
            await self.repository.close()
        
        logger.info("stream_processor_stopped")
    
    async def _trade_consumer_loop(self) -> None:
        """Background loop that consumes and processes trades."""
        logger.info("trade_consumer_loop_started")
        
        batch: list[Trade] = []
        batch_size = 100
        
        while self._running:
            try:
                async for msg in self.consumer.messages():
                    if not self._running:
                        break
                    
                    try:
                        # Deserialize trade
                        trade = Trade.from_json(msg["value"])
                        
                        # Update metrics
                        metrics.trades_processed.labels(
                            symbol=trade.symbol,
                            processor="stream-processor",
                        ).inc()
                        
                        metrics.kafka_messages_received.labels(
                            topic=settings.topic_trades,
                            consumer_group="stream-processor-group",
                        ).inc()
                        
                        # Add to aggregator
                        await self.aggregator.add_trade(trade)
                        
                        # Batch for DB insert
                        batch.append(trade)
                        
                        if len(batch) >= batch_size:
                            # Insert batch to DB
                            await self.repository.insert_trades(batch)
                            batch = []
                            
                            # Commit offsets
                            await self.consumer.commit()
                        
                        self.trades_processed += 1
                        self.last_trade_time = trade.timestamp
                        
                    except Exception as e:
                        logger.exception(
                            "trade_processing_error",
                            error=str(e),
                            offset=msg["offset"],
                        )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("consumer_loop_error", error=str(e))
                await asyncio.sleep(1)  # Back off on error
        
        # Insert remaining batch
        if batch:
            await self.repository.insert_trades(batch)
    
    async def _candle_flush_loop(self) -> None:
        """Periodically flush completed candles to database."""
        while self._running:
            try:
                await asyncio.sleep(5)  # Flush every 5 seconds
                
                if self.aggregator:
                    flushed = await self.aggregator.flush_completed()
                    self.candles_produced += flushed
                    
                    if flushed > 0:
                        logger.info("candles_flushed", count=flushed)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("candle_flush_error", error=str(e))


# Global service instance
processor_service = StreamProcessorService()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    await processor_service.start()
    yield
    await processor_service.stop()


# FastAPI application
app = FastAPI(
    title="FinStream Stream Processor",
    description="Processes trades and computes OHLCV candles",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "stream-processor",
        "timestamp": datetime.utcnow().isoformat(),
        "running": processor_service._running,
    }


@app.get("/ready")
async def readiness_check() -> dict:
    """Readiness check endpoint."""
    is_ready = (
        processor_service._running
        and processor_service.consumer is not None
        and processor_service.repository is not None
    )
    return {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/metrics")
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/stats")
async def stats() -> dict:
    """Get processing statistics."""
    return {
        "running": processor_service._running,
        "trades_processed": processor_service.trades_processed,
        "candles_produced": processor_service.candles_produced,
        "last_trade_time": (
            processor_service.last_trade_time.isoformat()
            if processor_service.last_trade_time
            else None
        ),
    }


def main() -> None:
    """Main entry point."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        log_level="info",
        reload=settings.is_development,
    )


if __name__ == "__main__":
    main()
