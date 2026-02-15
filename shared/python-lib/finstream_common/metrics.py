"""
Prometheus metrics for FinStream services.
"""

from functools import wraps
from time import perf_counter
from typing import Any, Callable, TypeVar

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    multiprocess,
    REGISTRY,
)

from finstream_common.config import Settings, get_settings

F = TypeVar("F", bound=Callable[..., Any])

# Default buckets for latency histograms (in seconds)
LATENCY_BUCKETS = (
    0.001,  # 1ms
    0.005,  # 5ms
    0.01,   # 10ms
    0.025,  # 25ms
    0.05,   # 50ms
    0.1,    # 100ms
    0.25,   # 250ms
    0.5,    # 500ms
    1.0,    # 1s
    2.5,    # 2.5s
    5.0,    # 5s
    10.0,   # 10s
)


class FinStreamMetrics:
    """
    Centralized metrics collection for FinStream services.

    Provides pre-defined metrics for:
    - Trade processing
    - Kafka operations
    - HTTP requests
    - Database operations
    - Business metrics
    """

    def __init__(
        self,
        service_name: str,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self.service_name = service_name
        self.registry = registry or REGISTRY

        # Service info
        self.info = Info(
            "finstream_service",
            "Service information",
            registry=self.registry,
        )
        self.info.info({
            "service": service_name,
            "version": "0.1.0",
        })

        # =================================================================
        # Trade Metrics
        # =================================================================
        self.trades_produced = Counter(
            "finstream_trades_produced_total",
            "Total number of trades produced to Kafka",
            ["symbol", "side"],
            registry=self.registry,
        )

        self.trades_processed = Counter(
            "finstream_trades_processed_total",
            "Total number of trades processed",
            ["symbol", "processor"],
            registry=self.registry,
        )

        self.trade_value = Counter(
            "finstream_trade_value_total",
            "Total value of trades processed",
            ["symbol", "side"],
            registry=self.registry,
        )

        self.trade_volume = Counter(
            "finstream_trade_volume_total",
            "Total volume of trades processed",
            ["symbol", "side"],
            registry=self.registry,
        )

        # =================================================================
        # Processing Latency Metrics
        # =================================================================
        self.processing_latency = Histogram(
            "finstream_processing_latency_seconds",
            "Processing latency in seconds",
            ["operation", "status"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        self.end_to_end_latency = Histogram(
            "finstream_end_to_end_latency_seconds",
            "End-to-end latency from trade generation to processing",
            ["symbol"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        # =================================================================
        # Kafka Metrics
        # =================================================================
        self.kafka_messages_sent = Counter(
            "finstream_kafka_messages_sent_total",
            "Total Kafka messages sent",
            ["topic"],
            registry=self.registry,
        )

        self.kafka_messages_received = Counter(
            "finstream_kafka_messages_received_total",
            "Total Kafka messages received",
            ["topic", "consumer_group"],
            registry=self.registry,
        )

        self.kafka_send_errors = Counter(
            "finstream_kafka_send_errors_total",
            "Total Kafka send errors",
            ["topic", "error_type"],
            registry=self.registry,
        )

        self.kafka_consumer_lag = Gauge(
            "finstream_kafka_consumer_lag",
            "Kafka consumer lag per partition",
            ["topic", "partition", "consumer_group"],
            registry=self.registry,
        )

        # =================================================================
        # Candle/Aggregation Metrics
        # =================================================================
        self.candles_produced = Counter(
            "finstream_candles_produced_total",
            "Total candles produced",
            ["symbol", "interval"],
            registry=self.registry,
        )

        self.candle_aggregation_duration = Histogram(
            "finstream_candle_aggregation_duration_seconds",
            "Duration of candle aggregation",
            ["interval"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        self.last_candle_timestamp = Gauge(
            "finstream_last_candle_timestamp",
            "Timestamp of last produced candle",
            ["symbol", "interval"],
            registry=self.registry,
        )

        # =================================================================
        # Alert Metrics
        # =================================================================
        self.alerts_triggered = Counter(
            "finstream_alerts_triggered_total",
            "Total alerts triggered",
            ["alert_type", "severity", "symbol"],
            registry=self.registry,
        )

        # =================================================================
        # HTTP Metrics
        # =================================================================
        self.http_requests = Counter(
            "finstream_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status"],
            registry=self.registry,
        )

        self.http_request_duration = Histogram(
            "finstream_http_request_duration_seconds",
            "HTTP request duration",
            ["method", "endpoint"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        self.http_requests_in_progress = Gauge(
            "finstream_http_requests_in_progress",
            "Number of HTTP requests in progress",
            ["method", "endpoint"],
            registry=self.registry,
        )

        # =================================================================
        # Database Metrics
        # =================================================================
        self.db_queries = Counter(
            "finstream_db_queries_total",
            "Total database queries",
            ["operation", "table"],
            registry=self.registry,
        )

        self.db_query_duration = Histogram(
            "finstream_db_query_duration_seconds",
            "Database query duration",
            ["operation", "table"],
            buckets=LATENCY_BUCKETS,
            registry=self.registry,
        )

        self.db_connections_active = Gauge(
            "finstream_db_connections_active",
            "Number of active database connections",
            registry=self.registry,
        )

        # =================================================================
        # Cache Metrics
        # =================================================================
        self.cache_hits = Counter(
            "finstream_cache_hits_total",
            "Total cache hits",
            ["cache_name"],
            registry=self.registry,
        )

        self.cache_misses = Counter(
            "finstream_cache_misses_total",
            "Total cache misses",
            ["cache_name"],
            registry=self.registry,
        )

        # =================================================================
        # WebSocket Metrics
        # =================================================================
        self.ws_connections_active = Gauge(
            "finstream_ws_connections_active",
            "Number of active WebSocket connections",
            ["channel"],
            registry=self.registry,
        )

        self.ws_messages_sent = Counter(
            "finstream_ws_messages_sent_total",
            "Total WebSocket messages sent",
            ["channel"],
            registry=self.registry,
        )

    def timed(
        self,
        operation: str,
        success_status: str = "success",
        error_status: str = "error",
    ) -> Callable[[F], F]:
        """
        Decorator to time a function and record to processing_latency histogram.

        Usage:
            @metrics.timed("process_trade")
            async def process_trade(trade):
                ...
        """

        def decorator(func: F) -> F:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    self.processing_latency.labels(
                        operation=operation,
                        status=success_status,
                    ).observe(perf_counter() - start)
                    return result
                except Exception:
                    self.processing_latency.labels(
                        operation=operation,
                        status=error_status,
                    ).observe(perf_counter() - start)
                    raise

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = perf_counter()
                try:
                    result = func(*args, **kwargs)
                    self.processing_latency.labels(
                        operation=operation,
                        status=success_status,
                    ).observe(perf_counter() - start)
                    return result
                except Exception:
                    self.processing_latency.labels(
                        operation=operation,
                        status=error_status,
                    ).observe(perf_counter() - start)
                    raise

            import asyncio

            if asyncio.iscoroutinefunction(func):
                return async_wrapper  # type: ignore
            return sync_wrapper  # type: ignore

        return decorator


# Global metrics instance
_metrics: FinStreamMetrics | None = None


def setup_metrics(
    service_name: str | None = None,
    settings: Settings | None = None,
) -> FinStreamMetrics:
    """
    Initialize metrics collection.

    Args:
        service_name: Service name for metrics labels
        settings: Settings instance

    Returns:
        FinStreamMetrics instance
    """
    global _metrics

    settings = settings or get_settings()
    service_name = service_name or settings.service_name

    if _metrics is None:
        _metrics = FinStreamMetrics(service_name)

    return _metrics


def get_metrics() -> FinStreamMetrics:
    """Get the global metrics instance."""
    global _metrics

    if _metrics is None:
        _metrics = setup_metrics()

    return _metrics


def generate_metrics() -> tuple[bytes, str]:
    """
    Generate Prometheus metrics output.

    Returns:
        Tuple of (metrics bytes, content type)
    """
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
