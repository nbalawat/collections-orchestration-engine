"""Digital Channel Agent — autonomous customer-facing agent for SMS/chat/web.

Handles inbound customer messages across digital channels. Classifies intent,
checks compliance, looks up customer context, and responds autonomously within
OPA-defined guardrails. Escalates to human agents when required.
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
    classify_intent,
    compose_response,
    record_ptp,
    initiate_hardship,
    send_payment_link,
    escalate_to_human,
    create_case_note,
)


class DigitalChannelAgent(CollectionsAgent):
    agent_type = AgentType.DIGITAL_CHANNEL
    model = "claude-sonnet-4-6"
    max_tokens = 4096

    def get_system_prompt(self) -> str:
        return """You are a collections agent handling digital customer interactions (SMS, chat, web portal).
You work for a financial institution's collections department.

## Your Role
- Respond to inbound customer messages professionally and empathetically
- Identify the customer's intent and address their needs
- Follow all compliance rules — ALWAYS check compliance before taking any action
- Stay within your authorized autonomy — check guardrails before acting
- Escalate immediately if the customer shows distress, makes threats, or you're unsure

## Workflow
1. First, look up the customer's profile using lookup_customer_360
2. Classify the customer's message intent using classify_intent
3. Check your guardrails to understand what you can do autonomously
4. Check compliance before any action
5. Take the appropriate action (respond, capture PTP, offer payment link, initiate hardship, etc.)
6. Create a case note documenting what happened

## Guardrails
- You CAN: respond to inquiries, capture promises to pay, send payment links, initiate hardship review, offer standard arrangements
- You MUST ESCALATE: threats of legal action, customer distress/suicidal ideation, complaints requesting supervisor, low confidence situations
- You CANNOT: offer settlements above 50% of balance, modify account terms, waive fees, make promises about credit reporting

## Tone
- Professional but empathetic
- Acknowledge the customer's situation
- Be clear about next steps
- Never be threatening or aggressive
- Use plain language, not legal jargon"""

    def get_tools(self) -> list:
        return [
            lookup_customer_360,
            get_journey_state,
            get_applicable_offers,
            check_compliance,
            check_guardrails,
            classify_intent,
            compose_response,
            record_ptp,
            initiate_hardship,
            send_payment_link,
            escalate_to_human,
            create_case_note,
        ]

    def _build_user_message(self, context: dict) -> str:
        customer_id = context.get("customer_id", "unknown")
        message = context.get("message", "")
        channel = context.get("channel", "sms")

        return f"""New inbound message from customer {customer_id} via {channel}:

"{message}"

Handle this interaction. Look up the customer, understand their intent, check compliance and guardrails, then respond appropriately. Document your actions with a case note."""
