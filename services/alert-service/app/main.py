"""
FinStream Alert Service - Main Application

Monitors trades and quotes for anomalies and publishes alerts.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncIterator

import uvicorn
import redis.asyncio as redis
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from finstream_common.config import get_settings
from finstream_common.kafka import KafkaConsumer, KafkaProducer
from finstream_common.logging import setup_logging, get_logger
from finstream_common.metrics import setup_metrics, get_metrics
from finstream_common.tracing import setup_tracing
from finstream_common.models import Trade, Quote

from app.detector import AlertDetector

# Initialize
settings = get_settings()
setup_logging(service_name="alert-service", settings=settings)
setup_tracing(service_name="alert-service", settings=settings)
metrics = setup_metrics(service_name="alert-service", settings=settings)
logger = get_logger(__name__)


class AlertService:
    """
    Main service that monitors market data for anomalies.
    """
    
    def __init__(self) -> None:
        self.trade_consumer: KafkaConsumer | None = None
        self.quote_consumer: KafkaConsumer | None = None
        self.producer: KafkaProducer | None = None
        self.redis_client: redis.Redis | None = None
        self.detector = AlertDetector()
        self._running = False
        self._tasks: list[asyncio.Task] = []
        
        # Statistics
        self.trades_processed = 0
        self.quotes_processed = 0
        self.alerts_generated = 0
    
    async def start(self) -> None:
        """Start the alert service."""
        logger.info("starting_alert_service")
        
        # Initialize Redis for pub/sub
        self.redis_client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        
        # Initialize Kafka producer for alert topic
        self.producer = KafkaProducer()
        await self.producer.start()
        
        # Initialize Kafka consumers
        self.trade_consumer = KafkaConsumer(
            topics=[settings.topic_trades],
            group_id="alert-service-trades",
        )
        await self.trade_consumer.start()
        
        self.quote_consumer = KafkaConsumer(
            topics=[settings.topic_quotes],
            group_id="alert-service-quotes",
        )
        await self.quote_consumer.start()
        
        self._running = True
        
        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._trade_monitor_loop()),
            asyncio.create_task(self._quote_monitor_loop()),
        ]
        
        logger.info("alert_service_started")
    
    async def stop(self) -> None:
        """Stop the alert service."""
        logger.info("stopping_alert_service")
        
        self._running = False
        
        # Cancel tasks
        for task in self._tasks:
            task.cancel()
        
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # Stop consumers
        if self.trade_consumer:
            await self.trade_consumer.stop()
        if self.quote_consumer:
            await self.quote_consumer.stop()
        
        # Stop producer
        if self.producer:
            await self.producer.stop()
        
        # Close Redis
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("alert_service_stopped")
    
    async def _trade_monitor_loop(self) -> None:
        """Monitor trades for anomalies."""
        logger.info("trade_monitor_loop_started")
        
        while self._running:
            try:
                async for msg in self.trade_consumer.messages():
                    if not self._running:
                        break
                    
                    try:
                        # Deserialize trade
                        trade = Trade.from_json(msg["value"])
                        
                        # Process through detector
                        alert = self.detector.process_trade(trade)
                        
                        self.trades_processed += 1
                        
                        if alert:
                            await self._publish_alert(alert)
                            self.alerts_generated += 1
                        
                    except Exception as e:
                        logger.exception("trade_monitor_error", error=str(e))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("trade_consumer_error", error=str(e))
                await asyncio.sleep(1)
    
    async def _quote_monitor_loop(self) -> None:
        """Monitor quotes for spread anomalies."""
        logger.info("quote_monitor_loop_started")
        
        while self._running:
            try:
                async for msg in self.quote_consumer.messages():
                    if not self._running:
                        break
                    
                    try:
                        # Deserialize quote
                        quote = Quote.from_json(msg["value"])
                        
                        # Process through detector
                        alert = self.detector.process_quote(quote)
                        
                        self.quotes_processed += 1
                        
                        if alert:
                            await self._publish_alert(alert)
                            self.alerts_generated += 1
                        
                    except Exception as e:
                        logger.exception("quote_monitor_error", error=str(e))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("quote_consumer_error", error=str(e))
                await asyncio.sleep(1)
    
    async def _publish_alert(self, alert) -> None:
        """Publish alert to Kafka and Redis pub/sub."""
        try:
            # Publish to Kafka alerts topic
            await self.producer.send(
                topic=settings.topic_alerts,
                value=alert.to_json(),
                key=alert.symbol,
            )
            
            metrics.kafka_messages_sent.labels(
                topic=settings.topic_alerts
            ).inc()
            
            # Publish to Redis for real-time WebSocket delivery
            await self.redis_client.publish(
                f"alerts:{alert.symbol}",
                alert.to_json().decode(),
            )
            
            # Also publish to global alerts channel
            await self.redis_client.publish(
                "alerts:all",
                alert.to_json().decode(),
            )
            
            logger.info(
                "alert_published",
                alert_id=alert.alert_id,
                symbol=alert.symbol,
                type=alert.alert_type.value,
                severity=alert.severity.value,
            )
            
        except Exception as e:
            logger.exception("alert_publish_error", error=str(e))


# Global service instance
alert_service = AlertService()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager."""
    await alert_service.start()
    yield
    await alert_service.stop()


# FastAPI application
app = FastAPI(
    title="FinStream Alert Service",
    description="Monitors market data for anomalies and generates alerts",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "alert-service",
        "timestamp": datetime.utcnow().isoformat(),
        "running": alert_service._running,
    }


@app.get("/ready")
async def readiness_check() -> dict:
    """Readiness check endpoint."""
    is_ready = (
        alert_service._running
        and alert_service.trade_consumer is not None
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
    """Get service statistics."""
    return {
        "running": alert_service._running,
        "trades_processed": alert_service.trades_processed,
        "quotes_processed": alert_service.quotes_processed,
        "alerts_generated": alert_service.alerts_generated,
        "detector_stats": alert_service.detector.get_all_stats(),
    }


@app.get("/stats/{symbol}")
async def symbol_stats(symbol: str) -> dict:
    """Get statistics for a specific symbol."""
    stats = alert_service.detector.get_stats(symbol.upper())
    if stats is None:
        return {"error": f"No statistics available for {symbol}"}
    return stats


def main() -> None:
    """Main entry point."""
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,
        log_level="info",
        reload=settings.is_development,
    )


if __name__ == "__main__":
    main()
