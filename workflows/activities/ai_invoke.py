"""Activity for invoking AI agents from inside a Temporal workflow.

Auto-fires the Digital Channel Agent when an inbound customer message arrives
with a non-trivial intent. The agent does the real Claude API call, persists
its decision to agent_actions, and returns the structured result.
"""
from __future__ import annotations

import logging

from temporalio import activity

logger = logging.getLogger(__name__)

# Intents that warrant an autonomous AI response
AUTO_AGENT_INTENTS = {
    "HARDSHIP", "DISPUTE", "DISTRESS", "PTP",
    "SETTLEMENT_INQUIRY", "REFUSAL_TO_PAY", "COMPLAINT",
}


@activity.defn
async def invoke_digital_channel_agent(
    customer_id: str,
    workflow_id: str,
    message: str,
    channel: str,
    intent: str | None,
) -> dict:
    """Invoke the digital channel agent with full context. Returns the structured
    decision (action_type, confidence, rationale) plus reasoning trace."""
    # Lazy import — these modules pull in the Anthropic SDK
    from services.ai_agents.digital_channel_agent import DigitalChannelAgent

    agent = DigitalChannelAgent()
    result = await agent.invoke({
        "customer_id": customer_id,
        "workflow_id": workflow_id,
        "message": message,
        "channel": channel,
        "intent": intent,
    })
    logger.info(
        "AI agent finished for %s: action=%s confidence=%.2f escalated=%s",
        customer_id,
        result.get("action_taken"),
        result.get("confidence", 0.0),
        result.get("escalated"),
    )
    return result


def should_invoke_agent(intent: str | None) -> bool:
    return intent in AUTO_AGENT_INTENTS if intent else False
