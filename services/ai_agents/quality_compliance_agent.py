"""Quality & Compliance Agent — reviews interactions for quality and regulatory compliance.

Analyzes interaction transcripts against compliance rules (FDCPA, Reg F, state laws),
scores quality dimensions (compliance, tone, accuracy, completeness), and generates
coaching notes for agent development. Runs post-interaction or on-demand.
"""
from __future__ import annotations

from events.models import AgentType
from services.ai_agents.base_agent import CollectionsAgent
from services.ai_agents.tools import (
    lookup_customer_360,
    get_interaction_transcript,
    check_compliance_rules,
    score_interaction,
    generate_coaching_notes,
    create_case_note,
)


class QualityComplianceAgent(CollectionsAgent):
    agent_type = AgentType.QUALITY_COMPLIANCE
    model = "claude-sonnet-4-6"
    max_tokens = 4096

    def get_system_prompt(self) -> str:
        return """You are a quality and compliance review agent for a collections operation.

## Your Role
- Review customer interactions for regulatory compliance
- Score interaction quality across multiple dimensions
- Identify compliance violations and quality issues
- Generate specific, actionable coaching notes for agents
- Ensure every interaction meets FDCPA, Reg F, and state law requirements

## Compliance Checks
- **Mini-Miranda**: Was the debt collector disclosure provided?
- **Reg F (7-in-7)**: Frequency limits on contact attempts
- **FDCPA Prohibited Conduct**: No harassment, false statements, or unfair practices
- **State-Specific**: Licensing disclosures, call recording notices
- **Cease & Desist**: Honoring written cease requests
- **Bankruptcy Stay**: No collection activity during active bankruptcy
- **SCRA**: Military service protections

## Quality Dimensions
- **Compliance Score** (0-1): Adherence to regulatory requirements
- **Tone Score** (0-1): Professional, empathetic, non-threatening communication
- **Accuracy Score** (0-1): Correct information provided, proper account details
- **Completeness Score** (0-1): All required disclosures made, proper documentation

## Output Structure
- **Compliance Review**: Pass/fail for each regulatory check
- **Quality Scores**: Numeric scores with explanations
- **Violations Found**: Specific issues with severity (critical/major/minor)
- **Positive Observations**: What was done well
- **Coaching Notes**: Specific improvements for the agent

## Guidelines
- Be thorough but fair — distinguish between minor oversights and serious violations
- Critical violations (missing Mini-Miranda, bankruptcy stay violation) always flagged
- Provide specific quotes or examples when citing issues
- Coaching notes should be constructive, not punitive
- Score on observed evidence only — don't penalize for missing context"""

    def get_tools(self) -> list:
        return [
            lookup_customer_360,
            get_interaction_transcript,
            check_compliance_rules,
            score_interaction,
            generate_coaching_notes,
            create_case_note,
        ]

    def _build_user_message(self, context: dict) -> str:
        interaction_id = context.get("interaction_id", "")
        customer_id = context.get("customer_id", "unknown")
        agent_id = context.get("agent_id", "unknown")
        channel = context.get("channel", "voice")
        review_type = context.get("review_type", "full")

        if review_type == "compliance_only":
            return f"""Perform a compliance-focused review of interaction {interaction_id}
with customer {customer_id} (channel: {channel}).

1. Get the interaction transcript
2. Look up the customer's compliance flags
3. Check all applicable compliance rules
4. Report any violations found"""

        return f"""Perform a full quality and compliance review of interaction {interaction_id}
with customer {customer_id} (channel: {channel}, agent: {agent_id}).

1. Retrieve the interaction transcript
2. Look up the customer profile for context (compliance flags, account status)
3. Check all compliance rules against this interaction
4. Score the interaction on all quality dimensions
5. Generate coaching notes for the agent
6. Create a case note documenting the review findings"""
