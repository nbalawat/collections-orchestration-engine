from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

import orjson
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from services.shared.config import get_settings

logger = logging.getLogger(__name__)


class KafkaProducer:
    def __init__(self, bootstrap_servers: str | None = None):
        self._settings = get_settings()
        self._bootstrap = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: v if isinstance(v, bytes) else orjson.dumps(v),
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
        )
        await self._producer.start()
        logger.info("Kafka producer started")

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def send(self, topic: str, value: Any, key: str | None = None):
        if not self._producer:
            raise RuntimeError("Producer not started")
        await self._producer.send_and_wait(topic, value=value, key=key)

    async def send_event(self, topic: str, event):
        key = getattr(event, "customer_id", None)
        await self.send(topic, event.to_kafka_value(), key=key)

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()


class KafkaConsumer:
    def __init__(
        self,
        topics: list[str],
        group_id: str | None = None,
        bootstrap_servers: str | None = None,
    ):
        self._settings = get_settings()
        self._bootstrap = bootstrap_servers or self._settings.kafka_bootstrap_servers
        self._topics = topics
        self._group_id = group_id or self._settings.kafka_consumer_group
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap,
            group_id=self._group_id,
            value_deserializer=lambda v: orjson.loads(v),
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        await self._consumer.start()
        logger.info(f"Kafka consumer started on {self._topics}")

    async def stop(self):
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")

    async def consume(self, handler: Callable):
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        async for msg in self._consumer:
            try:
                await handler(msg.topic, msg.key, msg.value)
            except Exception:
                logger.exception(f"Error handling message from {msg.topic}")

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *exc):
        await self.stop()
