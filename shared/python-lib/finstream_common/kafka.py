"""
Kafka producer and consumer clients using aiokafka.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import BaseModel

from finstream_common.config import Settings, get_settings
from finstream_common.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class KafkaProducer:
    """
    Async Kafka producer with batching, compression, and error handling.

    Usage:
        async with KafkaProducer() as producer:
            await producer.send("trades", trade.to_json(), key=trade.symbol)
    """

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._producer: AIOKafkaProducer | None = None
        self._started = False

    async def start(self) -> None:
        """Start the producer."""
        if self._started:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            acks=self._settings.kafka_producer_acks,
            linger_ms=self._settings.kafka_producer_linger_ms,
            max_batch_size=self._settings.kafka_producer_batch_size,
            compression_type=self._settings.kafka_producer_compression_type,
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            value_serializer=lambda v: v if isinstance(v, bytes) else v.encode("utf-8"),
        )

        await self._producer.start()
        self._started = True
        logger.info(
            "kafka_producer_started",
            bootstrap_servers=self._bootstrap_servers,
        )

    async def stop(self) -> None:
        """Stop the producer and flush pending messages."""
        if self._producer and self._started:
            await self._producer.stop()
            self._started = False
            logger.info("kafka_producer_stopped")

    async def send(
        self,
        topic: str,
        value: bytes | str,
        key: str | None = None,
        headers: list[tuple[str, bytes]] | None = None,
        partition: int | None = None,
    ) -> None:
        """
        Send a message to a Kafka topic.

        Args:
            topic: Target topic name
            value: Message value (bytes or string)
            key: Message key for partitioning
            headers: Optional message headers
            partition: Specific partition (optional)
        """
        if not self._started:
            raise RuntimeError("Producer not started. Call start() first.")

        try:
            await self._producer.send(
                topic=topic,
                value=value,
                key=key,
                headers=headers,
                partition=partition,
            )
            logger.debug("kafka_message_sent", topic=topic, key=key)
        except KafkaError as e:
            logger.error("kafka_send_failed", topic=topic, key=key, error=str(e))
            raise

    async def send_batch(
        self,
        topic: str,
        messages: list[tuple[str | None, bytes]],
    ) -> None:
        """
        Send multiple messages to a topic.

        Args:
            topic: Target topic name
            messages: List of (key, value) tuples
        """
        for key, value in messages:
            await self.send(topic, value, key)

        # Flush to ensure delivery
        await self._producer.flush()

    async def send_model(
        self,
        topic: str,
        model: BaseModel,
        key: str | None = None,
        headers: list[tuple[str, bytes]] | None = None,
    ) -> None:
        """
        Send a Pydantic model as JSON.

        Args:
            topic: Target topic name
            model: Pydantic model instance
            key: Message key
            headers: Optional headers
        """
        value = orjson.dumps(model.model_dump(mode="json"))
        await self.send(topic, value, key, headers)

    async def __aenter__(self) -> "KafkaProducer":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()


class KafkaConsumer:
    """
    Async Kafka consumer with automatic offset management and error handling.

    Usage:
        async with KafkaConsumer(["trades"], group_id="processor") as consumer:
            async for msg in consumer.messages():
                process(msg)
    """

    def __init__(
        self,
        topics: list[str],
        group_id: str | None = None,
        bootstrap_servers: str | None = None,
        settings: Settings | None = None,
        auto_commit: bool | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._topics = topics
        self._group_id = group_id or self._settings.kafka_consumer_group_id
        self._bootstrap_servers = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._auto_commit = (
            auto_commit
            if auto_commit is not None
            else self._settings.kafka_consumer_enable_auto_commit
        )
        self._consumer: AIOKafkaConsumer | None = None
        self._started = False

    async def start(self) -> None:
        """Start the consumer."""
        if self._started:
            return

        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset=self._settings.kafka_consumer_auto_offset_reset,
            enable_auto_commit=self._auto_commit,
            max_poll_records=self._settings.kafka_consumer_max_poll_records,
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            value_deserializer=lambda v: v,  # Return raw bytes
        )

        await self._consumer.start()
        self._started = True
        logger.info(
            "kafka_consumer_started",
            topics=self._topics,
            group_id=self._group_id,
        )

    async def stop(self) -> None:
        """Stop the consumer."""
        if self._consumer and self._started:
            await self._consumer.stop()
            self._started = False
            logger.info("kafka_consumer_stopped")

    async def messages(self) -> AsyncIterator[dict[str, Any]]:
        """
        Iterate over incoming messages.

        Yields:
            Dict containing: topic, partition, offset, key, value, timestamp, headers
        """
        if not self._started:
            raise RuntimeError("Consumer not started. Call start() first.")

        async for msg in self._consumer:
            yield {
                "topic": msg.topic,
                "partition": msg.partition,
                "offset": msg.offset,
                "key": msg.key,
                "value": msg.value,
                "timestamp": msg.timestamp,
                "headers": dict(msg.headers) if msg.headers else {},
            }

    async def messages_as(
        self,
        model_class: type[T],
    ) -> AsyncIterator[tuple[T, dict[str, Any]]]:
        """
        Iterate over messages, deserializing to a Pydantic model.

        Args:
            model_class: Pydantic model class to deserialize to

        Yields:
            Tuple of (model instance, metadata dict)
        """
        async for msg in self.messages():
            try:
                data = orjson.loads(msg["value"])
                model = model_class.model_validate(data)
                yield model, msg
            except Exception as e:
                logger.error(
                    "kafka_deserialize_failed",
                    topic=msg["topic"],
                    offset=msg["offset"],
                    error=str(e),
                )
                # Optionally send to DLQ here
                raise

    async def commit(self) -> None:
        """Manually commit offsets."""
        if self._consumer and not self._auto_commit:
            await self._consumer.commit()
            logger.debug("kafka_offsets_committed")

    async def seek_to_beginning(self) -> None:
        """Seek to beginning of all assigned partitions."""
        if self._consumer:
            await self._consumer.seek_to_beginning()

    async def seek_to_end(self) -> None:
        """Seek to end of all assigned partitions."""
        if self._consumer:
            await self._consumer.seek_to_end()

    def get_lag(self) -> dict[str, int]:
        """Get consumer lag per partition."""
        # This would require additional implementation
        # to fetch highwater marks and compare with committed offsets
        return {}

    async def __aenter__(self) -> "KafkaConsumer":
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()


@asynccontextmanager
async def kafka_producer(
    bootstrap_servers: str | None = None,
) -> AsyncIterator[KafkaProducer]:
    """Context manager for creating a Kafka producer."""
    producer = KafkaProducer(bootstrap_servers=bootstrap_servers)
    try:
        await producer.start()
        yield producer
    finally:
        await producer.stop()


@asynccontextmanager
async def kafka_consumer(
    topics: list[str],
    group_id: str | None = None,
    bootstrap_servers: str | None = None,
) -> AsyncIterator[KafkaConsumer]:
    """Context manager for creating a Kafka consumer."""
    consumer = KafkaConsumer(
        topics=topics,
        group_id=group_id,
        bootstrap_servers=bootstrap_servers,
    )
    try:
        await consumer.start()
        yield consumer
    finally:
        await consumer.stop()
