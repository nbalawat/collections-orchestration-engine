"""Activities that compute real contact statistics from customer_events.

Replaces hardcoded values (`voice_attempts_7d=0`, `customer_local_hour=14`,
`failed_channels=[]`, `conflicting_signals=[]`) that were silently breaking
compliance and strategy rules.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import asyncpg
from temporalio import activity

from workflows.types import ContactStats

logger = logging.getLogger(__name__)
DB_DSN = "postgresql://collections:collections@localhost:5432/collections"


@activity.defn
async def compute_contact_stats(customer_id: str) -> ContactStats:
    """Compute per-customer contact statistics for the last 7 days.

    Drives OPA inputs that govern: time-of-day calling restrictions, Reg F call
    frequency caps, channel exhaustion routing, and conflicting-signal escalation.
    """
    conn = await asyncpg.connect(DB_DSN)
    try:
        # Customer's local hour from their stored timezone.
        tz_row = await conn.fetchrow(
            "SELECT timezone FROM customer_profiles WHERE customer_id = $1",
            customer_id,
        )
        tz_name = (tz_row["timezone"] if tz_row else None) or "America/New_York"
        try:
            local_hour = datetime.now(ZoneInfo(tz_name)).hour
        except ZoneInfoNotFoundError:
            local_hour = datetime.now(ZoneInfo("America/New_York")).hour

        # Outbound contact attempts per channel over last 7 days.
        attempt_rows = await conn.fetch("""
            SELECT channel, COUNT(*) AS n
            FROM customer_events
            WHERE customer_id = $1
              AND direction = 'outbound'
              AND occurred_at > NOW() - INTERVAL '7 days'
              AND channel IS NOT NULL
            GROUP BY channel
        """, customer_id)
        channel_attempts = {r["channel"]: int(r["n"]) for r in attempt_rows}

        # Channels with delivery failures or bounces in last 7 days.
        failed_rows = await conn.fetch("""
            SELECT DISTINCT channel
            FROM customer_events
            WHERE customer_id = $1
              AND occurred_at > NOW() - INTERVAL '7 days'
              AND (event_type LIKE '%bounced%' OR event_type LIKE '%failed%'
                   OR event_type LIKE '%no_answer%' OR event_type LIKE '%undelivered%')
              AND channel IS NOT NULL
        """, customer_id)
        failed_channels = sorted({r["channel"] for r in failed_rows})

        # Conflicting signals — recent inbound intents that don't agree.
        recent_intents_rows = await conn.fetch("""
            SELECT DISTINCT intent
            FROM customer_events
            WHERE customer_id = $1
              AND direction = 'inbound'
              AND occurred_at > NOW() - INTERVAL '7 days'
              AND intent IS NOT NULL
        """, customer_id)
        intents = {r["intent"] for r in recent_intents_rows}
        conflicting_pairs = [
            ("PTP", "DISPUTE"),
            ("PTP", "REFUSAL_TO_PAY"),
            ("HARDSHIP", "PTP"),
            ("SETTLEMENT_INQUIRY", "DISPUTE"),
        ]
        conflicting = []
        for a, b in conflicting_pairs:
            if a in intents and b in intents:
                conflicting.append(f"{a}+{b}")

        # Last contact + last inbound intent for context.
        last_contact = await conn.fetchval("""
            SELECT occurred_at FROM customer_events
            WHERE customer_id = $1 ORDER BY occurred_at DESC LIMIT 1
        """, customer_id)
        last_intent = await conn.fetchval("""
            SELECT intent FROM customer_events
            WHERE customer_id = $1 AND direction = 'inbound' AND intent IS NOT NULL
            ORDER BY occurred_at DESC LIMIT 1
        """, customer_id)

        return ContactStats(
            customer_local_hour=local_hour,
            voice_attempts_7d=channel_attempts.get("voice", 0),
            sms_attempts_7d=channel_attempts.get("sms", 0),
            email_attempts_7d=channel_attempts.get("email", 0),
            dialer_attempts_7d=channel_attempts.get("dialer", 0),
            channel_attempts_7d=channel_attempts,
            failed_channels=failed_channels,
            conflicting_signals=conflicting,
            last_contact_at=last_contact.isoformat() if last_contact else None,
            last_inbound_intent=last_intent,
        )
    finally:
        await conn.close()
