"""Case Reasoning Agent — deep analysis for complex or escalated cases.

Handles cases with conflicting signals, multiple treatment paths, or high-value decisions.
Evaluates all available evidence, models different outcomes, and produces a reasoned
recommendation with full audit trail. Designed for the AI Reasoning Explorer UI.
"""
from __future__ import annotations

from events.models import AgentType
from services.ai_agents.base_agent import CollectionsAgent
from services.ai_agents.tools import (
    lookup_customer_360,
    get_journey_state,
    get_full_history,
    get_applicable_offers,
    check_compliance,
    check_guardrails,
    evaluate_treatment_paths,
    recommend_action,
    create_case_note,
    escalate_to_human,
)


class CaseReasoningAgent(CollectionsAgent):
    agent_type = AgentType.CASE_REASONING
    model = "claude-sonnet-4-6"
    max_tokens = 6144

    def get_system_prompt(self) -> str:
        return """You are a specialist case reasoning agent for complex collections cases.

## Your Role
- Analyze cases that have conflicting signals or require nuanced judgment
- Evaluate multiple treatment paths and their likely outcomes
- Produce a well-reasoned recommendation with clear rationale
- Your analysis is displayed in the AI Reasoning Explorer — be thorough and transparent

## Analysis Framework
1. **Gather Evidence**: Pull the full customer profile, complete history, and journey state
2. **Identify Signals**: What are the positive and negative indicators?
   - Payment history patterns (improving? deteriorating?)
   - Communication engagement (responding? ghosting?)
   - Life events (hardship? new job? bankruptcy?)
   - Compliance constraints
3. **Evaluate Paths**: Compare treatment options using evaluate_treatment_paths
   - Standard dunning, hardship program, settlement, arrangement
   - For each: estimated recovery, timeline, risk
4. **Reason Through**: Weigh the evidence and explain your thinking step by step
5. **Recommend**: Make a specific recommendation with confidence level

## Output Structure
Your final response should include:
- **Case Summary**: 2-3 sentence overview
- **Key Findings**: Bullet points of important evidence
- **Signal Analysis**: Positive vs. negative indicators
- **Treatment Path Comparison**: Table or comparison of options
- **Recommendation**: Specific action with rationale
- **Confidence Level**: High/Medium/Low with explanation
- **Risk Factors**: What could go wrong

## Guidelines
- Be objective — let the data drive your recommendation
- Acknowledge uncertainty explicitly
- If confidence is below 70%, recommend human specialist review
- Always check compliance and guardrails before recommending any action
- Consider the customer's full history, not just the current interaction"""

    def get_tools(self) -> list:
        return [
            lookup_customer_360,
            get_journey_state,
            get_full_history,
            get_applicable_offers,
            check_compliance,
            check_guardrails,
            evaluate_treatment_paths,
            recommend_action,
            create_case_note,
            escalate_to_human,
        ]

    def _build_user_message(self, context: dict) -> str:
        customer_id = context.get("customer_id", "unknown")
        reason = context.get("reason", "complex case requiring analysis")
        trigger = context.get("trigger", "")
        prior_actions = context.get("prior_actions", [])

        msg = f"""Analyze the complex case for customer {customer_id}.

Reason for escalation: {reason}
{f'Trigger event: {trigger}' if trigger else ''}
{f'Prior actions taken: {", ".join(prior_actions)}' if prior_actions else ''}

Perform a thorough analysis:
1. Get the full customer profile and complete interaction history
2. Check the current journey state
3. Evaluate all available treatment paths
4. Check compliance and guardrails
5. Produce a reasoned recommendation with confidence level"""

        return msg
