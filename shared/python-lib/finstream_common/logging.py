"""
Structured logging using structlog with JSON output.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor

from finstream_common.config import Settings, get_settings

_initialized = False


def setup_logging(
    service_name: str | None = None,
    settings: Settings | None = None,
) -> None:
    """
    Configure structured logging with structlog.

    Features:
    - JSON output for production
    - Pretty console output for development
    - Automatic context binding (trace_id, service, etc.)
    - Integration with standard library logging

    Args:
        service_name: Service name to include in all logs
        settings: Settings instance
    """
    global _initialized

    if _initialized:
        return

    settings = settings or get_settings()
    service_name = service_name or settings.service_name
    log_level = settings.log_level

    # Common processors for all environments
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Add service name to all logs
    def add_service_name(
        logger: Any, method_name: str, event_dict: dict[str, Any]
    ) -> dict[str, Any]:
        event_dict["service"] = service_name
        return event_dict

    shared_processors.insert(0, add_service_name)

    if settings.is_development:
        # Development: pretty console output
        processors: list[Processor] = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Production: JSON output
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level),
    )

    # Reduce noise from third-party libraries
    logging.getLogger("aiokafka").setLevel(logging.WARNING)
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _initialized = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Usage:
        logger = get_logger(__name__)
        logger.info("processing_trade", trade_id="123", symbol="AAPL")
    """
    if not _initialized:
        setup_logging()

    return structlog.get_logger(name)


def bind_context(**kwargs: Any) -> None:
    """
    Bind context variables that will be included in all subsequent logs.

    Usage:
        bind_context(trace_id="abc123", user_id="user456")
        logger.info("action")  # Will include trace_id and user_id
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def unbind_context(*keys: str) -> None:
    """
    Remove context variables.

    Usage:
        unbind_context("trace_id", "user_id")
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()


class LoggerAdapter:
    """
    Logger adapter that provides a simplified interface.

    Usage:
        logger = LoggerAdapter("my_service")
        logger.info("Processing trade", trade_id="123")
    """

    def __init__(self, name: str) -> None:
        self._logger = get_logger(name)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self._logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self._logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self._logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log error message."""
        self._logger.error(message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self._logger.exception(message, **kwargs)

    def bind(self, **kwargs: Any) -> "LoggerAdapter":
        """Bind context to logger and return new adapter."""
        self._logger = self._logger.bind(**kwargs)
        return self


# Convenience function for FastAPI/Starlette middleware
def log_request_middleware() -> Any:
    """
    Create a middleware that logs HTTP requests.

    Usage:
        app.add_middleware(log_request_middleware())
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    import time
    import uuid

    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # Generate request ID
            request_id = str(uuid.uuid4())[:8]

            # Bind context for this request
            bind_context(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
            )

            logger = get_logger("http")
            start_time = time.perf_counter()

            try:
                response = await call_next(request)
                duration_ms = (time.perf_counter() - start_time) * 1000

                logger.info(
                    "http_request",
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 2),
                    client_host=request.client.host if request.client else None,
                )

                # Add request ID to response headers
                response.headers["X-Request-ID"] = request_id

                return response

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.exception(
                    "http_request_error",
                    error=str(e),
                    duration_ms=round(duration_ms, 2),
                )
                raise

            finally:
                clear_context()

    return RequestLoggingMiddleware
