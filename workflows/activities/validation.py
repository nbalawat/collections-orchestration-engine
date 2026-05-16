"""Activities for Reg F §1006.34 validation notice tracking.

§1006.34 requires that a debt collector provide "validation information" within
5 days of an initial communication, OR include it in the initial communication
itself. We model this by creating a validation_notices row when the first
outbound communication on a workflow is about to be sent, then a workflow timer
ensures the notice is dispatched within the 5-day window.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import orjson
from aiokafka import AIOKafkaProducer
from temporalio import activity

from events.models import ChannelEvent, Channel, Direction
from events.topics import Topics

logger = logging.getLogger(__name__)
DB_DSN = "postgresql://collections:collections@localhost:5432/collections"
KAFKA_BOOTSTRAP = "localhost:9094"
VALIDATION_WINDOW_DAYS = 5


@activity.defn
async def ensure_validation_notice_scheduled(
    customer_id: str,
    workflow_id: str,
    account_id: str | None,
    first_contact_at_iso: str,
    channel: str,
) -> dict:
    """Creates a pending validation notice row if one doesn't already exist for
    this workflow. Returns the notice metadata (including the due deadline)."""
    first_contact_at = datetime.fromisoformat(first_contact_at_iso.replace("Z", "+00:00"))
    due_at = first_contact_at + timedelta(days=VALIDATION_WINDOW_DAYS)

    conn = await asyncpg.connect(DB_DSN)
    try:
        existing = await conn.fetchrow("""
            SELECT notice_id, status, notice_due_at FROM validation_notices
            WHERE workflow_id = $1
            ORDER BY created_at DESC LIMIT 1
        """, workflow_id)
        if existing:
            return {
                "notice_id": str(existing["notice_id"]),
                "status": existing["status"],
                "due_at": existing["notice_due_at"].isoformat(),
                "newly_created": False,
            }

        notice_id = uuid.uuid4()
        await conn.execute("""
            INSERT INTO validation_notices (
                notice_id, customer_id, account_id, workflow_id,
                first_contact_at, notice_due_at, channel, status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
        """, notice_id, customer_id, account_id, workflow_id,
             first_contact_at, due_at, channel)

        return {
            "notice_id": str(notice_id),
            "status": "pending",
            "due_at": due_at.isoformat(),
            "newly_created": True,
        }
    finally:
        await conn.close()


@activity.defn
async def dispatch_validation_notice(
    customer_id: str,
    workflow_id: str,
    notice_id: str,
    channel: str = "email",
    trace_id: str | None = None,
) -> dict:
    """Sends the validation notice via the customer's preferred channel. The
    notice content is a real outbound ChannelEvent so it flows through the same
    pipeline as any other dispatch, gets projected, and shows up in the timeline."""
    # Use email by default — it's the most defensible default channel for a
    # written validation notice. Voice is allowed under §1006.34 only if the
    # consumer has consented.
    if channel not in {"email", "sms"}:
        channel = "email"

    event_id = uuid.uuid4()
    content_template = "reg_f_validation_notice"
    event = ChannelEvent(
        event_id=str(event_id),
        customer_id=customer_id,
        channel=Channel(channel),
        direction=Direction.OUTBOUND,
        event_type=f"{channel}_sent",
        payload={
            "template": content_template,
            "compliance_purpose": "reg_f_1006_34_validation_notice",
            "notice_id": notice_id,
        },
        correlation_id=trace_id or str(uuid.uuid4()),
        occurred_at=datetime.now(timezone.utc),
        source_service="orchestrator-compliance",
    )

    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP)
    await producer.start()
    try:
        await producer.send_and_wait(
            Topics.INTERACTIONS_NORMALIZED,
            value=event.to_kafka_value(),
            key=customer_id.encode(),
        )
    finally:
        await producer.stop()

    conn = await asyncpg.connect(DB_DSN)
    try:
        await conn.execute("""
            UPDATE validation_notices
            SET status = 'sent', notice_sent_at = NOW(),
                channel = $1, delivery_event_id = $2
            WHERE notice_id = $3
        """, channel, event_id, uuid.UUID(notice_id))
    finally:
        await conn.close()

    logger.info("Dispatched Reg F validation notice for %s via %s (notice_id=%s)",
                customer_id, channel, notice_id)
    return {"dispatched": True, "event_id": str(event_id), "notice_id": notice_id}
