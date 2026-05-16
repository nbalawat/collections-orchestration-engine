"""Activities for compliance checks before dispatching actions."""
from __future__ import annotations

import logging

import httpx
from temporalio import activity

from workflows.types import ActionToDispatch

logger = logging.getLogger(__name__)
OPA_URL = "http://localhost:8181"


@activity.defn
async def check_compliance(
    action: ActionToDispatch,
    compliance_flags: list[str],
    customer_local_hour: int,
    voice_attempts_7d: int,
    channel_attempts_7d: dict | None = None,
    total_attempts_7d: int = 0,
) -> dict:
    opa_input = {
        "compliance_flags": compliance_flags,
        "customer_local_hour": customer_local_hour,
        "voice_attempts_7d": voice_attempts_7d,
        "channel_attempts_7d": channel_attempts_7d or {},
        "total_attempts_7d": total_attempts_7d,
    }
    action_input = {
        "channel": action.channel,
        "action_type": action.action_type,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{OPA_URL}/v1/data/collections/compliance/action_gate",
            json={"input": {**opa_input, "action": action_input}},
        )
        result = resp.json().get("result", {"allowed": False, "reason": "no OPA response"})

    logger.info(
        "Compliance check: action=%s channel=%s allowed=%s reason=%s",
        action.action_type, action.channel, result.get("allowed"), result.get("reason"),
    )
    return result
