"""
FinStream Market Simulator - Main Application

Generates realistic financial market data and publishes to Kafka.
"""

import asyncio
import signal
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from finstream_common.config import get_settings
from finstream_common.kafka import KafkaProducer
from finstream_common.logging import setup_logging, get_logger
from finstream_common.metrics import setup_metrics, get_metrics
from finstream_common.tracing import setup_tracing

from app.generators.price_generator import MarketSimulator
from app.generators.trade_generator import TradeGenerator

# Initialize
settings = get_settings()
setup_logging(service_name="market-simulator", settings=settings)
setup_tracing(service_name="market-simulator", settings=settings)
metrics = setup_metrics(service_name="market-simulator", settings=settings)
logger = get_logger(__name__)


class SimulatorService:
    """
    Main service that orchestrates market simulation and Kafka publishing.
    """
    
    def __init__(self) -> None:
        self.producer: KafkaProducer | None = None
        self.market = MarketSimulator()
        self.trade_generator = TradeGenerator(self.market)
        self._running = False
        self._tasks: list[asyncio.Task] = []
        
        # Configuration
        self.batch_interval = 0.1  # 100ms between batches
        self.trades_per_batch = 50
        self.quotes_per_batch = 10  # Quotes for all symbols
    
    async def start(self) -> None:
        """Start the simulator service."""
        logger.info("starting_market_simulator")
        
        # Initialize Kafka producer
        self.producer = KafkaProducer()
        await self.producer.start()
        
        self._running = True
        
        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._trade_producer_loop()),
            asyncio.create_task(self._quote_producer_loop()),
            asyncio.create_task(self._stats_reporter_loop()),
        ]
        
        logger.info(
            "market_simulator_started",
            symbols=list(self.market.generators.keys()),
            batch_interval=self.batch_interval,
        )
    
    async def stop(self) -> None:
        """Stop the simulator service."""
        logger.info("stopping_market_simulator")
        
        self._running = False
        
        # Cancel tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Stop Kafka producer
        if self.producer:
            await self.producer.stop()
        
        logger.info("market_simulator_stopped")
    
    async def _trade_producer_loop(self) -> None:
        """Background loop that generates and publishes trades."""
        logger.info("trade_producer_loop_started")
        
        while self._running:
            try:
                # Generate batch of trades
                trades, _ = self.trade_generator.generate_batch(
                    batch_size=self.trades_per_batch
                )
                
                # Publish to Kafka
                for trade in trades:
                    await self.producer.send(
                        topic=settings.topic_trades,
                        value=trade.to_json(),
                        key=trade.symbol,
                    )
                    
                    # Update metrics
                    metrics.trades_produced.labels(
                        symbol=trade.symbol,
                        side=trade.side.value,
                    ).inc()
                    
                    metrics.trade_value.labels(
                        symbol=trade.symbol,
                        side=trade.side.value,
                    ).inc(float(trade.notional))
                    
                    metrics.trade_volume.labels(
                        symbol=trade.symbol,
                        side=trade.side.value,
                    ).inc(trade.quantity)
                
                metrics.kafka_messages_sent.labels(
                    topic=settings.topic_trades
                ).inc(len(trades))
                
                # Throttle
                await asyncio.sleep(self.batch_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("trade_producer_error", error=str(e))
                metrics.kafka_send_errors.labels(
                    topic=settings.topic_trades,
                    error_type=type(e).__name__,
                ).inc()
                await asyncio.sleep(1)  # Back off on error
    
    async def _quote_producer_loop(self) -> None:
        """Background loop that generates and publishes quotes."""
        logger.info("quote_producer_loop_started")
        
        while self._running:
            try:
                # Generate quotes for all symbols
                _, quotes = self.trade_generator.generate_batch(batch_size=1)
                
                # Publish to Kafka
                for quote in quotes:
                    await self.producer.send(
                        topic=settings.topic_quotes,
                        value=quote.to_json(),
                        key=quote.symbol,
                    )
                
                metrics.kafka_messages_sent.labels(
                    topic=settings.topic_quotes
                ).inc(len(quotes))
                
                # Quotes update less frequently than trades
                await asyncio.sleep(self.batch_interval * 2)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("quote_producer_error", error=str(e))
                await asyncio.sleep(1)
    
    async def _stats_reporter_loop(self) -> None:
        """Periodically log statistics."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Report every minute
                
                for symbol, generator in self.market.generators.items():
                    state = generator.state
                    logger.info(
                        "symbol_stats",
                        symbol=symbol,
                        price=round(state.price, 2),
                        high=round(state.high, 2),
                        low=round(state.low, 2),
                        volume=state.volume,
                        trade_count=state.trade_count,
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("stats_reporter_error", error=str(e))


# Global service instance
simulator_service = SimulatorService()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    # Startup
    await simulator_service.start()
    yield
    # Shutdown
    await simulator_service.stop()


# FastAPI application
app = FastAPI(
    title="FinStream Market Simulator",
    description="Generates realistic financial market data",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "market-simulator",
        "timestamp": datetime.utcnow().isoformat(),
        "running": simulator_service._running,
    }


@app.get("/ready")
async def readiness_check() -> dict:
    """Readiness check endpoint."""
    is_ready = (
        simulator_service._running
        and simulator_service.producer is not None
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


@app.get("/status")
async def status() -> dict:
    """Get current simulator status."""
    return {
        "running": simulator_service._running,
        "symbols": list(simulator_service.market.generators.keys()),
        "prices": {
            symbol: {
                "price": round(gen.state.price, 2),
                "bid": round(gen.state.bid_price, 2),
                "ask": round(gen.state.ask_price, 2),
                "high": round(gen.state.high, 2),
                "low": round(gen.state.low, 2),
                "volume": gen.state.volume,
                "trades": gen.state.trade_count,
            }
            for symbol, gen in simulator_service.market.generators.items()
        },
    }


def main() -> None:
    """Main entry point."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
        reload=settings.is_development,
    )


if __name__ == "__main__":
    main()
