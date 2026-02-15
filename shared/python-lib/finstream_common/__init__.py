"""
FinStream Common Library
========================

Shared utilities for FinStream microservices including:
- Kafka producer/consumer clients
- Distributed tracing (OpenTelemetry)
- Prometheus metrics
- Structured logging
- Pydantic models for events
"""

from finstream_common.config import Settings, get_settings
from finstream_common.models import (
    Trade,
    Quote,
    Order,
    Candle,
    Alert,
    AlertType,
    AlertSeverity,
    OrderSide,
    OrderType,
    OrderStatus,
)
from finstream_common.kafka import KafkaProducer, KafkaConsumer
from finstream_common.tracing import setup_tracing, get_tracer
from finstream_common.metrics import setup_metrics, get_metrics
from finstream_common.logging import setup_logging, get_logger

__version__ = "0.1.0"
__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Models
    "Trade",
    "Quote",
    "Order",
    "Candle",
    "Alert",
    "AlertType",
    "AlertSeverity",
    "OrderSide",
    "OrderType",
    "OrderStatus",
    # Kafka
    "KafkaProducer",
    "KafkaConsumer",
    # Observability
    "setup_tracing",
    "get_tracer",
    "setup_metrics",
    "get_metrics",
    "setup_logging",
    "get_logger",
]
