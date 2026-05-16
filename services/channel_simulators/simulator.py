"""Channel Simulators — generate realistic events for SMS, email, voice, and dialer.

Each simulator produces canonical CustomerInteraction events on Kafka. Used for
demo scenarios and testing. Events go to interactions.normalized to be picked up
by the signal bridge and event projector.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from datetime import datetime, timezone

from events.models import ChannelEvent, Channel, Direction, Intent
from events.topics import Topics
from services.shared.kafka_client import KafkaProducer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


SMS_INBOUND_MESSAGES = {
    Intent.PTP: [
        "I can pay $500 by Friday",
        "Will send payment next Tuesday",
        "Can I pay half now and half next week?",
    ],
    Intent.HARDSHIP: [
        "I lost my job last month, can we work something out?",
        "I'm going through a divorce and can't make payments",
        "Medical bills have wiped me out, need help",
        "My hours got cut, I can't afford the minimum",
    ],
    Intent.BALANCE_INQUIRY: [
        "What do I owe?",
        "What's my current balance?",
        "How much is past due?",
    ],
    Intent.SETTLEMENT_INQUIRY: [
        "Can I settle for less than I owe?",
        "What settlement options do you have?",
        "I can pay a lump sum if you reduce the amount",
    ],
    Intent.PAYMENT_QUESTION: [
        "Where do I send payment?",
        "Can I pay online?",
        "Do you take credit cards?",
    ],
    Intent.REFUSAL_TO_PAY: [
        "I'm not paying this",
        "This isn't my debt",
        "Stop contacting me",
    ],
    Intent.GENERAL_INQUIRY: [
        "Can someone call me back?",
        "I need to update my phone number",
        "When is my next payment due?",
    ],
}

VOICE_OUTCOMES = [
    "connected_rpc", "connected_rpc", "connected_rpc",
    "no_answer", "voicemail", "busy", "wrong_number",
]

EMAIL_EVENTS = [
    "delivered", "delivered", "delivered", "opened", "opened",
    "clicked", "bounced", "unsubscribed",
]


class ChannelSimulator:
    def __init__(self):
        self.producer: KafkaProducer | None = None

    async def start(self):
        self.producer = KafkaProducer()
        await self.producer.start()
        logger.info("Channel simulator producer started")

    async def stop(self):
        if self.producer:
            await self.producer.stop()

    async def simulate_sms_inbound(
        self,
        customer_id: str,
        intent: Intent = Intent.GENERAL_INQUIRY,
        account_id: str | None = None,
        payload_override: dict | None = None,
    ) -> ChannelEvent:
        messages = SMS_INBOUND_MESSAGES.get(intent, SMS_INBOUND_MESSAGES[Intent.GENERAL_INQUIRY])
        text = random.choice(messages)
        # New inbound channel event starts a trace.
        trace_id = str(uuid.uuid4())
        event = ChannelEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            account_id=account_id,
            channel=Channel.SMS,
            direction=Direction.INBOUND,
            event_type="sms_received",
            intent=intent,
            payload={"text": text, "from_number": "+1555" + str(random.randint(1000000, 9999999)), **(payload_override or {})},
            correlation_id=trace_id,
            occurred_at=datetime.now(timezone.utc),
            source_service="adapter-sms",
        )
        await self.producer.send_event(Topics.INTERACTIONS_NORMALIZED, event)
        logger.info("SMS inbound [%s] %s: %s → '%s'", customer_id, intent.value, event.event_id[:8], text[:50])
        return event

    async def simulate_sms_outbound(
        self,
        customer_id: str,
        template: str = "payment_reminder",
        account_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ChannelEvent:
        event = ChannelEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            account_id=account_id,
            channel=Channel.SMS,
            direction=Direction.OUTBOUND,
            event_type="sms_sent",
            payload={"template": template, "status": "delivered"},
            correlation_id=correlation_id or str(uuid.uuid4()),
            occurred_at=datetime.now(timezone.utc),
            source_service="adapter-sms",
        )
        await self.producer.send_event(Topics.INTERACTIONS_NORMALIZED, event)
        logger.info("SMS outbound [%s]: template=%s", customer_id, template)
        return event

    async def simulate_email_event(
        self,
        customer_id: str,
        event_type: str = "delivered",
        direction: Direction = Direction.OUTBOUND,
        account_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ChannelEvent:
        event = ChannelEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            account_id=account_id,
            channel=Channel.EMAIL,
            direction=direction,
            event_type=f"email_{event_type}",
            payload={"email_event": event_type, "template": "collections_notice"},
            correlation_id=correlation_id or str(uuid.uuid4()),
            occurred_at=datetime.now(timezone.utc),
            source_service="adapter-email",
        )
        await self.producer.send_event(Topics.INTERACTIONS_NORMALIZED, event)
        logger.info("Email [%s] %s: %s", customer_id, event_type, direction.value)
        return event

    async def simulate_voice_call(
        self,
        customer_id: str,
        direction: Direction = Direction.OUTBOUND,
        outcome: str | None = None,
        intent: Intent | None = None,
        duration_seconds: int | None = None,
        account_id: str | None = None,
    ) -> ChannelEvent:
        outcome = outcome or random.choice(VOICE_OUTCOMES)
        duration = duration_seconds or (random.randint(60, 480) if "connected" in outcome else 0)

        event = ChannelEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            account_id=account_id,
            channel=Channel.VOICE,
            direction=direction,
            event_type=f"call_{outcome}",
            intent=intent,
            payload={
                "outcome": outcome,
                "duration_seconds": duration,
                "agent_id": f"AGT-{random.randint(100, 999)}" if "connected" in outcome else None,
                "contact_id": str(uuid.uuid4())[:8],
            },
            correlation_id=str(uuid.uuid4()),
            occurred_at=datetime.now(timezone.utc),
            source_service="adapter-voice",
        )
        await self.producer.send_event(Topics.INTERACTIONS_NORMALIZED, event)
        logger.info("Voice [%s] %s %s: outcome=%s duration=%ds",
                     customer_id, direction.value, intent or "", outcome, duration)
        return event

    async def simulate_dialer_campaign(
        self,
        customer_id: str,
        campaign_id: str = "CAMP-001",
        outcome: str | None = None,
        account_id: str | None = None,
    ) -> ChannelEvent:
        outcome = outcome or random.choice(["connected", "no_answer", "voicemail", "busy", "machine"])

        event = ChannelEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            account_id=account_id,
            channel=Channel.DIALER,
            direction=Direction.OUTBOUND,
            event_type=f"dialer_{outcome}",
            payload={
                "campaign_id": campaign_id,
                "outcome": outcome,
                "disposition": outcome,
                "attempt_number": random.randint(1, 5),
            },
            correlation_id=str(uuid.uuid4()),
            occurred_at=datetime.now(timezone.utc),
            source_service="adapter-dialer",
        )
        await self.producer.send_event(Topics.INTERACTIONS_NORMALIZED, event)
        logger.info("Dialer [%s] campaign=%s outcome=%s", customer_id, campaign_id, outcome)
        return event
