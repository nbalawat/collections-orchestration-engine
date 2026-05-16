"""[NOT MOCKED] — Genuinely publishes to Kafka. The audit should leave it alone."""
from __future__ import annotations

import orjson
from aiokafka import AIOKafkaProducer

KAFKA_BOOTSTRAP = "localhost:9094"


class RealPublisher:
    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
        await self._producer.start()

    async def publish(self, topic: str, key: str, value: dict) -> None:
        if not self._producer:
            raise RuntimeError("publisher not started")
        await self._producer.send_and_wait(
            topic, value=orjson.dumps(value), key=key.encode(),
        )

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()
