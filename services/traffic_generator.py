"""Continuous Channel Traffic Generator.

Drives the orchestrator with realistic inbound channel activity 24/7. This is the
ONLY service in the system that is allowed to simulate — it represents the external
world (customers, dialers, email gateways) sending events through their respective
adapters into Kafka.

Everything downstream — signal bridge, workflow, OPA, AI agents, dispatch, projector,
API — operates on real events using real persistence, real OPA evaluations, and
real Claude API calls. The output of those services is genuine.

Design:
  - Targets ~50–200 concurrent journeys (configurable via TARGET_LIVE_JOURNEYS env)
  - Mix of arrival rates by channel:
      ~40% inbound SMS (customer-initiated)
      ~25% inbound voice (customer call-back)
      ~15% inbound email replies
      ~15% dialer outcomes (machine/no-answer)
      ~5% payment events
  - Realistic intent distribution weighted by customer DPD bucket
  - Backoff if Kafka or workflow throughput drops
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import signal
import uuid
from collections import deque
from datetime import datetime, timezone

import asyncpg

from events.models import ChannelEvent, Channel, Direction, Intent
from events.topics import Topics
from services.channel_simulators.simulator import ChannelSimulator, SMS_INBOUND_MESSAGES
from services.shared.config import get_settings
from services.shared.demo_accounts import RESERVED_SCENARIO_CUSTOMERS
from services.shared.heartbeat import HeartbeatEmitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TARGET_LIVE_JOURNEYS = int(os.environ.get("TARGET_LIVE_JOURNEYS", "60"))
EVENTS_PER_MINUTE = int(os.environ.get("EVENTS_PER_MINUTE", "30"))


# Intent distributions by DPD bucket — realistic banking patterns
INTENT_DISTRIBUTIONS: dict[str, list[tuple[Intent, float]]] = {
    "current": [
        (Intent.BALANCE_INQUIRY, 0.35),
        (Intent.PAYMENT_QUESTION, 0.30),
        (Intent.GENERAL_INQUIRY, 0.25),
        (Intent.PTP, 0.10),
    ],
    "early": [  # 1–29 DPD
        (Intent.PTP, 0.35),
        (Intent.PAYMENT_QUESTION, 0.25),
        (Intent.BALANCE_INQUIRY, 0.15),
        (Intent.HARDSHIP, 0.10),
        (Intent.GENERAL_INQUIRY, 0.10),
        (Intent.SETTLEMENT_INQUIRY, 0.05),
    ],
    "mid": [  # 30–59 DPD
        (Intent.PTP, 0.30),
        (Intent.HARDSHIP, 0.25),
        (Intent.SETTLEMENT_INQUIRY, 0.15),
        (Intent.PAYMENT_QUESTION, 0.10),
        (Intent.DISPUTE, 0.10),
        (Intent.REFUSAL_TO_PAY, 0.05),
        (Intent.COMPLAINT, 0.05),
    ],
    "late": [  # 60–89 DPD
        (Intent.HARDSHIP, 0.30),
        (Intent.SETTLEMENT_INQUIRY, 0.25),
        (Intent.PTP, 0.15),
        (Intent.DISPUTE, 0.10),
        (Intent.REFUSAL_TO_PAY, 0.10),
        (Intent.COMPLAINT, 0.05),
        (Intent.DISTRESS, 0.05),
    ],
    "severe": [  # 90+ DPD
        (Intent.SETTLEMENT_INQUIRY, 0.35),
        (Intent.HARDSHIP, 0.25),
        (Intent.REFUSAL_TO_PAY, 0.15),
        (Intent.DISPUTE, 0.10),
        (Intent.DISTRESS, 0.10),
        (Intent.COMPLAINT, 0.05),
    ],
}


CHANNEL_MIX: list[tuple[str, float]] = [
    ("inbound_sms", 0.40),
    ("inbound_voice", 0.20),
    ("inbound_email", 0.10),
    ("dialer_outcome", 0.15),
    ("payment", 0.05),
    ("email_event", 0.10),
]


def _weighted_choice(choices: list[tuple]) -> object:
    """Return the first element of a (value, weight) pair selected by weight."""
    total = sum(w for _, w in choices)
    r = random.random() * total
    cum = 0.0
    for value, weight in choices:
        cum += weight
        if r <= cum:
            return value
    return choices[-1][0]


def _dpd_bucket(dpd: int) -> str:
    if dpd <= 0:
        return "current"
    if dpd < 30:
        return "early"
    if dpd < 60:
        return "mid"
    if dpd < 90:
        return "late"
    return "severe"


class TrafficGenerator:
    def __init__(self, target_journeys: int, events_per_min: int):
        self.target_journeys = target_journeys
        self.events_per_min = events_per_min
        self.simulator = ChannelSimulator()
        self.db: asyncpg.Pool | None = None
        self.stop_event = asyncio.Event()
        self.active_customers: deque[dict] = deque(maxlen=target_journeys * 3)
        self.total_events = 0
        self.heartbeat = HeartbeatEmitter("traffic-generator", extra={
            "target_journeys": target_journeys, "events_per_min": events_per_min,
        })

    async def start(self):
        self.db = await asyncpg.create_pool(get_settings().postgres_dsn_sync, min_size=2, max_size=5)
        await self.simulator.start()
        await self._load_customer_pool()
        await self.heartbeat.start()
        logger.info(
            "TrafficGenerator: target=%d concurrent journeys, %d events/min, pool=%d customers",
            self.target_journeys, self.events_per_min, len(self.active_customers),
        )

    async def stop(self):
        self.stop_event.set()
        await self.heartbeat.stop()
        await self.simulator.stop()
        if self.db:
            await self.db.close()

    async def _load_customer_pool(self):
        # Exclude accounts reserved for scripted demo scenarios so the traffic
        # generator never pollutes them — they stay clean for live demos.
        reserved = list(RESERVED_SCENARIO_CUSTOMERS)
        async with self.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT cp.customer_id, cp.timezone, cp.preferred_channel,
                       a.account_id, a.days_past_due, a.current_balance, a.delinquency_stage
                FROM customer_profiles cp
                JOIN accounts a ON a.customer_id = cp.customer_id
                WHERE a.status = 'ACTIVE'
                  AND cp.customer_id <> ALL($2::text[])
                ORDER BY RANDOM()
                LIMIT $1
            """, self.target_journeys * 3, reserved)
        for row in rows:
            self.active_customers.append(dict(row))
        logger.info(
            "Traffic generator pool: %d customers (excluded %d reserved demo accounts)",
            len(self.active_customers), len(reserved),
        )

    def _pick_customer(self) -> dict | None:
        if not self.active_customers:
            return None
        return random.choice(list(self.active_customers))

    def _pick_intent(self, dpd: int) -> Intent:
        bucket = _dpd_bucket(dpd)
        dist = INTENT_DISTRIBUTIONS[bucket]
        return _weighted_choice(dist)

    async def _emit_event(self):
        cust = self._pick_customer()
        if not cust:
            return

        cid = cust["customer_id"]
        aid = cust.get("account_id")
        dpd = int(cust.get("days_past_due") or 0)

        channel_kind = _weighted_choice(CHANNEL_MIX)

        try:
            if channel_kind == "inbound_sms":
                intent = self._pick_intent(dpd)
                await self.simulator.simulate_sms_inbound(cid, intent=intent, account_id=aid)
            elif channel_kind == "inbound_voice":
                intent = self._pick_intent(dpd)
                await self.simulator.simulate_voice_call(
                    cid,
                    direction=Direction.INBOUND,
                    outcome="connected_rpc",
                    intent=intent,
                    duration_seconds=random.randint(120, 480),
                    account_id=aid,
                )
            elif channel_kind == "inbound_email":
                await self.simulator.simulate_email_event(
                    cid, event_type="received", direction=Direction.INBOUND, account_id=aid,
                )
            elif channel_kind == "dialer_outcome":
                outcome = random.choices(
                    ["connected", "no_answer", "voicemail", "busy", "machine"],
                    weights=[15, 40, 20, 10, 15],
                )[0]
                await self.simulator.simulate_dialer_campaign(cid, outcome=outcome, account_id=aid)
            elif channel_kind == "email_event":
                event_type = random.choices(
                    ["delivered", "opened", "clicked", "bounced"],
                    weights=[60, 25, 10, 5],
                )[0]
                await self.simulator.simulate_email_event(cid, event_type=event_type, account_id=aid)
            elif channel_kind == "payment":
                amount = round(float(cust.get("current_balance") or 100) * random.uniform(0.05, 0.40), 2)
                await self._emit_payment(cid, aid, amount)

            self.total_events += 1
            self.heartbeat.record_event()
            if self.total_events % 50 == 0:
                logger.info("Traffic: emitted %d events", self.total_events)
        except Exception:
            self.heartbeat.record_error()
            logger.exception("Failed to emit %s event for %s", channel_kind, cid)

    async def _emit_payment(self, customer_id: str, account_id: str, amount: float):
        """Emit a payment_received event — this is treated as inbound from the payment processor."""
        event = ChannelEvent(
            event_id=str(uuid.uuid4()),
            customer_id=customer_id,
            account_id=account_id,
            channel=Channel.SYSTEM,
            direction=Direction.INBOUND,
            event_type="payment_received",
            payload={
                "amount": amount,
                "payment_method": random.choice(["ach", "card", "check"]),
                "payment_date": datetime.now(timezone.utc).date().isoformat(),
            },
            occurred_at=datetime.now(timezone.utc),
            source_service="adapter-payment-processor",
        )
        await self.simulator.producer.send_event(Topics.INTERACTIONS_NORMALIZED, event)

    async def run(self):
        interval = 60.0 / max(self.events_per_min, 1)
        jitter_low, jitter_high = 0.5, 1.5
        logger.info("TrafficGenerator running — emitting every ~%.2fs", interval)

        while not self.stop_event.is_set():
            await self._emit_event()
            sleep = interval * random.uniform(jitter_low, jitter_high)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=sleep)
            except asyncio.TimeoutError:
                pass

        logger.info("TrafficGenerator stopped after %d total events", self.total_events)


async def main():
    parser = argparse.ArgumentParser(description="Continuous channel traffic generator")
    parser.add_argument("--journeys", type=int, default=TARGET_LIVE_JOURNEYS,
                        help="Target concurrent journeys (default: %(default)s)")
    parser.add_argument("--rate", type=int, default=EVENTS_PER_MINUTE,
                        help="Events per minute (default: %(default)s)")
    args = parser.parse_args()

    gen = TrafficGenerator(target_journeys=args.journeys, events_per_min=args.rate)
    await gen.start()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, gen.stop_event.set)

    try:
        await gen.run()
    finally:
        await gen.stop()


if __name__ == "__main__":
    asyncio.run(main())
