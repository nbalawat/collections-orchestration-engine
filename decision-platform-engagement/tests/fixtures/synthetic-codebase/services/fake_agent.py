"""[PLANTED MOCK #1 — Critical]

This "AI agent" doesn't actually call any LLM. It keyword-matches the user's
message to infer an action, then returns a hardcoded confidence. The audit
should catch this immediately.
"""
from __future__ import annotations


class FakeCustomerAgent:
    """Pretends to be an AI agent. Actually a keyword router."""

    def invoke(self, customer_id: str, message: str) -> dict:
        message_lower = message.lower()

        # ANTIPATTERN: keyword matching free text to infer AI action
        if "hardship" in message_lower or "lost my job" in message_lower:
            action = "initiated_hardship"
        elif "pay" in message_lower or "ptp" in message_lower:
            action = "recorded_ptp"
        elif "dispute" in message_lower:
            action = "flagged_dispute"
        else:
            action = "no_action"

        # ANTIPATTERN: hardcoded confidence dressed as AI output
        return {
            "action_taken": action,
            "confidence": 0.85,
            "rationale": "AI agent processed the customer message.",
        }
