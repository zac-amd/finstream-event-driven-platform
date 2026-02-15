"""
Distributed tracing using OpenTelemetry with Jaeger exporter.
"""

from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, TypeVar

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.trace import Status, StatusCode, Span, Tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from finstream_common.config import Settings, get_settings

# Context variable for current trace ID
_current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)

# Global tracer instance
_tracer: Tracer | None = None
_initialized = False

F = TypeVar("F", bound=Callable[..., Any])


def setup_tracing(
    service_name: str | None = None,
    settings: Settings | None = None,
) -> Tracer:
    """
    Initialize OpenTelemetry tracing with Jaeger exporter.

    Args:
        service_name: Name of the service for tracing
        settings: Settings instance (uses default if not provided)

    Returns:
        Configured Tracer instance
    """
    global _tracer, _initialized

    if _initialized:
        return _tracer

    settings = settings or get_settings()
    service_name = service_name or settings.service_name

    if not settings.tracing_enabled:
        # Return a no-op tracer
        _tracer = trace.get_tracer(service_name)
        _initialized = True
        return _tracer

    # Create resource with service info
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.environment,
        }
    )

    # Configure sampler based on settings
    sampler = TraceIdRatioBased(settings.jaeger_sampler_param)

    # Create tracer provider
    provider = TracerProvider(
        resource=resource,
        sampler=sampler,
    )

    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name=settings.jaeger_agent_host,
        agent_port=settings.jaeger_agent_port,
    )

    # Add batch processor for efficient exporting
    provider.add_span_processor(
        BatchSpanProcessor(
            jaeger_exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            schedule_delay_millis=5000,
        )
    )

    # Set global tracer provider
    trace.set_tracer_provider(provider)

    # Instrument libraries
    _instrument_libraries()

    # Get tracer
    _tracer = trace.get_tracer(service_name)
    _initialized = True

    return _tracer


def _instrument_libraries() -> None:
    """Instrument common libraries for automatic tracing."""
    try:
        AsyncPGInstrumentor().instrument()
    except Exception:
        pass  # Library not available or already instrumented

    try:
        RedisInstrumentor().instrument()
    except Exception:
        pass


def get_tracer(name: str | None = None) -> Tracer:
    """
    Get the configured tracer instance.

    Args:
        name: Optional tracer name (defaults to __name__)

    Returns:
        Tracer instance
    """
    if not _initialized:
        setup_tracing()

    if name:
        return trace.get_tracer(name)

    return _tracer or trace.get_tracer(__name__)


def get_current_trace_id() -> str | None:
    """Get the current trace ID from context."""
    span = trace.get_current_span()
    if span and span.is_recording():
        return format(span.get_span_context().trace_id, "032x")
    return _current_trace_id.get()


def set_current_trace_id(trace_id: str) -> None:
    """Set the current trace ID in context."""
    _current_trace_id.set(trace_id)


def traced(
    name: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> Callable[[F], F]:
    """
    Decorator to trace a function.

    Args:
        name: Span name (defaults to function name)
        attributes: Additional span attributes

    Usage:
        @traced("process_trade")
        async def process_trade(trade: Trade):
            ...
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def add_span_attributes(**attributes: Any) -> None:
    """Add attributes to the current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def add_span_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add an event to the current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.add_event(name, attributes=attributes)


def inject_trace_context(headers: dict[str, str]) -> dict[str, str]:
    """
    Inject trace context into headers for propagation.

    Args:
        headers: Headers dict to inject into

    Returns:
        Headers with trace context
    """
    propagator = TraceContextTextMapPropagator()
    propagator.inject(headers)
    return headers


def extract_trace_context(headers: dict[str, str]) -> Any:
    """
    Extract trace context from headers.

    Args:
        headers: Headers containing trace context

    Returns:
        Extracted context
    """
    propagator = TraceContextTextMapPropagator()
    return propagator.extract(headers)
