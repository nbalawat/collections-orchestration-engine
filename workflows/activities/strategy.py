"""Activities for evaluating collection strategies via OPA."""
from __future__ import annotations

import logging
import os

import asyncpg
import httpx
from temporalio import activity

from services.shared.config import get_settings
from workflows.types import AccountInfo, ContactStats, StrategyDecision

logger = logging.getLogger(__name__)


def _opa_url() -> str:
    return get_settings().opa_url


def _db_dsn() -> str:
    return get_settings().postgres_dsn_sync


async def _resolve_strategy_version(customer_id: str) -> str:
    """Look up the customer's assigned strategy version (champion or challenger).
    If unassigned, randomly allocate based on strategy_versions.allocation_pct weights
    and persist the assignment so future evaluations are stable.
    """
    import random as _random

    try:
        conn = await asyncpg.connect(_db_dsn())
    except Exception:
        return "v1.0.0"

    try:
        existing = await conn.fetchrow(
            "SELECT strategy_version FROM customer_strategy_assignments WHERE customer_id = $1",
            customer_id,
        )
        if existing:
            return existing["strategy_version"]

        versions = await conn.fetch("""
            SELECT strategy_version, allocation_pct FROM strategy_versions
            WHERE role IN ('champion', 'challenger') AND retired_at IS NULL
            ORDER BY allocation_pct DESC
        """)
        if not versions:
            return "v1.0.0"

        total = sum(float(v["allocation_pct"] or 0) for v in versions) or 1.0
        roll = _random.random() * total
        cum = 0.0
        chosen = versions[0]["strategy_version"]
        for v in versions:
            cum += float(v["allocation_pct"] or 0)
            if roll <= cum:
                chosen = v["strategy_version"]
                break

        try:
            await conn.execute("""
                INSERT INTO customer_strategy_assignments (customer_id, strategy_version)
                VALUES ($1, $2)
                ON CONFLICT (customer_id) DO NOTHING
            """, customer_id, chosen)
        except Exception:
            pass

        return chosen
    finally:
        await conn.close()


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

    opa_url = _opa_url()
    async with httpx.AsyncClient() as client:
        seg_resp = await client.post(
            f"{opa_url}/v1/data/collections/segmentation/segment",
            json={"input": opa_input},
        )
        segment = seg_resp.json().get("result", {})

        treat_resp = await client.post(
            f"{opa_url}/v1/data/collections/treatment/treatment",
            json={"input": opa_input},
        )
        treatment = treat_resp.json().get("result", {})

        route_resp = await client.post(
            f"{opa_url}/v1/data/collections/channel_routing/routing",
            json={"input": opa_input},
        )
        routing = route_resp.json().get("result", {})

        comp_resp = await client.post(
            f"{opa_url}/v1/data/collections/compliance/check",
            json={"input": opa_input},
        )
        compliance = comp_resp.json().get("result", {})

        ai_review_resp = await client.post(
            f"{opa_url}/v1/data/collections/treatment/requires_ai_review",
            json={"input": opa_input},
        )
        requires_ai = ai_review_resp.json().get("result", False)

    dpd = account_info.days_past_due
    next_eval = 24.0 if dpd < 30 else 12.0 if dpd < 60 else 8.0 if dpd < 90 else 6.0
    strategy_version = await _resolve_strategy_version(account_info.customer_id)
    opa_input["strategy_version"] = strategy_version

    # Persist the decision rationale — input + outputs — for full audit trail.
    try:
        conn = await asyncpg.connect(_db_dsn())
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
