"""Activities for evaluating collection strategies via OPA."""
from __future__ import annotations

import logging

import httpx
from temporalio import activity

from workflows.types import AccountInfo, StrategyDecision

logger = logging.getLogger(__name__)
OPA_URL = "http://localhost:8181"


@activity.defn
async def evaluate_strategy(account_info: AccountInfo) -> StrategyDecision:
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
        "failed_channels": [],
        "channel_attempts_7d": {},
        "voice_attempts_7d": 0,
        "customer_local_hour": 14,
        "late_fee_amount": account_info.minimum_payment * 0.5,
        "recent_income_change": False,
        "conflicting_signals": [],
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

    return StrategyDecision(
        segment=segment,
        treatment=treatment,
        routing=routing,
        compliance=compliance,
        requires_ai_review=requires_ai,
        strategy_version="v1.0.0",
        next_eval_hours=next_eval,
    )
