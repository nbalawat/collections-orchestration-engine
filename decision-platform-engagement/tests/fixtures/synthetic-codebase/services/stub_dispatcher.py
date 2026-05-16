"""[PLANTED MOCK #3 — High]

These tools look like they dispatch outbound actions but they don't actually
do anything. They return canned success and the caller has no way to know.
"""
from __future__ import annotations

from datetime import datetime, timezone


def send_payment_link(customer_id: str, amount: float, channel: str = "sms") -> dict:
    # ANTIPATTERN: stub returning fake success with no real action
    return {
        "status": "payment_link_sent",
        "link_id": f"PAY-{customer_id[-4:]}-{int(datetime.now(timezone.utc).timestamp())}",
        "channel": channel,
        "amount": amount,
        "expires_in_hours": 72,
    }


def escalate_to_human(customer_id: str, reason: str, urgency: str = "normal") -> dict:
    # ANTIPATTERN: another stub returning fake "escalated" with no queue insert
    return {
        "status": "escalated",
        "customer_id": customer_id,
        "queue_position": 1,
        "specialist": "collections_agent",
    }
