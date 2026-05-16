"""The required closing tool every AI agent must call before ending its turn.

The LLM emits a structured payload via this tool call. The harness captures the
payload from the tool_use block directly — not by parsing free text.
"""
from __future__ import annotations

import json
from anthropic import beta_async_tool


@beta_async_tool
async def record_decision(
    action_type: str,
    confidence: float,
    rationale: str,
    escalate: bool = False,
    parameters: str = "{}",
) -> str:
    """Record your final decision for this interaction. You MUST call this
    before ending your turn — without it, the orchestrator treats your work
    as incomplete and escalates.

    action_type: a concrete action keyword (e.g. `sent_payment_link`,
                 `recorded_ptp`, `initiated_hardship`, `escalated_to_human`,
                 `responded`, `no_action_needed`, or a domain-specific action)
    confidence:  0.0–1.0, CALIBRATED to your actual evidence.
                 Do not default to 0.85; reflect uncertainty honestly.
    rationale:   1-3 sentences explaining WHY this action, citing the evidence.
    escalate:    true if a human should review or take over.
    parameters:  JSON string with structured parameters (amounts, dates,
                 channels, IDs, etc.).
    """
    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError:
        params = {"raw": parameters}
    confidence = max(0.0, min(1.0, float(confidence)))
    return json.dumps({
        "status": "decision_recorded",
        "action_type": action_type,
        "confidence": confidence,
        "rationale": rationale,
        "escalate": escalate,
        "parameters": params,
    })
