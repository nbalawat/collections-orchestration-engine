"""Agent Copilot — real-time AI assistant for human collections agents.

Sits alongside human agents during live calls. Provides next-best-action suggestions,
pre-fills forms, generates call summaries, and surfaces relevant customer context.
Never acts directly — only advises and assists.
"""
from __future__ import annotations

from events.models import AgentType
from services.ai_agents.base_agent import CollectionsAgent
from services.ai_agents.tools import (
    lookup_customer_360,
    get_journey_state,
    get_applicable_offers,
    check_compliance,
    check_guardrails,
    suggest_next_best_action,
    generate_call_summary,
    prefill_form,
    create_case_note,
)


class CopilotAgent(CollectionsAgent):
    agent_type = AgentType.COPILOT
    model = "claude-sonnet-4-6"
    max_tokens = 4096

    def get_system_prompt(self) -> str:
        return """You are an AI copilot assisting a human collections agent during a live customer interaction.

## Your Role
- Provide real-time suggestions and context to help the human agent
- You NEVER interact with the customer directly — you only advise the human agent
- Surface relevant customer information proactively
- Suggest next-best-actions based on the customer's situation
- Pre-fill forms to save the agent time
- Generate call summaries after interactions

## What You Should Do
1. Look up the customer's full profile and journey state
2. Identify available offers and compliance constraints
3. Suggest the most appropriate next action with clear rationale
4. Pre-fill any relevant forms (PTP, hardship, settlement, call notes)
5. When the interaction ends, generate a structured call summary

## Output Format
Structure your suggestions clearly for the agent:
- **Customer Context**: Key facts about this customer
- **Compliance Alerts**: Any flags or restrictions
- **Suggested Action**: What to do next and why
- **Talking Points**: Key things to say
- **Available Offers**: What can be offered

## Guidelines
- Be concise — the agent is on a live call
- Lead with the most important information
- Flag compliance risks prominently
- Provide specific numbers (offer amounts, DPD, balances)
- If you detect the customer might be in distress, alert the agent immediately"""

    def get_tools(self) -> list:
        return [
            lookup_customer_360,
            get_journey_state,
            get_applicable_offers,
            check_compliance,
            check_guardrails,
            suggest_next_best_action,
            generate_call_summary,
            prefill_form,
            create_case_note,
        ]

    def _build_user_message(self, context: dict) -> str:
        customer_id = context.get("customer_id", "unknown")
        request_type = context.get("request_type", "nba")
        channel = context.get("channel", "voice")
        interaction_context = context.get("interaction_context", "")

        if request_type == "call_summary":
            return f"""Generate a call summary for the interaction with customer {customer_id}.
Call details: {interaction_context}
Duration: {context.get('duration_seconds', 0)} seconds
Channel: {channel}

Look up the customer, then create a comprehensive call summary."""

        if request_type == "prefill":
            form_type = context.get("form_type", "ptp")
            return f"""Pre-fill a {form_type} form for customer {customer_id}.
Look up the customer profile and account details, then populate the form fields."""

        return f"""A human agent is about to interact with customer {customer_id} via {channel}.
{f'Context: {interaction_context}' if interaction_context else ''}

Prepare a briefing for the agent:
1. Look up the full customer profile
2. Check their journey state
3. Review available offers and compliance constraints
4. Suggest the best approach for this interaction"""
