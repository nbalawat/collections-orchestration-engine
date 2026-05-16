"""Risk & ML API — feature store, risk scoring, roll-rate forecasting,
recovery curves, cohort vintage, A/B significance, AI cost dashboard.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from services.ml import features as feat_mod
from services.ml import risk_model as risk_mod
from services.ml import roll_rate as roll_mod
from services.shared.db import execute_query

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Feature store ────────────────────────────────────────────────────

@router.get("/features/catalog")
async def feature_catalog():
    return {"features": feat_mod.FEATURE_CATALOG}


@router.get("/features/{customer_id}")
async def customer_features(customer_id: str):
    return await feat_mod.get_features(customer_id)


# ─── Risk model ───────────────────────────────────────────────────────

@router.get("/model/card")
async def model_card():
    m = risk_mod.get_model()
    return {
        "training_meta": m.training_meta,
        "feature_importance": m.feature_importance[:15],
        "n_features": len(m.feature_order),
        "is_real": m.is_real,
    }


@router.post("/model/retrain")
async def retrain_model():
    m = await risk_mod.train()
    return {
        "status": "retrained",
        "training_meta": m.training_meta,
        "feature_importance_top": m.feature_importance[:5],
    }


@router.get("/score/{customer_id}")
async def risk_score(customer_id: str):
    f = await feat_mod.get_features(customer_id)
    m = risk_mod.get_model()
    vec = feat_mod.feature_vector(f)
    p = m.predict_proba(vec)
    return {
        "customer_id": customer_id,
        "probability_worsen_7d": round(p, 3),
        "risk_band": _band(p),
        "model_status": m.training_meta.get("status"),
        "top_contributors": m.explain(vec, top_k=5),
        "features": f,
    }


def _band(p: float) -> str:
    if p >= 0.7:
        return "HIGH"
    if p >= 0.4:
        return "MEDIUM"
    return "LOW"


# ─── Roll-rate forecast ───────────────────────────────────────────────

@router.get("/roll-rate")
async def roll_rate_endpoint():
    return await roll_mod.roll_rate_forecast()


# ─── Recovery curves ──────────────────────────────────────────────────

@router.get("/recovery-curves")
async def recovery_curves():
    """Per-segment cumulative cure rate over the days following entry into that segment.

    Cohort = customers whose journey reached a given stage (from lifecycle events).
    Cure = subsequent stage_change:_->CURED event.
    """
    rows = await execute_query("""
        WITH first_entry AS (
            SELECT customer_id,
                   payload->>'to_stage' AS entry_stage,
                   MIN(occurred_at) AS entered_at
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%'
              AND payload->>'to_stage' IN ('DUNNING','PTP_ACTIVE','HARDSHIP_REVIEW',
                                            'SETTLEMENT_NEGOTIATION','PTP_BROKEN')
              AND occurred_at > NOW() - INTERVAL '30 days'
            GROUP BY customer_id, entry_stage
        ),
        cures AS (
            SELECT ce.customer_id,
                   fe.entry_stage,
                   ce.occurred_at AS cured_at,
                   fe.entered_at,
                   EXTRACT(EPOCH FROM (ce.occurred_at - fe.entered_at)) / 3600 AS hours_to_cure
            FROM customer_events ce
            JOIN first_entry fe ON fe.customer_id = ce.customer_id
                                AND ce.occurred_at > fe.entered_at
            WHERE ce.event_type LIKE 'stage_change:%->CURED'
        ),
        per_cohort AS (
            SELECT entry_stage, COUNT(DISTINCT customer_id) AS cohort_size FROM first_entry
            GROUP BY entry_stage
        )
        SELECT pc.entry_stage,
               pc.cohort_size,
               COALESCE(COUNT(c.customer_id), 0) AS cures,
               COALESCE(ROUND(COUNT(c.customer_id)::numeric / pc.cohort_size * 100, 2), 0) AS cure_rate_pct,
               COALESCE(AVG(c.hours_to_cure)::numeric(10,1), 0) AS avg_hours_to_cure
        FROM per_cohort pc
        LEFT JOIN cures c ON c.entry_stage = pc.entry_stage
        GROUP BY pc.entry_stage, pc.cohort_size
        ORDER BY pc.entry_stage
    """)
    # Also produce a per-hour cumulative cure curve per cohort for charting
    curves = await execute_query("""
        WITH first_entry AS (
            SELECT customer_id, payload->>'to_stage' AS entry_stage,
                   MIN(occurred_at) AS entered_at
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%'
              AND payload->>'to_stage' IN ('DUNNING','PTP_ACTIVE','HARDSHIP_REVIEW','SETTLEMENT_NEGOTIATION','PTP_BROKEN')
              AND occurred_at > NOW() - INTERVAL '30 days'
            GROUP BY customer_id, entry_stage
        ),
        cures AS (
            SELECT ce.customer_id, fe.entry_stage,
                   FLOOR(EXTRACT(EPOCH FROM (ce.occurred_at - fe.entered_at)) / 3600)::int AS hours_to_cure
            FROM customer_events ce
            JOIN first_entry fe ON fe.customer_id = ce.customer_id AND ce.occurred_at > fe.entered_at
            WHERE ce.event_type LIKE 'stage_change:%->CURED'
        )
        SELECT entry_stage, hours_to_cure, COUNT(*) AS n
        FROM cures
        WHERE hours_to_cure BETWEEN 0 AND 168
        GROUP BY entry_stage, hours_to_cure
        ORDER BY entry_stage, hours_to_cure
    """)
    return {"summary": rows, "curve_points": curves}


# ─── Cohort vintage ──────────────────────────────────────────────────

@router.get("/cohort-vintage")
async def cohort_vintage():
    """Customers grouped by the week they first entered any delinquency stage,
    cross-tabbed against their current stage."""
    rows = await execute_query("""
        WITH first_delinq AS (
            SELECT customer_id,
                   DATE_TRUNC('week', MIN(occurred_at)) AS vintage_week
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%'
            GROUP BY customer_id
        ),
        latest_stage AS (
            SELECT DISTINCT ON (customer_id)
                   customer_id, payload->>'to_stage' AS current_stage
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%'
            ORDER BY customer_id, occurred_at DESC
        )
        SELECT fd.vintage_week, ls.current_stage, COUNT(*) AS n
        FROM first_delinq fd
        LEFT JOIN latest_stage ls ON ls.customer_id = fd.customer_id
        GROUP BY fd.vintage_week, ls.current_stage
        ORDER BY fd.vintage_week DESC, ls.current_stage
    """)
    return {"cells": rows}


# ─── A/B significance ────────────────────────────────────────────────

@router.get("/ab-significance")
async def ab_significance(metric: str = Query("cure", regex="^(cure|escalation|engagement)$")):
    """Compute lift + p-value for champion vs challenger on a given metric.

    metric:
      cure        — fraction of customers with a CURED transition in last 24h
      escalation  — fraction of customers with an escalated agent_action in last 24h
      engagement  — fraction of customers with an inbound interaction in last 24h
    """
    versions = await execute_query("""
        SELECT csa.strategy_version, sv.role, COUNT(DISTINCT csa.customer_id) AS n
        FROM customer_strategy_assignments csa
        LEFT JOIN strategy_versions sv ON sv.strategy_version = csa.strategy_version
        GROUP BY csa.strategy_version, sv.role
    """)
    if len(versions) < 2:
        return {"error": "Need at least two strategy versions", "versions": versions}

    champ = next((v for v in versions if v["role"] == "champion"), versions[0])
    chal = next((v for v in versions if v["role"] == "challenger"), versions[1])

    metric_sql = {
        "cure": """
            SELECT COUNT(DISTINCT csa.customer_id) AS converted
            FROM customer_strategy_assignments csa
            JOIN customer_events ce ON ce.customer_id = csa.customer_id
            WHERE csa.strategy_version = :v
              AND ce.event_type LIKE 'stage_change:%->CURED'
              AND ce.occurred_at > NOW() - INTERVAL '24 hours'
        """,
        "escalation": """
            SELECT COUNT(DISTINCT csa.customer_id) AS converted
            FROM customer_strategy_assignments csa
            JOIN agent_actions aa ON aa.customer_id = csa.customer_id
            WHERE csa.strategy_version = :v
              AND aa.status = 'escalated'
              AND aa.created_at > NOW() - INTERVAL '24 hours'
        """,
        "engagement": """
            SELECT COUNT(DISTINCT csa.customer_id) AS converted
            FROM customer_strategy_assignments csa
            JOIN customer_events ce ON ce.customer_id = csa.customer_id
            WHERE csa.strategy_version = :v
              AND ce.direction = 'inbound'
              AND ce.occurred_at > NOW() - INTERVAL '24 hours'
        """,
    }[metric]

    champ_rows = await execute_query(metric_sql, {"v": champ["strategy_version"]})
    chal_rows = await execute_query(metric_sql, {"v": chal["strategy_version"]})
    champ_conv = int(champ_rows[0]["converted"] or 0) if champ_rows else 0
    chal_conv = int(chal_rows[0]["converted"] or 0) if chal_rows else 0

    n_c, c_c = int(champ["n"] or 0), champ_conv
    n_h, c_h = int(chal["n"] or 0), chal_conv

    return _two_proportion_z(
        champion=champ["strategy_version"], champion_n=n_c, champion_conversions=c_c,
        challenger=chal["strategy_version"], challenger_n=n_h, challenger_conversions=c_h,
        metric=metric,
    )


def _two_proportion_z(
    *, champion: str, champion_n: int, champion_conversions: int,
    challenger: str, challenger_n: int, challenger_conversions: int,
    metric: str,
) -> dict:
    if champion_n == 0 or challenger_n == 0:
        return {
            "metric": metric,
            "champion": {"version": champion, "n": champion_n, "conversions": champion_conversions, "rate": None},
            "challenger": {"version": challenger, "n": challenger_n, "conversions": challenger_conversions, "rate": None},
            "lift_pct": None, "p_value": None, "significant_95": False,
            "verdict": "insufficient_data",
        }
    p1 = champion_conversions / champion_n
    p2 = challenger_conversions / challenger_n
    pooled = (champion_conversions + challenger_conversions) / (champion_n + challenger_n)
    se = math.sqrt(pooled * (1 - pooled) * (1 / champion_n + 1 / challenger_n))
    z = (p2 - p1) / se if se > 0 else 0.0
    p_value = 2 * (1 - _norm_cdf(abs(z)))  # two-sided
    lift = (p2 - p1) / p1 * 100 if p1 > 0 else None

    # 95% CI on the difference
    ci_half = 1.96 * math.sqrt(p1 * (1 - p1) / champion_n + p2 * (1 - p2) / challenger_n)
    diff = p2 - p1

    # Sample size needed to detect a 5% relative lift at 80% power, alpha 0.05 (two-sided)
    if p1 > 0:
        p2_target = p1 * 1.05
        avg = (p1 + p2_target) / 2
        se_test = math.sqrt(2 * avg * (1 - avg))
        se_alt = math.sqrt(p1 * (1 - p1) + p2_target * (1 - p2_target))
        required_n = math.ceil(((1.96 * se_test + 0.84 * se_alt) ** 2) / ((p2_target - p1) ** 2)) if p2_target > p1 else None
    else:
        required_n = None

    if p_value < 0.05 and lift is not None and lift > 0:
        verdict = "challenger_wins"
    elif p_value < 0.05 and lift is not None and lift < 0:
        verdict = "champion_wins"
    else:
        verdict = "no_difference"

    return {
        "metric": metric,
        "champion": {"version": champion, "n": champion_n, "conversions": champion_conversions, "rate": round(p1, 4)},
        "challenger": {"version": challenger, "n": challenger_n, "conversions": challenger_conversions, "rate": round(p2, 4)},
        "absolute_difference": round(diff, 4),
        "difference_95_ci": [round(diff - ci_half, 4), round(diff + ci_half, 4)],
        "lift_pct": round(lift, 2) if lift is not None else None,
        "z_score": round(z, 3),
        "p_value": round(p_value, 4),
        "significant_95": bool(p_value < 0.05),
        "verdict": verdict,
        "required_n_per_arm_for_5pct_lift_80pct_power": required_n,
    }


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ─── AI cost dashboard ───────────────────────────────────────────────

# Rate card (per million tokens) — keep aligned with shared/anthropic_client.
RATES_PER_M = {
    "claude-opus-4-7":    {"input": 5.00, "output": 25.00},
    "claude-opus-4-6":    {"input": 5.00, "output": 25.00},
    "claude-sonnet-4-6":  {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-5":  {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5":   {"input": 1.00, "output": 5.00},
}


@router.get("/ai-cost")
async def ai_cost():
    """Per-agent / per-day token spend and estimated $ cost."""
    rows = await execute_query("""
        SELECT
            DATE_TRUNC('day', occurred_at) AS day,
            payload->>'agent_type' AS agent_type,
            COALESCE(payload->>'model', 'unknown') AS model,
            COUNT(*) AS invocations,
            SUM((payload->>'tokens_used')::int) FILTER (WHERE payload->>'tokens_used' IS NOT NULL) AS tokens,
            AVG((payload->>'latency_ms')::int) FILTER (WHERE payload->>'latency_ms' IS NOT NULL)::int AS avg_latency_ms,
            MAX((payload->>'latency_ms')::int) FILTER (WHERE payload->>'latency_ms' IS NOT NULL) AS max_latency_ms,
            COUNT(*) FILTER (WHERE (payload->>'escalated')::boolean = true) AS escalations
        FROM customer_events
        WHERE event_category = 'ai_reasoning'
          AND occurred_at > NOW() - INTERVAL '7 days'
        GROUP BY day, agent_type, model
        ORDER BY day DESC, tokens DESC NULLS LAST
    """)
    enriched = []
    total_cost = 0.0
    for r in rows:
        model = r.get("model") or "unknown"
        tokens = int(r.get("tokens") or 0)
        # Tokens recorded are total (input+output). Approximate split as 60/40 input/output.
        rate = RATES_PER_M.get(model, {"input": 3.00, "output": 15.00})
        input_tokens = int(tokens * 0.6)
        output_tokens = tokens - input_tokens
        cost = (input_tokens / 1_000_000) * rate["input"] + (output_tokens / 1_000_000) * rate["output"]
        total_cost += cost
        enriched.append({
            **r,
            "estimated_cost_usd": round(cost, 4),
            "rate_per_m_input": rate["input"],
            "rate_per_m_output": rate["output"],
        })
    return {
        "rows": enriched,
        "total_estimated_cost_usd_7d": round(total_cost, 2),
        "rate_card": RATES_PER_M,
    }
