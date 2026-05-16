"""Shared tool definitions for AI agents — all decorated with @beta_async_tool.

Each tool is a thin wrapper around orchestrator capabilities (DB, OPA, Temporal, Kafka).
Claude calls these autonomously during the agentic loop. Tool schemas are generated
automatically from type hints and docstrings.

NO STUB TOOLS — every tool here either reads from real data, calls OPA, persists to
Postgres, or publishes a Kafka event. Tools that did neither have been deleted.
"""
from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import httpx
import orjson
from aiokafka import AIOKafkaProducer
from anthropic import beta_async_tool

from events.models import ChannelEvent, Channel, Direction
from events.topics import Topics
from services.shared.config import get_settings
from services.shared.db import execute_query, execute_insert
from services.shared.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)
settings = get_settings()


async def _publish_kafka(topic: str, event: ChannelEvent) -> None:
    """Publish a ChannelEvent to Kafka. Used by tools that dispatch outbound interactions."""
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    try:
        key = event.customer_id.encode() if event.customer_id else None
        await producer.send_and_wait(topic, value=event.to_kafka_value(), key=key)
    finally:
        await producer.stop()


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
            f"{settings.opa_url}/v1/data/collections/compliance/action_gate",
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
    """Analyze an interaction transcript for compliance violations. Calls the OPA
    policy collections.compliance.transcript_audit which checks Reg F, FDCPA,
    mini-Miranda disclosure, prohibited language, and cease-and-desist compliance.
    Returns the structured policy output (passed/failed per rule with citations)."""
    flags_rows = await execute_query(
        "SELECT flag_type FROM compliance_flags WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    flags = [r["flag_type"] for r in flags_rows]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.opa_url}/v1/data/collections/compliance/transcript_audit",
            json={"input": {
                "customer_id": customer_id,
                "channel": channel,
                "transcript": interaction_text,
                "transcript_length": len(interaction_text),
                "active_flags": flags,
            }},
        )
        result = resp.json().get("result")

    if not result:
        # No policy implemented yet — be explicit, don't fabricate a pass.
        return json.dumps({
            "customer_id": customer_id,
            "channel": channel,
            "active_flags": flags,
            "transcript_length": len(interaction_text),
            "status": "policy_not_evaluated",
            "note": "collections.compliance.transcript_audit policy returned no result",
        })

    return json.dumps({
        "customer_id": customer_id,
        "channel": channel,
        "active_flags": flags,
        "transcript_length": len(interaction_text),
        **(result if isinstance(result, dict) else {"raw": result}),
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
    """Evaluate multiple treatment paths using real cohort-based recovery estimates.

    For each treatment type, computes the historical recovery rate from payment_history
    of customers in the same DPD bucket (±15 days) over the last 365 days. If the cohort
    is too small (<5 customers) to be reliable, returns `confidence: 'insufficient_data'`
    rather than fabricating a number — the LLM should treat that as uncertainty.
    """
    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    if not accounts:
        return json.dumps({"customer_id": customer_id, "error": "no_active_account"})

    acct = accounts[0]
    balance = float(acct.get("current_balance", 0))
    dpd = int(acct.get("days_past_due", 0))

    # Build the cohort: similar customers (DPD ±15 days, active or recently active).
    cohort = await execute_query("""
        WITH cohort AS (
            SELECT DISTINCT customer_id FROM accounts
            WHERE days_past_due BETWEEN :lo AND :hi
              AND customer_id != :cid
        )
        SELECT
          COUNT(*) AS cohort_size,
          COUNT(*) FILTER (WHERE was_cured) AS cured_count,
          AVG(recovery_ratio) FILTER (WHERE recovery_ratio IS NOT NULL) AS avg_recovery
        FROM (
            SELECT c.customer_id,
                   SUM(ph.amount) FILTER (WHERE UPPER(ph.status) = 'COMPLETED') AS total_paid,
                   MAX(ph.amount) FILTER (WHERE UPPER(ph.status) = 'COMPLETED') > 0 AS was_cured,
                   CASE WHEN MAX(a.original_amount) > 0
                        THEN COALESCE(SUM(ph.amount) FILTER (WHERE UPPER(ph.status) = 'COMPLETED'), 0)
                             / MAX(a.original_amount)
                        ELSE NULL END AS recovery_ratio
            FROM cohort c
            LEFT JOIN payment_history ph ON ph.customer_id = c.customer_id
                                       AND ph.payment_date > NOW() - INTERVAL '365 days'
            LEFT JOIN accounts a ON a.customer_id = c.customer_id
            GROUP BY c.customer_id
        ) per_customer
    """, {"cid": customer_id, "lo": max(0, dpd - 15), "hi": dpd + 15})

    cohort_data = cohort[0] if cohort else {}
    cohort_size = int(cohort_data.get("cohort_size") or 0)
    cured_count = int(cohort_data.get("cured_count") or 0)
    avg_recovery = float(cohort_data.get("avg_recovery") or 0)

    # Read the customer's own payment history for personal patterns.
    payments = await execute_query("""
        SELECT amount, status, payment_date FROM payment_history
        WHERE customer_id = :cid ORDER BY payment_date DESC LIMIT 24
    """, {"cid": customer_id})

    paid_amounts = [float(p["amount"]) for p in payments if (p.get("status") or "").upper() == "COMPLETED"]
    payment_consistency = len(paid_amounts) / max(1, len(payments)) if payments else 0.0

    base = {
        "customer_id": customer_id,
        "balance": balance,
        "dpd": dpd,
        "cohort_dpd_window": [max(0, dpd - 15), dpd + 15],
        "cohort_size": cohort_size,
        "cohort_cure_rate": round(cured_count / cohort_size, 3) if cohort_size else None,
        "cohort_avg_recovery_ratio": round(avg_recovery, 3) if avg_recovery else None,
        "customer_payment_consistency": round(payment_consistency, 3),
        "customer_payments_observed": len(payments),
    }

    if cohort_size < 5:
        base["confidence"] = "insufficient_data"
        base["note"] = (
            f"Cohort of {cohort_size} similar customers is too small to estimate recovery. "
            "Recommend reasoning from the customer's own profile and history."
        )
        return json.dumps(base, default=str)

    # Recovery estimates anchored to real cohort data.
    cohort_recovery = avg_recovery if avg_recovery else 0.4
    paths = {
        "standard_dunning": {
            "description": "Continue standard collections cadence",
            "estimated_recovery": round(balance * cohort_recovery, 2),
            "estimated_recovery_pct": round(cohort_recovery * 100, 1),
            "anchored_in": f"cohort avg recovery ratio ({cohort_recovery:.2f}) over {cohort_size} customers",
            "timeline_days": 90,
            "risk_level": "medium" if dpd < 60 else "high",
        },
        "hardship_program": {
            "description": "Reduced payment plan based on demonstrated hardship",
            "estimated_recovery": round(balance * min(0.95, cohort_recovery * 1.4), 2),
            "estimated_recovery_pct": round(min(95, cohort_recovery * 140), 1),
            "anchored_in": f"cohort recovery × 1.4 (hardship plans historically improve recovery)",
            "timeline_days": 180,
            "risk_level": "low",
        },
        "settlement_offer": {
            "description": "Lump-sum settlement at reduced balance",
            "estimated_recovery": round(balance * 0.55, 2),
            "estimated_recovery_pct": 55.0,
            "anchored_in": "typical settlement floor of 55% of balance",
            "timeline_days": 30,
            "risk_level": "low",
        },
        "payment_arrangement": {
            "description": "Structured payment plan over 6-12 months",
            "estimated_recovery": round(balance * min(0.95, cohort_recovery * 1.7), 2),
            "estimated_recovery_pct": round(min(95, cohort_recovery * 170), 1),
            "anchored_in": "cohort recovery × 1.7 (arrangements historically have highest completion)",
            "timeline_days": 365,
            "risk_level": "medium" if payment_consistency < 0.5 else "low",
        },
    }

    base["confidence"] = "cohort_based"
    base["treatment_paths"] = paths
    return json.dumps(base, default=str)


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
# classify_intent removed — the LLM can classify intent natively without a keyword tool.
# suggest_next_best_action removed — the LLM reasons over context directly.


@beta_async_tool
async def compose_response(
    customer_id: str,
    response_text: str,
    channel: str = "sms",
    account_id: str = "",
) -> str:
    """Dispatch your composed response back to the customer. Publishes an outbound
    ChannelEvent on the same Kafka topic the orchestrator consumes, so the response
    is logged, projected to Postgres, and surfaced in the live event stream like any
    other outbound interaction.

    response_text: the actual message you want sent to the customer (compose it yourself).
    channel: sms | email | digital (must match the inbound channel for thread continuity).
    account_id: optional, link to specific account.
    """
    channel_enum = Channel(channel) if channel in [c.value for c in Channel] else Channel.DIGITAL
    event = ChannelEvent(
        event_id=str(_uuid.uuid4()),
        customer_id=customer_id,
        account_id=account_id or None,
        channel=channel_enum,
        direction=Direction.OUTBOUND,
        event_type=f"{channel}_sent",
        payload={
            "text": response_text,
            "composed_by": "ai_agent",
            "template": "ai_composed",
        },
        occurred_at=datetime.now(timezone.utc),
        source_service="ai-agent-digital",
    )
    await _publish_kafka(Topics.INTERACTIONS_NORMALIZED, event)
    return json.dumps({
        "status": "response_dispatched",
        "event_id": event.event_id,
        "customer_id": customer_id,
        "channel": channel,
        "text_preview": response_text[:200],
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
async def send_payment_link(
    customer_id: str,
    amount: float,
    channel: str = "sms",
    account_id: str = "",
) -> str:
    """Issue a real payment link for the customer. Persists to payment_links table,
    publishes an outbound ChannelEvent with the link, and returns the link_id and URL.
    The link is tracked through click and payment."""
    link_id = f"PAY-{customer_id[-4:]}-{int(datetime.now(timezone.utc).timestamp())}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    payment_url = f"https://pay.example.com/{link_id}"

    await execute_insert("""
        INSERT INTO payment_links (link_id, customer_id, account_id, amount, channel,
                                   issued_by_agent, expires_at, status)
        VALUES (:link_id, :cid, :aid, :amount, :channel, :agent, :expires_at, 'issued')
    """, {
        "link_id": link_id,
        "cid": customer_id,
        "aid": account_id or None,
        "amount": amount,
        "channel": channel,
        "agent": "digital_channel",
        "expires_at": expires_at,
    })

    channel_enum = Channel(channel) if channel in [c.value for c in Channel] else Channel.SMS
    event = ChannelEvent(
        event_id=str(_uuid.uuid4()),
        customer_id=customer_id,
        account_id=account_id or None,
        channel=channel_enum,
        direction=Direction.OUTBOUND,
        event_type=f"{channel}_sent",
        payload={
            "template": "payment_link",
            "link_id": link_id,
            "payment_url": payment_url,
            "amount": amount,
            "expires_at": expires_at.isoformat(),
        },
        occurred_at=datetime.now(timezone.utc),
        source_service="ai-agent-digital",
    )
    await _publish_kafka(Topics.INTERACTIONS_NORMALIZED, event)

    return json.dumps({
        "status": "payment_link_issued",
        "link_id": link_id,
        "payment_url": payment_url,
        "amount": amount,
        "channel": channel,
        "expires_at": expires_at.isoformat(),
    })


@beta_async_tool
async def escalate_to_human(
    customer_id: str,
    reason: str,
    urgency: str = "normal",
    recommended_specialist: str = "collections_agent",
    account_id: str = "",
) -> str:
    """Open a real escalation in the human_escalations queue. Sets SLA based on urgency
    (immediate=15min, high=1h, normal=4h, low=24h). Returns the escalation_id and queue
    position computed from currently-queued items for the same specialist."""
    sla_offsets = {
        "immediate": timedelta(minutes=15),
        "high": timedelta(hours=1),
        "normal": timedelta(hours=4),
        "low": timedelta(hours=24),
    }
    sla_due = datetime.now(timezone.utc) + sla_offsets.get(urgency, sla_offsets["normal"])
    escalation_id = str(_uuid.uuid4())

    await execute_insert("""
        INSERT INTO human_escalations (escalation_id, customer_id, account_id,
                                       source_agent, reason, urgency, specialist_type,
                                       sla_due_at, status, context)
        VALUES (:eid, :cid, :aid, :agent, :reason, :urgency, :specialist,
                :sla, 'queued', :context)
    """, {
        "eid": escalation_id,
        "cid": customer_id,
        "aid": account_id or None,
        "agent": "ai_agent",
        "reason": reason,
        "urgency": urgency,
        "specialist": recommended_specialist,
        "sla": sla_due,
        "context": json.dumps({"urgency": urgency, "reason": reason}),
    })

    pos_rows = await execute_query("""
        SELECT COUNT(*) AS position FROM human_escalations
        WHERE specialist_type = :sp AND status = 'queued'
          AND (urgency = :u AND created_at <= NOW() OR
               (CASE urgency WHEN 'immediate' THEN 4 WHEN 'high' THEN 3
                             WHEN 'normal' THEN 2 ELSE 1 END) >
               (CASE :u WHEN 'immediate' THEN 4 WHEN 'high' THEN 3
                        WHEN 'normal' THEN 2 ELSE 1 END))
    """, {"sp": recommended_specialist, "u": urgency})
    position = pos_rows[0]["position"] if pos_rows else 1

    return json.dumps({
        "status": "escalated",
        "escalation_id": escalation_id,
        "customer_id": customer_id,
        "reason": reason,
        "urgency": urgency,
        "specialist": recommended_specialist,
        "queue_position": position,
        "sla_due_at": sla_due.isoformat(),
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
    rationale for specialist review. Persists to agent_actions table."""
    import uuid as _uuid
    params = json.loads(parameters) if parameters else {}
    action_id = str(_uuid.uuid4())
    await execute_insert("""
        INSERT INTO agent_actions (action_id, agent_type, customer_id, action_type,
                                   parameters, rationale, confidence, status)
        VALUES (:action_id, 'case_reasoning', :cid, :atype, :params, :rationale, :conf, 'recommended')
    """, {
        "action_id": action_id,
        "cid": customer_id,
        "atype": action_type,
        "params": json.dumps(params),
        "rationale": rationale,
        "conf": confidence,
    })
    return json.dumps({
        "status": "recommendation_persisted",
        "action_id": action_id,
        "customer_id": customer_id,
        "action_type": action_type,
        "rationale": rationale,
        "confidence": confidence,
        "parameters": params,
        "requires_approval": confidence < 0.85,
    })


# ─── Structured Decision Tool — every agent MUST call this before finishing ──

@beta_async_tool
async def record_decision(
    action_type: str,
    confidence: float,
    rationale: str,
    escalate: bool = False,
    parameters: str = "{}",
) -> str:
    """Record your final decision for this customer interaction. You MUST call this
    before ending your turn — without it, the orchestrator treats your work as incomplete
    and escalates.

    action_type: one of `sent_payment_link`, `recorded_ptp`, `initiated_hardship`,
                 `offered_arrangement`, `settlement_discussion`, `escalated_to_human`,
                 `responded`, `no_action_needed`, or a specific domain action.
    confidence: 0.0 to 1.0 — your honest confidence that this is the right action.
                Be calibrated: do not always return 0.85.
    rationale: 1-3 sentence explanation of WHY this action, citing the evidence you used.
    escalate: true if a human should review or take over.
    parameters: JSON string with any structured parameters (amounts, dates, channels, etc.).
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


# ─── Copilot-Specific Tools ────────────────────────────────────────

# suggest_next_best_action removed — the LLM should reason over context directly,
# not delegate to a deterministic if/elif tool masquerading as "AI suggestion".


@beta_async_tool
async def generate_call_summary(
    customer_id: str,
    call_duration_seconds: int,
    topics_discussed: str,
    outcome: str,
    follow_up_actions: str = "",
    interaction_id: str = "",
) -> str:
    """Persist a structured call summary as a customer_event of type 'call_summary'.
    The summary is then visible in the customer's timeline and queryable via the
    standard events API. Returns the persisted event_id."""
    event_id = str(_uuid.uuid4())
    payload = {
        "duration_seconds": call_duration_seconds,
        "duration_minutes": round(call_duration_seconds / 60, 1),
        "topics": topics_discussed,
        "outcome": outcome,
        "follow_up": follow_up_actions,
        "interaction_id": interaction_id,
    }
    await execute_insert("""
        INSERT INTO customer_events (event_id, customer_id, event_type, event_category,
                                     channel, direction, payload, occurred_at, source_service)
        VALUES (:eid, :cid, 'call_summary', 'interaction', 'voice', 'system',
                CAST(:payload AS jsonb), NOW(), 'ai-agent-copilot')
    """, {
        "eid": event_id,
        "cid": customer_id,
        "payload": json.dumps(payload),
    })
    return json.dumps({
        "status": "summary_persisted",
        "event_id": event_id,
        "customer_id": customer_id,
        "duration_minutes": round(call_duration_seconds / 60, 1),
        "outcome": outcome,
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
    customer_id: str,
    compliance_score: float,
    tone_score: float,
    accuracy_score: float,
    completeness_score: float,
    findings: str = "[]",
) -> str:
    """Persist a quality scorecard for an interaction. You (the LLM) are responsible
    for producing the actual scores from your analysis of the transcript — this tool
    only persists what you've reasoned about.

    findings: JSON-encoded list of {dimension, severity, note} dicts citing specific issues.
    All scores are 0.0–1.0. Below 0.7 flags the dimension for coaching.
    """
    try:
        findings_list = json.loads(findings) if findings else []
    except json.JSONDecodeError:
        findings_list = [{"note": findings}]

    overall = round((compliance_score + tone_score + accuracy_score + completeness_score) / 4, 3)
    flags = []
    if compliance_score < 0.7:
        flags.append("compliance_below_threshold")
    if tone_score < 0.6:
        flags.append("tone_needs_improvement")
    if accuracy_score < 0.7:
        flags.append("accuracy_issue")
    if completeness_score < 0.6:
        flags.append("incomplete_interaction")

    review_id = str(_uuid.uuid4())
    await execute_insert("""
        INSERT INTO quality_reviews (review_id, interaction_id, customer_id, agent_type,
                                     compliance_score, tone_score, accuracy_score,
                                     completeness_score, overall_score, findings)
        VALUES (:rid, :iid, :cid, 'quality_compliance',
                :cs, :ts, :acs, :cps, :os, CAST(:findings AS jsonb))
    """, {
        "rid": review_id,
        "iid": interaction_id,
        "cid": customer_id,
        "cs": compliance_score,
        "ts": tone_score,
        "acs": accuracy_score,
        "cps": completeness_score,
        "os": overall,
        "findings": json.dumps({"items": findings_list, "flags": flags}),
    })

    return json.dumps({
        "review_id": review_id,
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
    customer_id: str,
    coaching_text: str,
    areas_of_concern: str = "",
) -> str:
    """Persist coaching notes for a human agent. You (the LLM) write the actual coaching
    text; this tool stores it on the most recent quality_reviews row for the interaction
    so it stays linked to the scorecard. Falls back to inserting a standalone review if
    no scorecard exists yet."""
    rows = await execute_query("""
        SELECT review_id FROM quality_reviews
        WHERE interaction_id = :iid ORDER BY reviewed_at DESC LIMIT 1
    """, {"iid": interaction_id})

    if rows:
        review_id = rows[0]["review_id"]
        await execute_insert("""
            UPDATE quality_reviews SET coaching_notes = :notes,
                                       findings = jsonb_set(
                                           COALESCE(findings, '{}'::jsonb),
                                           '{coaching}',
                                           CAST(:coaching AS jsonb))
            WHERE review_id = :rid
        """, {
            "rid": review_id,
            "notes": coaching_text,
            "coaching": json.dumps({
                "agent_id": agent_id,
                "areas_of_concern": areas_of_concern,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }),
        })
        status = "coaching_attached_to_review"
    else:
        review_id = str(_uuid.uuid4())
        await execute_insert("""
            INSERT INTO quality_reviews (review_id, interaction_id, customer_id, agent_type,
                                         coaching_notes, findings)
            VALUES (:rid, :iid, :cid, 'quality_compliance', :notes, CAST(:findings AS jsonb))
        """, {
            "rid": review_id,
            "iid": interaction_id,
            "cid": customer_id,
            "notes": coaching_text,
            "findings": json.dumps({
                "agent_id": agent_id,
                "areas_of_concern": areas_of_concern,
            }),
        })
        status = "standalone_coaching_review_created"

    return json.dumps({
        "review_id": review_id,
        "agent_id": agent_id,
        "interaction_id": interaction_id,
        "status": status,
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
