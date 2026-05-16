"""Activities for evaluating collection strategies via OPA."""
from __future__ import annotations

import logging
import os

import asyncpg
import httpx
from temporalio import activity

from workflows.types import AccountInfo, ContactStats, StrategyDecision

logger = logging.getLogger(__name__)
OPA_URL = "http://localhost:8181"
DB_DSN = "postgresql://collections:collections@localhost:5432/collections"


async def _current_strategy_version() -> str:
    """Read the live strategy version from strategy_audit_log, falling back to v1.0.0."""
    try:
        conn = await asyncpg.connect(DB_DSN)
        try:
            row = await conn.fetchrow("""
                SELECT strategy_version FROM strategy_audit_log
                WHERE strategy_version IS NOT NULL
                ORDER BY evaluated_at DESC NULLS LAST LIMIT 1
            """)
            return (row["strategy_version"] if row else None) or "v1.0.0"
        finally:
            await conn.close()
    except Exception:
        return "v1.0.0"


@activity.defn
async def evaluate_strategy(account_info: AccountInfo, stats: ContactStats | None = None) -> StrategyDecision:
    stats = stats or ContactStats()
    opa_input = {
        "dpd": account_info.days_past_due,
        "balance": account_info.current_balance,
        "risk_score": account_info.risk_score or 600,
        "relationship_value": account_info.relationship_value,
        "relationship_tenure_years": account_info.relationship_tenure_years,
        "prior_delinquencies": account_info.prior_delinquencies,
        "prior_cures": account_info.prior_cures,
        "hardship_flag": "HARDSHIP" in (account_info.compliance_flags or []),
        "compliance_flags": account_info.compliance_flags or [],
        "failed_channels": stats.failed_channels,
        "channel_attempts_7d": stats.channel_attempts_7d,
        "voice_attempts_7d": stats.voice_attempts_7d,
        "customer_local_hour": stats.customer_local_hour,
        "late_fee_amount": account_info.minimum_payment * 0.5,
        "recent_income_change": False,  # No income-signal table yet; surface as known-unknown
        "conflicting_signals": stats.conflicting_signals,
        "last_inbound_intent": stats.last_inbound_intent,
        "preferred_channel": account_info.preferred_channel,
    }

    async with httpx.AsyncClient() as client:
        seg_resp = await client.post(
            f"{OPA_URL}/v1/data/collections/segmentation/segment",
            json={"input": opa_input},
        )
        segment = seg_resp.json().get("result", {})

        treat_resp = await client.post(
            f"{OPA_URL}/v1/data/collections/treatment/treatment",
            json={"input": opa_input},
        )
        treatment = treat_resp.json().get("result", {})

        route_resp = await client.post(
            f"{OPA_URL}/v1/data/collections/channel_routing/routing",
            json={"input": opa_input},
        )
        routing = route_resp.json().get("result", {})

        comp_resp = await client.post(
            f"{OPA_URL}/v1/data/collections/compliance/check",
            json={"input": opa_input},
        )
        compliance = comp_resp.json().get("result", {})

        ai_review_resp = await client.post(
            f"{OPA_URL}/v1/data/collections/treatment/requires_ai_review",
            json={"input": opa_input},
        )
        requires_ai = ai_review_resp.json().get("result", False)

    dpd = account_info.days_past_due
    next_eval = 24.0 if dpd < 30 else 12.0 if dpd < 60 else 8.0 if dpd < 90 else 6.0
    strategy_version = await _current_strategy_version()

    # Persist the decision rationale — input + outputs — for full audit trail.
    try:
        conn = await asyncpg.connect(DB_DSN)
        try:
            import uuid as _uuid
            await conn.execute("""
                INSERT INTO strategy_audit_log (audit_id, customer_id, strategy_version,
                                                policy_name, input_context, decision)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            """,
                _uuid.uuid4(),
                account_info.customer_id,
                strategy_version,
                "collections.treatment",
                _json_dumps({"opa_input": opa_input}),
                _json_dumps({
                    "segment": segment,
                    "treatment": treatment,
                    "routing": routing,
                    "compliance": compliance,
                    "requires_ai_review": requires_ai,
                }),
            )
        finally:
            await conn.close()
    except Exception:
        logger.exception("Failed to record strategy_audit_log entry")

    return StrategyDecision(
        segment=segment,
        treatment=treatment,
        routing=routing,
        compliance=compliance,
        requires_ai_review=requires_ai,
        strategy_version=strategy_version,
        next_eval_hours=next_eval,
    )


def _json_dumps(obj) -> str:
    import json as _json
    return _json.dumps(obj, default=str)
