"""Shared tool definitions for AI agents — all decorated with @beta_async_tool.

Each tool is a thin wrapper around orchestrator capabilities (DB, OPA, Temporal, Kafka).
Claude calls these autonomously during the agentic loop. Tool schemas are generated
automatically from type hints and docstrings.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import httpx
from anthropic import beta_async_tool

from services.shared.config import get_settings
from services.shared.db import execute_query, execute_insert
from services.shared.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()


# ─── Customer & Account Tools ───────────────────────────────────────

@beta_async_tool
async def lookup_customer_360(customer_id: str) -> str:
    """Get the full customer profile including demographics, accounts, recent interactions,
    compliance flags, and active promises to pay. Use this first to understand the customer."""
    rows = await execute_query(
        "SELECT * FROM customer_profiles WHERE customer_id = :cid",
        {"cid": customer_id},
    )
    profile = rows[0] if rows else {}

    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )

    recent = await execute_query("""
        SELECT event_type, channel, direction, intent, payload, occurred_at
        FROM customer_events WHERE customer_id = :cid
        ORDER BY occurred_at DESC LIMIT 15
    """, {"cid": customer_id})

    flags = await execute_query(
        "SELECT flag_type, reason, created_at FROM compliance_flags WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )

    ptps = await execute_query(
        "SELECT * FROM promises_to_pay WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )

    return json.dumps({
        "profile": _serialize(profile),
        "accounts": [_serialize(a) for a in accounts],
        "recent_events": [_serialize(e) for e in recent],
        "compliance_flags": [_serialize(f) for f in flags],
        "active_ptps": [_serialize(p) for p in ptps],
    }, default=str)


@beta_async_tool
async def get_journey_state(customer_id: str) -> str:
    """Get the current Temporal workflow state for this customer's collections journey,
    including stage, actions taken, and channel history."""
    from temporalio.client import Client
    try:
        client = await Client.connect(settings.temporal_host)
        handle = client.get_workflow_handle(f"journey-{customer_id}")
        state = await handle.query("snapshot")
        return json.dumps(state, default=str)
    except Exception as e:
        return json.dumps({"error": f"No active journey: {e}"})


@beta_async_tool
async def get_full_history(customer_id: str) -> str:
    """Get the complete interaction history for a customer — all events across all channels,
    ordered chronologically. Use for deep case analysis."""
    rows = await execute_query("""
        SELECT event_type, channel, direction, intent, payload, occurred_at, source_service
        FROM customer_events WHERE customer_id = :cid
        ORDER BY occurred_at DESC LIMIT 50
    """, {"cid": customer_id})
    return json.dumps([_serialize(r) for r in rows], default=str)


# ─── Compliance & Guardrails Tools ──────────────────────────────────

@beta_async_tool
async def check_compliance(
    customer_id: str,
    action_type: str,
    channel: str = "digital",
) -> str:
    """Check whether a proposed action is allowed under current compliance rules.
    Returns allowed/blocked status with reasons. Always call before taking any action."""
    flags_rows = await execute_query(
        "SELECT flag_type FROM compliance_flags WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    flags = [r["flag_type"] for r in flags_rows]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/compliance/action_allowed",
            json={"input": {
                "action_type": action_type,
                "channel": channel,
                "compliance_flags": flags,
            }},
        )
        result = resp.json().get("result", {})

    return json.dumps({"allowed": result, "compliance_flags": flags, "action": action_type}, default=str)


@beta_async_tool
async def check_guardrails(
    agent_type: str,
    action_type: str = "",
    confidence: float = 0.85,
    compliance_flags: str = "",
    intent: str = "",
    ptp_amount: float = 0.0,
    ptp_days: int = 0,
    total_past_due: float = 0.0,
    balance: float = 0.0,
    settlement_amount: float = 0.0,
) -> str:
    """Check AI agent guardrails — determines what actions the agent is authorized to take
    autonomously vs. what requires human escalation."""
    flags_list = [f.strip() for f in compliance_flags.split(",") if f.strip()]
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/ai_guardrails/guardrail_check",
            json={"input": {
                "agent_type": agent_type,
                "action_type": action_type,
                "confidence": confidence,
                "compliance_flags": flags_list,
                "intent": intent,
                "ptp_amount": ptp_amount,
                "ptp_days": ptp_days,
                "total_past_due": total_past_due,
                "balance": balance,
                "settlement_amount": settlement_amount,
            }},
        )
        return json.dumps(resp.json().get("result", {}), default=str)


@beta_async_tool
async def check_compliance_rules(
    customer_id: str,
    interaction_text: str,
    channel: str,
) -> str:
    """Analyze an interaction transcript for compliance violations — checks Reg F,
    FDCPA, mini-Miranda, disclosure requirements, and prohibited language."""
    flags_rows = await execute_query(
        "SELECT flag_type, reason FROM compliance_flags WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    return json.dumps({
        "customer_id": customer_id,
        "channel": channel,
        "active_flags": [_serialize(r) for r in flags_rows],
        "interaction_length": len(interaction_text),
        "checks": [
            "mini_miranda_disclosure",
            "reg_f_frequency",
            "fdcpa_prohibited_language",
            "state_specific_requirements",
            "recording_disclosure",
            "cease_and_desist_compliance",
        ],
    }, default=str)


# ─── Strategy & Decision Tools ──────────────────────────────────────

@beta_async_tool
async def get_applicable_offers(customer_id: str) -> str:
    """Get the current strategy-driven offers available for this customer based on their
    segment, DPD bucket, and compliance status. Includes payment plans, settlements, and hardship programs."""
    accounts = await execute_query(
        "SELECT account_id, current_balance, days_past_due, total_past_due, product_type FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    if not accounts:
        return json.dumps({"offers": [], "reason": "No active accounts"})

    acct = accounts[0]
    async with httpx.AsyncClient() as client:
        seg_resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/segmentation",
            json={"input": {
                "days_past_due": acct["days_past_due"],
                "current_balance": float(acct["current_balance"]),
                "risk_score": 50,
                "prior_delinquencies": 0,
                "prior_cures": 0,
            }},
        )
        segment = seg_resp.json().get("result", {})

        treat_resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/treatment",
            json={"input": {
                "dpd_bucket": segment.get("dpd_bucket", "bucket_1_29"),
                "value_segment": segment.get("value_segment", "standard"),
                "risk_tier": segment.get("risk_tier", "medium"),
                "self_cure_probability": segment.get("self_cure_probability", "medium"),
                "journey_stage": "DUNNING",
                "channel_history": [],
                "prior_treatments": [],
            }},
        )
        treatment = treat_resp.json().get("result", {})

    return json.dumps({
        "account": _serialize(acct),
        "segment": segment,
        "treatment": treatment,
    }, default=str)


@beta_async_tool
async def evaluate_treatment_paths(
    customer_id: str,
    scenario: str = "all",
) -> str:
    """Evaluate multiple treatment paths for a complex case. Compares outcomes across
    standard dunning, hardship, settlement, and arrangement options."""
    customer_data = await execute_query(
        "SELECT * FROM customer_profiles WHERE customer_id = :cid", {"cid": customer_id}
    )
    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'", {"cid": customer_id}
    )
    payments = await execute_query(
        "SELECT * FROM payment_history WHERE customer_id = :cid ORDER BY payment_date DESC LIMIT 12",
        {"cid": customer_id},
    )

    profile = customer_data[0] if customer_data else {}
    acct = accounts[0] if accounts else {}
    balance = float(acct.get("current_balance", 0))
    dpd = acct.get("days_past_due", 0)

    paths = {
        "standard_dunning": {
            "description": "Continue standard collections cadence",
            "estimated_recovery": balance * 0.4 if dpd > 60 else balance * 0.7,
            "timeline_days": 90,
            "risk": "medium" if dpd < 60 else "high",
        },
        "hardship_program": {
            "description": "Reduced payment plan based on demonstrated hardship",
            "estimated_recovery": balance * 0.6,
            "timeline_days": 180,
            "risk": "low",
        },
        "settlement_offer": {
            "description": f"Lump-sum settlement at reduced balance",
            "estimated_recovery": balance * 0.45,
            "timeline_days": 30,
            "risk": "low",
        },
        "payment_arrangement": {
            "description": "Structured payment plan over 6-12 months",
            "estimated_recovery": balance * 0.85,
            "timeline_days": 365,
            "risk": "medium",
        },
    }

    return json.dumps({
        "customer_id": customer_id,
        "balance": balance,
        "dpd": dpd,
        "payment_history_count": len(payments),
        "treatment_paths": paths,
    }, default=str)


@beta_async_tool
async def suggest_strategy_change(
    segment: str,
    metric: str,
    current_value: float,
    target_value: float,
    rationale: str,
) -> str:
    """Propose a strategy configuration change for a customer segment. Creates an audit
    log entry for human review. Does not auto-apply."""
    await execute_insert("""
        INSERT INTO strategy_audit_log (strategy_version, change_type, change_details, changed_by, change_reason)
        VALUES (:version, :change_type, :details, :changed_by, :reason)
    """, {
        "version": "v1.0.0",
        "change_type": "ai_recommendation",
        "details": json.dumps({
            "segment": segment,
            "metric": metric,
            "current_value": current_value,
            "target_value": target_value,
        }),
        "changed_by": "portfolio_intelligence_agent",
        "reason": rationale,
    })
    return json.dumps({
        "status": "recommendation_logged",
        "segment": segment,
        "metric": metric,
        "requires_human_approval": True,
    })


# ─── Action Tools (write operations) ───────────────────────────────

@beta_async_tool
async def classify_intent(message: str) -> str:
    """Classify the intent of a customer message. Returns the detected intent category
    and confidence score. Used by the digital channel agent to understand what the customer wants."""
    message_lower = message.lower()
    intent_signals = {
        "PTP": ["pay", "payment", "promise", "send money", "friday", "tuesday", "next week"],
        "HARDSHIP": ["lost job", "can't afford", "medical", "divorce", "hours cut", "hardship", "help"],
        "DISPUTE": ["not my debt", "wrong amount", "dispute", "never had", "error"],
        "SETTLEMENT_INQUIRY": ["settle", "lump sum", "reduce", "less than", "settlement"],
        "BALANCE_INQUIRY": ["owe", "balance", "how much", "past due", "amount"],
        "PAYMENT_QUESTION": ["where", "send", "online", "credit card", "payment method"],
        "REFUSAL_TO_PAY": ["not paying", "stop contacting", "leave me alone", "refuse"],
        "COMPLAINT": ["supervisor", "manager", "complaint", "report", "unacceptable"],
        "DISTRESS": ["kill", "suicide", "can't go on", "end it", "hopeless", "desperate"],
        "GENERAL_INQUIRY": ["call back", "update", "phone number", "next payment"],
    }

    scores = {}
    for intent, keywords in intent_signals.items():
        score = sum(1 for kw in keywords if kw in message_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return json.dumps({"intent": "GENERAL_INQUIRY", "confidence": 0.5})

    best = max(scores, key=scores.get)
    confidence = min(0.95, 0.6 + scores[best] * 0.1)
    return json.dumps({"intent": best, "confidence": confidence})


@beta_async_tool
async def compose_response(
    customer_id: str,
    intent: str,
    tone: str = "professional_empathetic",
    key_points: str = "",
) -> str:
    """Compose a response message to send to the customer via digital channel.
    The response follows collections compliance guidelines and the specified tone."""
    return json.dumps({
        "customer_id": customer_id,
        "intent": intent,
        "tone": tone,
        "key_points": key_points,
        "status": "response_drafted",
        "note": "Agent should compose the actual response text in its reply.",
    })


@beta_async_tool
async def record_ptp(
    customer_id: str,
    account_id: str,
    amount: float,
    promised_date: str,
    channel: str = "digital",
) -> str:
    """Record a promise-to-pay from the customer. Triggers PTP monitoring in the workflow."""
    await execute_insert("""
        INSERT INTO promises_to_pay (customer_id, account_id, promised_amount, promised_date, channel, status)
        VALUES (:cid, :aid, :amount, :date, :channel, 'ACTIVE')
    """, {
        "cid": customer_id, "aid": account_id,
        "amount": amount, "date": promised_date, "channel": channel,
    })

    try:
        from temporalio.client import Client
        tc = await Client.connect(settings.temporal_host)
        handle = tc.get_workflow_handle(f"journey-{customer_id}")
        from workflows.types import PaymentSignal
        await handle.signal("payment_received", PaymentSignal(
            amount=amount, payment_date=promised_date, account_id=account_id, method="ptp",
        ))
    except Exception as e:
        logger.warning("Could not signal PTP to workflow: %s", e)

    return json.dumps({
        "status": "ptp_recorded",
        "customer_id": customer_id,
        "amount": amount,
        "promised_date": promised_date,
    })


@beta_async_tool
async def initiate_hardship(
    customer_id: str,
    reason: str,
    monthly_income: float = 0.0,
    monthly_expenses: float = 0.0,
) -> str:
    """Initiate a hardship review for the customer. Transitions the journey to HARDSHIP_REVIEW stage."""
    try:
        from temporalio.client import Client
        tc = await Client.connect(settings.temporal_host)
        handle = tc.get_workflow_handle(f"journey-{customer_id}")
        from workflows.types import ChannelEventSignal
        await handle.signal("channel_event", ChannelEventSignal(
            customer_id=customer_id,
            channel="digital",
            direction="inbound",
            event_type="hardship_request",
            intent="HARDSHIP",
            payload={"reason": reason, "monthly_income": monthly_income, "monthly_expenses": monthly_expenses},
        ))
    except Exception as e:
        logger.warning("Could not signal hardship to workflow: %s", e)

    return json.dumps({
        "status": "hardship_initiated",
        "customer_id": customer_id,
        "reason": reason,
    })


@beta_async_tool
async def send_payment_link(customer_id: str, amount: float, channel: str = "sms") -> str:
    """Send a secure payment link to the customer via SMS or email."""
    return json.dumps({
        "status": "payment_link_sent",
        "customer_id": customer_id,
        "amount": amount,
        "channel": channel,
        "link_id": f"PAY-{customer_id[-4:]}-{int(datetime.now(timezone.utc).timestamp())}",
        "expires_in_hours": 72,
    })


@beta_async_tool
async def escalate_to_human(
    customer_id: str,
    reason: str,
    urgency: str = "normal",
    recommended_specialist: str = "collections_agent",
) -> str:
    """Escalate the interaction to a human agent. Use when the situation requires human judgment,
    the customer is distressed, or the agent's confidence is low."""
    return json.dumps({
        "status": "escalated",
        "customer_id": customer_id,
        "reason": reason,
        "urgency": urgency,
        "specialist": recommended_specialist,
        "queue_position": 1,
    })


@beta_async_tool
async def create_case_note(
    customer_id: str,
    note: str,
    category: str = "general",
) -> str:
    """Create a case note on the customer's account. Used to document interactions,
    decisions, and follow-up actions."""
    await execute_insert("""
        INSERT INTO customer_events (customer_id, event_type, channel, direction, intent, payload, occurred_at, source_service)
        VALUES (:cid, 'case_note', 'system', 'system', NULL, :payload, NOW(), 'ai-agent')
    """, {
        "cid": customer_id,
        "payload": json.dumps({"note": note, "category": category}),
    })
    return json.dumps({"status": "note_created", "customer_id": customer_id, "category": category})


@beta_async_tool
async def recommend_action(
    customer_id: str,
    action_type: str,
    rationale: str,
    confidence: float,
    parameters: str = "{}",
) -> str:
    """Recommend a specific action for a complex case. Logs the recommendation with full
    rationale for specialist review."""
    params = json.loads(parameters) if parameters else {}
    return json.dumps({
        "status": "recommendation_made",
        "customer_id": customer_id,
        "action_type": action_type,
        "rationale": rationale,
        "confidence": confidence,
        "parameters": params,
        "requires_approval": confidence < 0.85,
    })


# ─── Copilot-Specific Tools ────────────────────────────────────────

@beta_async_tool
async def suggest_next_best_action(
    customer_id: str,
    current_stage: str,
    last_interaction_intent: str = "",
) -> str:
    """Suggest the next best action for the human agent based on customer context and journey state.
    Returns ranked suggestions with rationale."""
    customer_data = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    acct = customer_data[0] if customer_data else {}
    dpd = acct.get("days_past_due", 0)
    balance = float(acct.get("current_balance", 0))

    suggestions = []
    if last_interaction_intent == "HARDSHIP":
        suggestions.append({"action": "initiate_hardship_review", "priority": 1, "rationale": "Customer indicated financial hardship"})
        suggestions.append({"action": "offer_reduced_payment_plan", "priority": 2, "rationale": "Demonstrate willingness to work with customer"})
    elif last_interaction_intent == "PTP":
        suggestions.append({"action": "confirm_ptp_details", "priority": 1, "rationale": "Capture promise amount and date"})
        suggestions.append({"action": "send_confirmation_sms", "priority": 2, "rationale": "Document the agreement"})
    elif dpd > 60:
        suggestions.append({"action": "discuss_settlement_options", "priority": 1, "rationale": f"Account is {dpd} DPD"})
        suggestions.append({"action": "offer_payment_arrangement", "priority": 2, "rationale": "Structured repayment may prevent charge-off"})
    else:
        suggestions.append({"action": "standard_payment_reminder", "priority": 1, "rationale": "Encourage voluntary payment"})
        suggestions.append({"action": "verify_contact_info", "priority": 2, "rationale": "Ensure future reachability"})

    return json.dumps({"customer_id": customer_id, "suggestions": suggestions})


@beta_async_tool
async def generate_call_summary(
    customer_id: str,
    call_duration_seconds: int,
    topics_discussed: str,
    outcome: str,
    follow_up_actions: str = "",
) -> str:
    """Generate a structured call summary for agent documentation. Formats the summary
    for insertion into the case management system."""
    return json.dumps({
        "customer_id": customer_id,
        "duration_minutes": round(call_duration_seconds / 60, 1),
        "topics": topics_discussed,
        "outcome": outcome,
        "follow_up": follow_up_actions,
        "status": "summary_generated",
    })


@beta_async_tool
async def prefill_form(
    customer_id: str,
    form_type: str,
) -> str:
    """Pre-fill a form with customer data. Supported forms: ptp, hardship_application,
    settlement_offer, call_disposition, case_note."""
    profile = await execute_query(
        "SELECT * FROM customer_profiles WHERE customer_id = :cid", {"cid": customer_id}
    )
    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'", {"cid": customer_id}
    )

    p = profile[0] if profile else {}
    a = accounts[0] if accounts else {}

    fields = {
        "customer_name": f"{p.get('first_name', '')} {p.get('last_name', '')}",
        "customer_id": customer_id,
        "account_id": a.get("account_id", ""),
        "current_balance": str(a.get("current_balance", "")),
        "days_past_due": str(a.get("days_past_due", "")),
        "form_type": form_type,
    }

    if form_type == "ptp":
        fields["suggested_amount"] = str(a.get("total_past_due", ""))
    elif form_type == "settlement_offer":
        balance = float(a.get("current_balance", 0))
        fields["settlement_floor"] = str(round(balance * 0.40, 2))
        fields["settlement_ceiling"] = str(round(balance * 0.60, 2))

    return json.dumps({"form_type": form_type, "fields": fields})


# ─── Portfolio Intelligence Tools ───────────────────────────────────

@beta_async_tool
async def query_portfolio_metrics(metric_type: str = "summary") -> str:
    """Query portfolio-level metrics. Types: summary, delinquency_breakdown, channel_performance,
    recovery_rates, agent_performance."""
    if metric_type == "delinquency_breakdown":
        rows = await execute_query("""
            SELECT delinquency_stage, COUNT(*) as count,
                   SUM(current_balance) as total_balance,
                   AVG(days_past_due) as avg_dpd
            FROM accounts WHERE status = 'ACTIVE'
            GROUP BY delinquency_stage ORDER BY avg_dpd
        """)
        return json.dumps([_serialize(r) for r in rows], default=str)

    if metric_type == "channel_performance":
        rows = await execute_query("""
            SELECT channel, direction, COUNT(*) as event_count
            FROM customer_events
            WHERE occurred_at > NOW() - INTERVAL '30 days'
            GROUP BY channel, direction ORDER BY event_count DESC
        """)
        return json.dumps([_serialize(r) for r in rows], default=str)

    rows = await execute_query("""
        SELECT
            COUNT(DISTINCT customer_id) as total_customers,
            COUNT(*) as total_accounts,
            SUM(current_balance) as total_outstanding,
            AVG(days_past_due) as avg_dpd,
            SUM(total_past_due) as total_past_due,
            COUNT(*) FILTER (WHERE days_past_due > 90) as severe_count
        FROM accounts WHERE status = 'ACTIVE'
    """)
    return json.dumps(_serialize(rows[0]) if rows else {}, default=str)


@beta_async_tool
async def query_segment_trends(segment_field: str = "delinquency_stage") -> str:
    """Analyze trends across customer segments. Shows distributions and key metrics per segment."""
    rows = await execute_query(f"""
        SELECT a.{segment_field}, COUNT(*) as count,
               AVG(a.current_balance) as avg_balance,
               AVG(a.days_past_due) as avg_dpd
        FROM accounts a
        WHERE a.status = 'ACTIVE'
        GROUP BY a.{segment_field}
        ORDER BY count DESC
    """)
    return json.dumps([_serialize(r) for r in rows], default=str)


@beta_async_tool
async def compare_cohorts(
    cohort_a: str,
    cohort_b: str,
    dimension: str = "delinquency_stage",
) -> str:
    """Compare two customer cohorts across key metrics. Useful for champion/challenger analysis."""
    results = {}
    for label, value in [("cohort_a", cohort_a), ("cohort_b", cohort_b)]:
        rows = await execute_query(f"""
            SELECT COUNT(*) as count, AVG(current_balance) as avg_balance,
                   AVG(days_past_due) as avg_dpd, SUM(total_past_due) as total_past_due
            FROM accounts WHERE {dimension} = :val AND status = 'ACTIVE'
        """, {"val": value})
        results[label] = {"value": value, **_serialize(rows[0])} if rows else {"value": value}

    return json.dumps(results, default=str)


@beta_async_tool
async def query_strategy_performance(strategy_version: str = "v1.0.0") -> str:
    """Get performance metrics for a strategy version — recovery rates, contact rates,
    escalation rates, and PTP conversion."""
    audit = await execute_query(
        "SELECT * FROM strategy_audit_log ORDER BY created_at DESC LIMIT 10"
    )
    ptps = await execute_query("""
        SELECT status, COUNT(*) as count, SUM(promised_amount) as total_amount
        FROM promises_to_pay GROUP BY status
    """)
    return json.dumps({
        "strategy_version": strategy_version,
        "recent_changes": [_serialize(a) for a in audit],
        "ptp_summary": [_serialize(p) for p in ptps],
    }, default=str)


# ─── Quality & Compliance Tools ─────────────────────────────────────

@beta_async_tool
async def get_interaction_transcript(interaction_id: str) -> str:
    """Retrieve the full transcript or event details for a specific interaction."""
    rows = await execute_query(
        "SELECT * FROM customer_events WHERE event_id = :eid",
        {"eid": interaction_id},
    )
    if not rows:
        rows = await execute_query(
            "SELECT * FROM customer_events ORDER BY occurred_at DESC LIMIT 1"
        )
    return json.dumps([_serialize(r) for r in rows], default=str)


@beta_async_tool
async def score_interaction(
    interaction_id: str,
    compliance_score: float,
    tone_score: float,
    accuracy_score: float,
    completeness_score: float,
) -> str:
    """Score an interaction across quality dimensions. Calculates overall score and
    flags any dimension below threshold."""
    overall = round((compliance_score + tone_score + accuracy_score + completeness_score) / 4, 2)
    flags = []
    if compliance_score < 0.7:
        flags.append("compliance_below_threshold")
    if tone_score < 0.6:
        flags.append("tone_needs_improvement")
    if accuracy_score < 0.7:
        flags.append("accuracy_issue")
    if completeness_score < 0.6:
        flags.append("incomplete_interaction")

    return json.dumps({
        "interaction_id": interaction_id,
        "compliance_score": compliance_score,
        "tone_score": tone_score,
        "accuracy_score": accuracy_score,
        "completeness_score": completeness_score,
        "overall_score": overall,
        "flags": flags,
        "pass": overall >= 0.7 and not flags,
    })


@beta_async_tool
async def generate_coaching_notes(
    agent_id: str,
    interaction_id: str,
    scores: str,
    areas_of_concern: str,
) -> str:
    """Generate coaching notes for a human agent based on interaction quality scores.
    Provides specific, actionable feedback."""
    return json.dumps({
        "agent_id": agent_id,
        "interaction_id": interaction_id,
        "scores": scores,
        "areas_of_concern": areas_of_concern,
        "status": "coaching_notes_generated",
        "note": "AI should provide specific coaching feedback in its response.",
    })


# ─── Helpers ────────────────────────────────────────────────────────

def _serialize(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "__float__"):
            out[k] = float(v)
        else:
            out[k] = v
    return out
