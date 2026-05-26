"""Feature store — assembles per-customer feature vectors from Postgres + silver lakehouse.

This is the single source for what an ML model sees about a customer. The same
function is called by:
  - Training (batch over all customers with known outcomes)
  - Online scoring (one customer, latest state)
  - The /api/ml/features/{customer_id} endpoint for explainability

Returned shape: { feature_name: float_or_int }, plus a `_meta` block that
explains where each feature came from (table, time window, computation).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import asyncpg

from services.shared.config import get_settings


def _db_dsn() -> str:
    return get_settings().postgres_dsn_sync

# Feature catalog — used both for extraction and for the UI to show what's available
FEATURE_CATALOG: list[dict[str, str]] = [
    {"name": "days_past_due", "source": "accounts", "type": "int", "doc": "Current DPD on most-delinquent account"},
    {"name": "current_balance", "source": "accounts", "type": "float", "doc": "Account current balance"},
    {"name": "total_past_due", "source": "accounts", "type": "float", "doc": "Past-due amount on account"},
    {"name": "risk_score", "source": "customer_profiles", "type": "int", "doc": "Existing risk score (0-100, higher = riskier)"},
    {"name": "behavioral_score", "source": "customer_profiles", "type": "int", "doc": "Behavioral score (0-100)"},
    {"name": "tenure_years", "source": "customer_profiles", "type": "float", "doc": "Years since account opened"},
    {"name": "prior_delinquencies", "source": "customer_profiles", "type": "int", "doc": "Number of past delinquencies"},
    {"name": "prior_cures", "source": "customer_profiles", "type": "int", "doc": "Number of past cures"},
    {"name": "active_compliance_flags", "source": "compliance_flags", "type": "int", "doc": "Count of active flags (BANKRUPTCY, SCRA, …)"},
    {"name": "interactions_7d", "source": "customer_events", "type": "int", "doc": "Total interactions in last 7 days"},
    {"name": "inbound_7d", "source": "customer_events", "type": "int", "doc": "Inbound interactions in last 7 days"},
    {"name": "outbound_7d", "source": "customer_events", "type": "int", "doc": "Outbound interactions in last 7 days"},
    {"name": "voice_attempts_7d", "source": "customer_events", "type": "int", "doc": "Voice contact attempts in last 7 days"},
    {"name": "sms_attempts_7d", "source": "customer_events", "type": "int", "doc": "SMS attempts in last 7 days"},
    {"name": "email_attempts_7d", "source": "customer_events", "type": "int", "doc": "Email attempts in last 7 days"},
    {"name": "intent_hardship_7d", "source": "customer_events", "type": "int", "doc": "Inbound HARDSHIP intents in last 7 days"},
    {"name": "intent_ptp_7d", "source": "customer_events", "type": "int", "doc": "Inbound PTP intents in last 7 days"},
    {"name": "intent_dispute_7d", "source": "customer_events", "type": "int", "doc": "Inbound DISPUTE intents in last 7 days"},
    {"name": "intent_distress_7d", "source": "customer_events", "type": "int", "doc": "Inbound DISTRESS intents in last 7 days"},
    {"name": "stage_transitions_7d", "source": "customer_events", "type": "int", "doc": "Lifecycle transitions in last 7 days"},
    {"name": "compliance_blocks_7d", "source": "customer_events", "type": "int", "doc": "Compliance gate blocks in last 7 days"},
    {"name": "agent_actions_7d", "source": "agent_actions", "type": "int", "doc": "AI agent decisions in last 7 days"},
    {"name": "agent_escalations_7d", "source": "agent_actions", "type": "int", "doc": "AI escalations to humans in last 7 days"},
    {"name": "active_ptp", "source": "promises_to_pay", "type": "int", "doc": "1 if customer has active PTP, 0 otherwise"},
    {"name": "open_escalations", "source": "human_escalations", "type": "int", "doc": "Currently queued human escalations"},
]


async def get_features(customer_id: str, *, as_of: datetime | None = None) -> dict[str, Any]:
    """Extract feature vector for one customer. `as_of` defaults to now."""
    as_of = as_of or datetime.now(timezone.utc)
    conn = await asyncpg.connect(_db_dsn())
    try:
        return await _features_for_conn(conn, customer_id, as_of)
    finally:
        await conn.close()


async def get_features_batch(customer_ids: list[str], *, as_of: datetime | None = None) -> list[dict[str, Any]]:
    """Extract feature vectors for many customers. Uses a single connection."""
    as_of = as_of or datetime.now(timezone.utc)
    conn = await asyncpg.connect(_db_dsn())
    try:
        return [await _features_for_conn(conn, cid, as_of) for cid in customer_ids]
    finally:
        await conn.close()


async def list_known_customers(limit: int | None = None) -> list[str]:
    """All customers with at least one account — i.e. anyone we could score."""
    conn = await asyncpg.connect(_db_dsn())
    try:
        rows = await conn.fetch(
            "SELECT DISTINCT customer_id FROM accounts WHERE status = 'ACTIVE'"
            + (f" LIMIT {int(limit)}" if limit else "")
        )
        return [r["customer_id"] for r in rows]
    finally:
        await conn.close()


async def _features_for_conn(conn: asyncpg.Connection, customer_id: str, as_of: datetime) -> dict[str, Any]:
    """Single-customer extraction — issued as several focused queries.

    Cheaper than a giant join for online scoring; for training we call this in a
    loop with one connection (acceptable for a POC scale of a few hundred
    customers). For prod scale we'd materialize features in a feature_store
    table or use silver Parquet directly via DuckDB.
    """
    profile = await conn.fetchrow(
        """SELECT risk_score, behavioral_score, relationship_start
           FROM customer_profiles WHERE customer_id = $1""",
        customer_id,
    )
    # prior_delinquencies / prior_cures: derive from stage_change history
    # (the schema doesn't have these columns; we synthesize them from events
    # so the model still trains on real behavioral data)
    prior_counts = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE event_type IN (
                'stage_change:CURRENT->DUNNING',
                'stage_change:CURED->DUNNING',
                'stage_change:IDLE->DUNNING'
            )) AS prior_delinquencies,
            COUNT(*) FILTER (WHERE event_type LIKE 'stage_change:%->CURED') AS prior_cures
        FROM customer_events
        WHERE customer_id = $1 AND occurred_at < $2
    """, customer_id, as_of)
    prior_delinquencies = int(prior_counts["prior_delinquencies"] or 0)
    prior_cures = int(prior_counts["prior_cures"] or 0)
    account = await conn.fetchrow(
        """SELECT days_past_due, current_balance, total_past_due, delinquency_stage
           FROM accounts WHERE customer_id = $1 AND status = 'ACTIVE'
           ORDER BY days_past_due DESC LIMIT 1""",
        customer_id,
    )
    flags = await conn.fetchval(
        "SELECT COUNT(*) FROM compliance_flags WHERE customer_id = $1 AND status = 'ACTIVE'",
        customer_id,
    )

    # Activity window: 7 days back from as_of
    window_start = as_of.replace(tzinfo=timezone.utc) if as_of.tzinfo is None else as_of

    ev = await conn.fetchrow("""
        SELECT
            COUNT(*) FILTER (WHERE event_category IN ('channel','interaction')) AS interactions_7d,
            COUNT(*) FILTER (WHERE direction = 'inbound') AS inbound_7d,
            COUNT(*) FILTER (WHERE direction = 'outbound') AS outbound_7d,
            COUNT(*) FILTER (WHERE channel = 'voice') AS voice_attempts_7d,
            COUNT(*) FILTER (WHERE channel = 'sms') AS sms_attempts_7d,
            COUNT(*) FILTER (WHERE channel = 'email') AS email_attempts_7d,
            COUNT(*) FILTER (WHERE intent = 'HARDSHIP' AND direction = 'inbound') AS intent_hardship_7d,
            COUNT(*) FILTER (WHERE intent = 'PTP' AND direction = 'inbound') AS intent_ptp_7d,
            COUNT(*) FILTER (WHERE intent = 'DISPUTE' AND direction = 'inbound') AS intent_dispute_7d,
            COUNT(*) FILTER (WHERE intent = 'DISTRESS' AND direction = 'inbound') AS intent_distress_7d,
            COUNT(*) FILTER (WHERE event_type LIKE 'stage_change:%') AS stage_transitions_7d,
            COUNT(*) FILTER (WHERE event_category = 'compliance'
                             AND (payload->>'passed')::boolean = false) AS compliance_blocks_7d
        FROM customer_events
        WHERE customer_id = $1
          AND occurred_at >= $2::timestamptz - INTERVAL '7 days'
          AND occurred_at <= $2::timestamptz
    """, customer_id, window_start)

    aa = await conn.fetchrow("""
        SELECT COUNT(*) AS actions_7d,
               COUNT(*) FILTER (WHERE status = 'escalated') AS escalations_7d
        FROM agent_actions
        WHERE customer_id = $1
          AND created_at >= $2::timestamptz - INTERVAL '7 days'
          AND created_at <= $2::timestamptz
    """, customer_id, window_start)

    active_ptp = await conn.fetchval(
        "SELECT COUNT(*) FROM promises_to_pay WHERE customer_id = $1 AND status = 'ACTIVE'",
        customer_id,
    )
    open_esc = await conn.fetchval(
        "SELECT COUNT(*) FROM human_escalations WHERE customer_id = $1 AND status = 'queued'",
        customer_id,
    )

    tenure = 0.0
    if profile and profile["relationship_start"]:
        d = profile["relationship_start"]
        try:
            tenure = max(0.0, (as_of.date() - d).days / 365.25)
        except Exception:
            pass

    return {
        "customer_id": customer_id,
        "as_of": as_of.isoformat(),
        "delinquency_stage": account["delinquency_stage"] if account else None,
        # Account
        "days_past_due": int(account["days_past_due"] or 0) if account else 0,
        "current_balance": float(account["current_balance"] or 0) if account else 0.0,
        "total_past_due": float(account["total_past_due"] or 0) if account else 0.0,
        # Profile
        "risk_score": int(profile["risk_score"] or 600) if profile and profile["risk_score"] is not None else 600,
        "behavioral_score": int(profile["behavioral_score"] or 50) if profile and profile["behavioral_score"] is not None else 50,
        "tenure_years": round(tenure, 2),
        "prior_delinquencies": prior_delinquencies,
        "prior_cures": prior_cures,
        "active_compliance_flags": int(flags or 0),
        # 7d activity
        "interactions_7d": int(ev["interactions_7d"] or 0) if ev else 0,
        "inbound_7d": int(ev["inbound_7d"] or 0) if ev else 0,
        "outbound_7d": int(ev["outbound_7d"] or 0) if ev else 0,
        "voice_attempts_7d": int(ev["voice_attempts_7d"] or 0) if ev else 0,
        "sms_attempts_7d": int(ev["sms_attempts_7d"] or 0) if ev else 0,
        "email_attempts_7d": int(ev["email_attempts_7d"] or 0) if ev else 0,
        "intent_hardship_7d": int(ev["intent_hardship_7d"] or 0) if ev else 0,
        "intent_ptp_7d": int(ev["intent_ptp_7d"] or 0) if ev else 0,
        "intent_dispute_7d": int(ev["intent_dispute_7d"] or 0) if ev else 0,
        "intent_distress_7d": int(ev["intent_distress_7d"] or 0) if ev else 0,
        "stage_transitions_7d": int(ev["stage_transitions_7d"] or 0) if ev else 0,
        "compliance_blocks_7d": int(ev["compliance_blocks_7d"] or 0) if ev else 0,
        "agent_actions_7d": int(aa["actions_7d"] or 0) if aa else 0,
        "agent_escalations_7d": int(aa["escalations_7d"] or 0) if aa else 0,
        "active_ptp": int(active_ptp or 0),
        "open_escalations": int(open_esc or 0),
    }


def feature_names() -> list[str]:
    return [f["name"] for f in FEATURE_CATALOG]


def feature_vector(features: dict[str, Any]) -> list[float]:
    """Convert a feature dict into the model's input order."""
    return [float(features.get(f["name"], 0) or 0) for f in FEATURE_CATALOG]
