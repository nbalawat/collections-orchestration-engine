"""Event Projector — consumes all Kafka topics and writes to PostgreSQL + Redis.

This is the CQRS read-side projection. Every event from every topic gets
written to the customer_events table (the event store) and relevant
aggregates get updated.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid

import asyncpg
import orjson
import redis.asyncio as aioredis

from events.topics import Topics
from services.shared.heartbeat import HeartbeatEmitter
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
        self.heartbeat = HeartbeatEmitter("event-projector")

    async def start(self):
        self.db = await asyncpg.connect(DB_DSN)
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=False)
        logger.info("Connected to Postgres and Redis")
        await self.heartbeat.start()

        self.consumer = KafkaConsumer(
            topics=Topics.ALL,
            group_id="event-projector",
        )
        await self.consumer.start()
        logger.info("Consuming from all topics: %s", Topics.ALL)

        await self.consumer.consume(self._handle)

    def _extract_event_type(self, topic: str, value: dict) -> str:
        if value.get("event_type"):
            return value["event_type"]
        if topic == Topics.DECISIONS:
            return value.get("decision_type", "strategy_evaluation")
        if topic == Topics.COMPLIANCE:
            ct = value.get("check_type", "")
            passed = value.get("passed")
            if value.get("action_blocked"):
                return f"blocked:{value['action_blocked']}"
            return f"compliance:{ct}" if ct else "compliance_check"
        if topic == Topics.LIFECYCLE:
            fs, ts = value.get("from_stage", ""), value.get("to_stage", "")
            if fs and ts:
                return f"stage_change:{fs}->{ts}"
            return f"stage_change:{ts}" if ts else "lifecycle"
        if topic == Topics.AI_REASONING:
            return f"ai_reasoning:{value.get('agent_type', 'unknown')}"
        if topic == Topics.ACTIONS:
            return value.get("action_type", "action_dispatched")
        return topic.split(".")[-1]

    def _extract_payload(self, topic: str, value: dict) -> dict:
        base = value.get("payload", {})
        if topic == Topics.DECISIONS:
            return {
                **base,
                "decision_type": value.get("decision_type"),
                "strategy_version": value.get("strategy_version"),
                "policy_name": value.get("policy_name"),
                "rationale": value.get("rationale"),
            }
        if topic == Topics.COMPLIANCE:
            return {**base, "check_type": value.get("check_type"), "passed": value.get("passed"), "rule_name": value.get("rule_name"), "action_blocked": value.get("action_blocked"), **value.get("details", {})}
        if topic == Topics.LIFECYCLE:
            return {**base, "from_stage": value.get("from_stage"), "to_stage": value.get("to_stage"), "reason": value.get("reason"), "triggered_by": value.get("triggered_by")}
        if topic == Topics.AI_REASONING:
            return {**base, "agent_type": value.get("agent_type"), "action_taken": value.get("action_taken"), "confidence": value.get("confidence"), "escalated": value.get("escalated"), "tokens_used": value.get("tokens_used"), "latency_ms": value.get("latency_ms"), "model": value.get("model")}
        if topic == Topics.ACTIONS:
            return {**base, "action_type": value.get("action_type"), "status": value.get("status")}
        return base

    async def _handle(self, topic: str, key: bytes | None, value: dict):
        start = time.monotonic()
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

        event_type = self._extract_event_type(topic, value)
        payload = self._extract_payload(topic, value)

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
                event_type,
                category_map.get(topic, "unknown"),
                value.get("intent"),
                json.dumps({k: v for k, v in payload.items() if v is not None}),
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
            self.heartbeat.record_event(latency_ms=int((time.monotonic() - start) * 1000))
            if self.event_count % 100 == 0:
                logger.info("Projected %d events", self.event_count)

        except Exception:
            self.heartbeat.record_error()
            logger.exception("Failed to project event from %s", topic)

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
        await self.heartbeat.stop()
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
