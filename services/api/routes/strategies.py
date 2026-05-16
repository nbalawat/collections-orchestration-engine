"""Strategy endpoints — OPA policy evaluation, audit log, and configuration."""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.shared.config import get_settings
from services.shared.db import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


@router.post("/evaluate/segmentation")
async def evaluate_segmentation(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/segmentation",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/treatment")
async def evaluate_treatment(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/treatment",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/routing")
async def evaluate_routing(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/channel_routing",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/compliance")
async def evaluate_compliance(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/compliance",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/guardrails")
async def evaluate_guardrails(body: dict):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/ai_guardrails/guardrail_check",
            json={"input": body},
        )
        return resp.json().get("result", {})


@router.post("/evaluate/full")
async def evaluate_full_strategy(body: dict):
    results = {}
    async with httpx.AsyncClient() as client:
        for policy in ["segmentation", "treatment", "channel_routing", "compliance"]:
            url = f"{settings.opa_url}/v1/data/collections/{policy}"
            resp = await client.post(url, json={"input": body})
            results[policy] = resp.json().get("result", {})
    return results


@router.get("/audit-log")
async def get_audit_log(limit: int = 50):
    rows = await execute_query("""
        SELECT * FROM strategy_audit_log
        ORDER BY evaluated_at DESC LIMIT :limit
    """, {"limit": limit})
    return {"audit_log": rows}


@router.get("/config")
async def get_strategy_config():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.opa_url}/v1/data/collections/strategy_config")
        return resp.json().get("result", {})


# ─── Story-driven endpoints: segment matrix, treatment matrix, version diff ──

@router.get("/segment-matrix")
async def segment_matrix():
    """Real distribution of customers across the 2-D strategy segment space:
    DPD bucket × risk tier. Drives the heatmap on the Strategy Console."""
    rows = await execute_query("""
        SELECT
            decision->'segment'->>'dpd_bucket' AS dpd_bucket,
            decision->'segment'->>'risk_tier' AS risk_tier,
            decision->'segment'->>'value_segment' AS value_segment,
            COUNT(*) AS n,
            COUNT(DISTINCT customer_id) AS unique_customers
        FROM strategy_audit_log
        WHERE decision IS NOT NULL
          AND evaluated_at > NOW() - INTERVAL '24 hours'
        GROUP BY dpd_bucket, risk_tier, value_segment
        ORDER BY dpd_bucket, risk_tier
    """)
    return {"cells": rows}


@router.get("/treatment-matrix")
async def treatment_matrix():
    """What treatment action was chosen by segment?"""
    rows = await execute_query("""
        SELECT
            decision->'segment'->>'dpd_bucket' AS dpd_bucket,
            decision->'segment'->>'risk_tier' AS risk_tier,
            decision->'treatment'->>'action' AS treatment_action,
            decision->'treatment'->>'message_tone' AS message_tone,
            COUNT(*) AS n
        FROM strategy_audit_log
        WHERE decision IS NOT NULL
          AND evaluated_at > NOW() - INTERVAL '24 hours'
        GROUP BY dpd_bucket, risk_tier, treatment_action, message_tone
        ORDER BY n DESC
    """)
    return {"rows": rows}


@router.get("/compliance-firing")
async def compliance_firing():
    """Top compliance reasons firing across the platform — what is the policy
    enforcing in practice?"""
    rows = await execute_query("""
        SELECT
            (payload->>'reason') AS reason,
            (payload->>'check_type') AS check_type,
            (payload->>'action_blocked') AS action_blocked,
            (payload->>'passed')::boolean AS passed,
            COUNT(*) AS n
        FROM customer_events
        WHERE event_category = 'compliance'
          AND occurred_at > NOW() - INTERVAL '24 hours'
        GROUP BY reason, check_type, action_blocked, passed
        ORDER BY n DESC
        LIMIT 20
    """)
    return {"reasons": rows}


@router.get("/recent-decisions")
async def recent_decisions(limit: int = 30):
    """Recent strategy_audit_log entries, slim-shaped for UI consumption."""
    rows = await execute_query("""
        SELECT
            audit_id,
            customer_id,
            strategy_version,
            policy_name,
            decision->'segment'->>'dpd_bucket' AS dpd_bucket,
            decision->'segment'->>'risk_tier' AS risk_tier,
            decision->'segment'->>'value_segment' AS value_segment,
            decision->'treatment'->>'action' AS treatment_action,
            decision->'routing'->'recommended_channels' AS recommended_channels,
            decision->'compliance'->>'can_contact' AS can_contact,
            input_context,
            decision,
            evaluated_at
        FROM strategy_audit_log
        WHERE decision IS NOT NULL
        ORDER BY evaluated_at DESC
        LIMIT :limit
    """, {"limit": limit})
    return {"decisions": rows}


@router.get("/version-comparison")
async def version_comparison():
    """Live champion vs challenger comparison built from real strategy_audit_log
    + agent_actions. Drives the A/B story."""
    versions = await execute_query("""
        SELECT
            sv.strategy_version, sv.role, sv.description, sv.allocation_pct,
            sv.activated_at, sv.retired_at,
            (SELECT COUNT(*) FROM customer_strategy_assignments csa WHERE csa.strategy_version = sv.strategy_version) AS assigned_customers
        FROM strategy_versions sv
        ORDER BY
            CASE sv.role WHEN 'champion' THEN 1 WHEN 'challenger' THEN 2 ELSE 3 END
    """)

    per_version_stats = await execute_query("""
        WITH per_v AS (
            SELECT
                COALESCE(csa.strategy_version, 'v1.0.0') AS strategy_version,
                csa.customer_id
            FROM customer_strategy_assignments csa
        )
        SELECT
            per_v.strategy_version,
            COUNT(DISTINCT per_v.customer_id) AS customers,
            COUNT(DISTINCT sal.audit_id) FILTER (WHERE sal.evaluated_at > NOW() - INTERVAL '24 hours') AS evaluations_24h,
            COUNT(DISTINCT aa.action_id) FILTER (WHERE aa.created_at > NOW() - INTERVAL '24 hours') AS agent_actions_24h,
            COUNT(DISTINCT aa.action_id) FILTER (WHERE aa.status = 'escalated' AND aa.created_at > NOW() - INTERVAL '24 hours') AS escalations_24h,
            COUNT(DISTINCT cured.customer_id) AS cures_24h,
            AVG(aa.confidence) FILTER (WHERE aa.created_at > NOW() - INTERVAL '24 hours')::numeric(4,3) AS avg_confidence
        FROM per_v
        LEFT JOIN strategy_audit_log sal ON sal.customer_id = per_v.customer_id
        LEFT JOIN agent_actions aa ON aa.customer_id = per_v.customer_id
        LEFT JOIN (
            SELECT DISTINCT customer_id FROM customer_events
            WHERE event_type LIKE 'stage_change:%->CURED'
              AND occurred_at > NOW() - INTERVAL '24 hours'
        ) cured ON cured.customer_id = per_v.customer_id
        GROUP BY per_v.strategy_version
    """)

    stats_by_v: dict = {r["strategy_version"]: r for r in per_version_stats}
    for v in versions:
        s = stats_by_v.get(v["strategy_version"], {})
        v["customers_24h"] = int(s.get("customers") or 0)
        v["evaluations_24h"] = int(s.get("evaluations_24h") or 0)
        v["agent_actions_24h"] = int(s.get("agent_actions_24h") or 0)
        v["escalations_24h"] = int(s.get("escalations_24h") or 0)
        v["cures_24h"] = int(s.get("cures_24h") or 0)
        v["avg_confidence"] = float(s["avg_confidence"]) if s.get("avg_confidence") is not None else None
        v["cure_rate_24h"] = round((v["cures_24h"] / v["customers_24h"]) * 100, 2) if v["customers_24h"] else None

    return {"versions": versions}


class SideBySideRequest(BaseModel):
    customer_input: dict


@router.post("/evaluate-side-by-side")
async def evaluate_side_by_side(req: SideBySideRequest):
    """Run the same input through every loaded strategy version — for the
    side-by-side case study card."""
    versions = await execute_query("""
        SELECT strategy_version, role, description
        FROM strategy_versions
        WHERE retired_at IS NULL
        ORDER BY CASE role WHEN 'champion' THEN 1 WHEN 'challenger' THEN 2 ELSE 3 END
    """)
    if not versions:
        versions = [{"strategy_version": "v1.0.0", "role": "champion", "description": "default"}]
    results = []
    async with httpx.AsyncClient() as client:
        for v in versions:
            policy_results = {}
            for policy in ["segmentation", "treatment", "channel_routing", "compliance"]:
                resp = await client.post(
                    f"{settings.opa_url}/v1/data/collections/{policy}",
                    json={"input": {**req.customer_input, "strategy_version": v["strategy_version"]}},
                )
                policy_results[policy] = resp.json().get("result", {})
            results.append({
                "strategy_version": v["strategy_version"],
                "role": v["role"],
                "description": v["description"],
                "policies": policy_results,
            })
    return {"results": results}


@router.get("/version-timeline")
async def version_timeline():
    """Timeline of strategy version activations + a daily-evaluations slice."""
    versions = await execute_query("""
        SELECT strategy_version, role, description, allocation_pct,
               activated_at, retired_at
        FROM strategy_versions
        ORDER BY activated_at NULLS FIRST
    """)
    by_day = await execute_query("""
        SELECT strategy_version,
               DATE_TRUNC('day', evaluated_at) AS day,
               COUNT(*) AS evaluations
        FROM strategy_audit_log
        WHERE evaluated_at > NOW() - INTERVAL '14 days'
        GROUP BY strategy_version, day
        ORDER BY day, strategy_version
    """)
    return {"versions": versions, "daily_evaluations": by_day}
