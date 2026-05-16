"""Customer Story endpoints — narrative-first view of a single customer journey.

Powers the rewritten /customer/:id page. Combines:
  - LLM-generated narrative summary of what's happened
  - Enriched timeline (every channel event + decision + compliance check + AI action)
  - Per-decision rationale (the OPA inputs + outputs that produced each strategy call)
  - Agent receipts (every agent_actions row tied to this customer)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from anthropic import AsyncAnthropic
from fastapi import APIRouter, HTTPException

from services.shared.db import execute_query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/customers/{customer_id}/timeline")
async def enriched_timeline(customer_id: str, limit: int = 200):
    """Every event in the customer's history, enriched with the joined agent_action,
    strategy decision, or escalation that the event triggered (when applicable)."""
    events = await execute_query("""
        SELECT event_id, customer_id, event_type, event_category, channel, direction,
               intent, payload, source_service, correlation_id,
               workflow_id, occurred_at, received_at
        FROM customer_events
        WHERE customer_id = :cid
        ORDER BY occurred_at DESC
        LIMIT :limit
    """, {"cid": customer_id, "limit": limit})

    correlation_ids = {str(e["correlation_id"]) for e in events if e.get("correlation_id")}

    actions_by_trace: dict[str, list[dict]] = {}
    if correlation_ids:
        # Pull all of this customer's recent agent_actions; we filter to the relevant
        # trace_ids in Python (SQLAlchemy text() doesn't accept list params without
        # extra bindparam wiring, and customer cardinality keeps this cheap).
        all_actions = await execute_query("""
            SELECT trace_id, action_id, agent_type, action_type, parameters,
                   rationale, confidence, status, created_at
            FROM agent_actions
            WHERE customer_id = :cid
              AND created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
        """, {"cid": customer_id})
        for a in all_actions:
            tid = str(a.get("trace_id") or "")
            if tid in correlation_ids:
                actions_by_trace.setdefault(tid, []).append(a)

    enriched = []
    for e in events:
        cid_key = str(e.get("correlation_id") or "")
        enriched.append({**e, "linked_actions": actions_by_trace.get(cid_key, [])})

    return {"timeline": enriched, "count": len(enriched)}


@router.get("/customers/{customer_id}/agent-actions")
async def customer_agent_actions(customer_id: str, limit: int = 30):
    rows = await execute_query("""
        SELECT action_id, agent_type, action_type, parameters, rationale, confidence,
               status, trace_id, dispatched_at, created_at
        FROM agent_actions
        WHERE customer_id = :cid
        ORDER BY created_at DESC
        LIMIT :limit
    """, {"cid": customer_id, "limit": limit})
    return {"actions": rows}


@router.get("/customers/{customer_id}/decisions")
async def customer_decisions(customer_id: str, limit: int = 30):
    rows = await execute_query("""
        SELECT audit_id, strategy_version, policy_name,
               input_context, decision, evaluated_at
        FROM strategy_audit_log
        WHERE customer_id = :cid
        ORDER BY evaluated_at DESC NULLS LAST
        LIMIT :limit
    """, {"cid": customer_id, "limit": limit})
    return {"decisions": rows}


@router.get("/customers/{customer_id}/escalations")
async def customer_escalations(customer_id: str):
    rows = await execute_query("""
        SELECT escalation_id, reason, urgency, specialist_type, status,
               sla_due_at, created_at, source_agent, assigned_to, resolved_at
        FROM human_escalations
        WHERE customer_id = :cid
        ORDER BY created_at DESC
    """, {"cid": customer_id})
    return {"escalations": rows}


@router.get("/customers/{customer_id}/narrative")
async def customer_narrative(customer_id: str):
    """LLM-generated narrative summary of the customer's journey. Real Claude call —
    no canned text. Reads profile + account + recent events + recent decisions and
    asks Claude to tell the story in 3-5 sentences a CTO could read on a dashboard.
    """
    profile = await execute_query(
        "SELECT * FROM customer_profiles WHERE customer_id = :cid", {"cid": customer_id}
    )
    if not profile:
        raise HTTPException(404, "Customer not found")
    p = profile[0]

    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE' ORDER BY days_past_due DESC LIMIT 1",
        {"cid": customer_id},
    )
    acct = accounts[0] if accounts else {}

    events = await execute_query("""
        SELECT event_type, event_category, channel, direction, intent,
               occurred_at, payload->>'rule_name' AS rule_name,
               payload->>'action_blocked' AS action_blocked,
               payload->>'to_stage' AS to_stage
        FROM customer_events
        WHERE customer_id = :cid
        ORDER BY occurred_at DESC
        LIMIT 40
    """, {"cid": customer_id})

    actions = await execute_query("""
        SELECT agent_type, action_type, rationale, confidence, status, created_at
        FROM agent_actions
        WHERE customer_id = :cid
        ORDER BY created_at DESC
        LIMIT 10
    """, {"cid": customer_id})

    flags = await execute_query("""
        SELECT flag_type, reason FROM compliance_flags
        WHERE customer_id = :cid AND status = 'ACTIVE'
    """, {"cid": customer_id})

    context = {
        "customer": {
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}",
            "customer_id": customer_id,
            "risk_score": p.get("risk_score"),
            "preferred_channel": p.get("preferred_channel"),
            "tenure_years": _years_since(p.get("relationship_start")),
        },
        "account": {
            "product": acct.get("product_type"),
            "balance": float(acct.get("current_balance") or 0),
            "past_due": float(acct.get("total_past_due") or 0),
            "dpd": acct.get("days_past_due"),
            "delinquency_stage": acct.get("delinquency_stage"),
        },
        "active_compliance_flags": [f["flag_type"] for f in flags],
        "recent_events": [
            {k: v for k, v in e.items() if v is not None}
            for e in events[:30]
        ],
        "recent_agent_actions": actions,
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # No API key — return a structured fallback, not fake prose
        return {
            "narrative": None,
            "fallback": _structured_fallback(context),
            "model": None,
            "note": "ANTHROPIC_API_KEY not set — returning structured summary instead",
        }

    client = AsyncAnthropic(api_key=api_key)
    system = (
        "You are summarizing a customer's collections journey for a senior collections manager. "
        "Write 3-5 sentences in plain English that tell the story: where the customer is now, "
        "how they got there, what the system has done, and what's notable (escalations, blocks, "
        "successful PTPs). Cite specific numbers and dates. Do NOT speculate beyond the data. "
        "Do not include preamble like 'Here is the summary' — just write the narrative."
    )
    user_prompt = f"Customer context:\n```json\n{json.dumps(context, default=str, indent=2)}\n```"

    try:
        msg = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=600,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "\n".join(b.text for b in msg.content if b.type == "text").strip()
        return {
            "narrative": text,
            "model": msg.model,
            "tokens": {
                "input": msg.usage.input_tokens,
                "output": msg.usage.output_tokens,
            },
        }
    except Exception as e:
        logger.exception("Narrative generation failed")
        return {
            "narrative": None,
            "fallback": _structured_fallback(context),
            "error": str(e),
        }


def _years_since(date_str: str | None) -> float | None:
    if not date_str:
        return None
    try:
        start = datetime.fromisoformat(str(date_str))
        return round((datetime.utcnow() - start.replace(tzinfo=None)).days / 365.25, 1)
    except Exception:
        return None


def _structured_fallback(ctx: dict[str, Any]) -> str:
    """When Claude isn't available, return a structured fact summary — not made-up prose."""
    c = ctx.get("customer", {})
    a = ctx.get("account", {})
    flags = ctx.get("active_compliance_flags") or []
    events = ctx.get("recent_events") or []
    actions = ctx.get("recent_agent_actions") or []
    parts = []
    parts.append(
        f"{c.get('name', 'Customer')} ({c.get('customer_id')}) is {a.get('dpd', 0)} days past due "
        f"on a {a.get('product') or 'unspecified product'} with ${a.get('past_due', 0):,.0f} past due "
        f"out of ${a.get('balance', 0):,.0f} balance."
    )
    if flags:
        parts.append(f"Active compliance flags: {', '.join(flags)}.")
    if events:
        recent_intents = [e.get("intent") for e in events[:10] if e.get("intent")]
        if recent_intents:
            parts.append(f"Recent customer signals: {', '.join(set(recent_intents))}.")
    if actions:
        last_action = actions[0]
        parts.append(
            f"Most recent AI action: {last_action.get('action_type')} "
            f"({(float(last_action.get('confidence') or 0) * 100):.0f}% confidence)."
        )
    return " ".join(parts)
