"""Python wrapper for the OPA action_gate policy. Emit compliance events on
BOTH pass and fail — full evaluation log, not denial log.
"""
from __future__ import annotations

import httpx

OPA_URL = "http://localhost:8181"  # adapt


async def check_action_gate(
    *,
    action_type: str,
    channel: str,
    compliance_flags: list[str],
    customer_local_hour: int,
    voice_attempts_7d: int,
    channel_attempts_7d: dict[str, int] | None = None,
    total_attempts_7d: int = 0,
) -> dict:
    opa_input = {
        "compliance_flags": compliance_flags,
        "customer_local_hour": customer_local_hour,
        "voice_attempts_7d": voice_attempts_7d,
        "channel_attempts_7d": channel_attempts_7d or {},
        "total_attempts_7d": total_attempts_7d,
        "action": {"channel": channel, "action_type": action_type},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{OPA_URL}/v1/data/collections/compliance/action_gate",
            json={"input": opa_input},
        )
        result = resp.json().get("result", {"allowed": False, "reason": "no OPA response"})
    return result


async def publish_compliance_event(
    *,
    customer_id: str,
    workflow_id: str,
    check_type: str,
    passed: bool,
    reason: str,
    details: dict,
    action_blocked: str | None,
    trace_id: str | None,
):
    """Adapt to your event-publish helper. The key point: emit on PASS and FAIL —
    full evaluation log, not denial log. Auditors need the complete record."""
    raise NotImplementedError("plug in your project's event publisher")


async def evaluate_and_log(
    *,
    customer_id: str,
    workflow_id: str,
    action_type: str,
    channel: str,
    compliance_flags: list[str],
    customer_local_hour: int,
    voice_attempts_7d: int,
    channel_attempts_7d: dict[str, int],
    total_attempts_7d: int,
    trace_id: str | None,
) -> dict:
    result = await check_action_gate(
        action_type=action_type, channel=channel,
        compliance_flags=compliance_flags,
        customer_local_hour=customer_local_hour,
        voice_attempts_7d=voice_attempts_7d,
        channel_attempts_7d=channel_attempts_7d,
        total_attempts_7d=total_attempts_7d,
    )
    await publish_compliance_event(
        customer_id=customer_id, workflow_id=workflow_id,
        check_type="action_gate",
        passed=bool(result.get("allowed", False)),
        reason=result.get("reason", ""),
        details=result,
        action_blocked=None if result.get("allowed") else action_type,
        trace_id=trace_id,
    )
    return result
