"""Event Projector — consumes all Kafka topics and writes to PostgreSQL + Redis.

This is the CQRS read-side projection. Every event from every topic gets
written to the customer_events table (the event store) and relevant
aggregates get updated.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

import asyncpg
import orjson
import redis.asyncio as aioredis

from events.topics import Topics
from services.shared.kafka_client import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_DSN = "postgresql://collections:collections@localhost:5432/collections"
REDIS_URL = "redis://localhost:6379/0"


class EventProjector:
    def __init__(self):
        self.db: asyncpg.Connection | None = None
        self.redis: aioredis.Redis | None = None
        self.consumer: KafkaConsumer | None = None
        self.event_count = 0

    async def start(self):
        self.db = await asyncpg.connect(DB_DSN)
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=False)
        logger.info("Connected to Postgres and Redis")

        self.consumer = KafkaConsumer(
            topics=Topics.ALL,
            group_id="event-projector",
        )
        await self.consumer.start()
        logger.info("Consuming from all topics: %s", Topics.ALL)

        await self.consumer.consume(self._handle)

    async def _handle(self, topic: str, key: bytes | None, value: dict):
        customer_id = value.get("customer_id", "")
        event_id = value.get("event_id", str(uuid.uuid4()))

        category_map = {
            Topics.CHANNEL_EVENTS_RAW: "channel",
            Topics.INTERACTIONS_NORMALIZED: "interaction",
            Topics.DECISIONS: "decision",
            Topics.ACTIONS: "action",
            Topics.LIFECYCLE: "lifecycle",
            Topics.COMPLIANCE: "compliance",
            Topics.AI_REASONING: "ai_reasoning",
            Topics.AI_QUALITY: "ai_quality",
        }

        try:
            await self.db.execute("""
                INSERT INTO customer_events (
                    event_id, customer_id, account_id, workflow_id,
                    channel, direction, event_type, event_category,
                    intent, payload, correlation_id, source_service, occurred_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,NOW())
                ON CONFLICT (event_id) DO NOTHING
            """,
                uuid.UUID(event_id) if len(event_id) == 36 else uuid.uuid4(),
                customer_id,
                value.get("account_id"),
                value.get("workflow_id"),
                value.get("channel"),
                value.get("direction"),
                value.get("event_type", topic.split(".")[-1]),
                category_map.get(topic, "unknown"),
                value.get("intent"),
                json.dumps(value.get("payload", {})),
                uuid.UUID(value["correlation_id"]) if value.get("correlation_id") and len(value.get("correlation_id", "")) == 36 else None,
                value.get("source_service"),
            )

            if customer_id:
                await self.redis.publish(
                    f"events:{customer_id}",
                    orjson.dumps({"topic": topic, **value}),
                )
                await self.redis.publish(
                    "events:all",
                    orjson.dumps({"topic": topic, **value}),
                )

            self.event_count += 1
            if self.event_count % 100 == 0:
                logger.info("Projected %d events", self.event_count)

        except Exception:
            logger.exception("Failed to project event from %s", topic)

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
        if self.db:
            await self.db.close()
        if self.redis:
            await self.redis.aclose()


async def main():
    projector = EventProjector()
    try:
        await projector.start()
    except KeyboardInterrupt:
        await projector.stop()


if __name__ == "__main__":
    asyncio.run(main())
