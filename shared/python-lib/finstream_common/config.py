"""
Configuration management using Pydantic Settings.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # General
    environment: Literal["development", "staging", "production"] = "development"
    service_name: str = "finstream-service"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    debug: bool = False

    # Kafka / Redpanda
    kafka_bootstrap_servers: str = "localhost:19092"
    schema_registry_url: str = "http://localhost:18081"

    # Kafka Producer
    kafka_producer_acks: Literal["0", "1", "all"] = "all"
    kafka_producer_retries: int = 3
    kafka_producer_linger_ms: int = 5
    kafka_producer_batch_size: int = 16384
    kafka_producer_compression_type: Literal["none", "gzip", "snappy", "lz4", "zstd"] = "gzip"

    # Kafka Consumer
    kafka_consumer_group_id: str = "finstream-consumer"
    kafka_consumer_auto_offset_reset: Literal["earliest", "latest"] = "earliest"
    kafka_consumer_enable_auto_commit: bool = False
    kafka_consumer_max_poll_records: int = 500

    # Redis
    redis_url: str = "redis://localhost:6379"
    redis_max_connections: int = 10
    redis_decode_responses: bool = True

    # Cache TTLs
    cache_ttl_quotes: int = 5
    cache_ttl_candles: int = 60
    cache_ttl_statistics: int = 300

    # TimescaleDB
    timescale_url: str = "postgresql://finstream:finstream@localhost:5432/finstream"
    timescale_pool_size: int = 10
    timescale_max_overflow: int = 20
    timescale_pool_timeout: int = 30

    # Observability - Jaeger
    jaeger_agent_host: str = "localhost"
    jaeger_agent_port: int = 6831
    jaeger_sampler_type: str = "probabilistic"
    jaeger_sampler_param: float = 0.1
    tracing_enabled: bool = True

    # Observability - Prometheus
    metrics_enabled: bool = True
    metrics_port: int = 8000

    # Topics
    topic_trades: str = "trades"
    topic_quotes: str = "quotes"
    topic_orders: str = "orders"
    topic_candles: str = "candles"
    topic_alerts: str = "alerts"
    topic_dlq: str = "dlq"

    @field_validator("kafka_bootstrap_servers", mode="before")
    @classmethod
    def parse_bootstrap_servers(cls, v: str) -> str:
        """Ensure bootstrap servers is properly formatted."""
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
