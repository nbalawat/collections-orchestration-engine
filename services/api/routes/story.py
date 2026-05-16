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
        "Write a concise markdown brief with the following structure:\n\n"
        "**Where they stand** — one sentence on current state (DPD, balance, stage, risk).\n\n"
        "**How they got here** — 2-3 sentences on the journey: starting state, key interactions,"
        " what the system did, what the customer signaled.\n\n"
        "**Notable** — bullet list of anything that deserves attention: escalations, compliance"
        " blocks, AI agent actions taken, PTPs made/broken, errors the agents hit.\n\n"
        "**Next** — one sentence on what to watch for or do next.\n\n"
        "Cite specific numbers and dates. Use `inline code` for IDs and amounts. Do NOT speculate"
        " beyond the data. Do not include preamble like 'Here is the summary'. Output ONLY the"
        " markdown — no surrounding code fence."
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


WINDOW_INTERVALS = {
    "24h": "24 hours",
    "7d": "7 days",
    "30d": "30 days",
    "90d": "90 days",
    "all": "100 years",
}


@router.get("/customers/{customer_id}/activity-digest")
async def customer_activity_digest(customer_id: str, window: str = "7d"):
    """Multi-dimensional AI-generated summary of a customer's activity over a time
    window. Designed for senior operators / compliance / risk who don't want to
    scroll through event logs — they want a structured digest that calls out what
    happened across every key dimension and what needs attention.

    window: 24h | 7d | 30d | 90d | all
    """
    interval = WINDOW_INTERVALS.get(window, WINDOW_INTERVALS["7d"])

    profile = await execute_query(
        "SELECT * FROM customer_profiles WHERE customer_id = :cid", {"cid": customer_id}
    )
    if not profile:
        raise HTTPException(404, "Customer not found")
    p = profile[0]

    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE' ORDER BY days_past_due DESC",
        {"cid": customer_id},
    )

    # Customer-side activity by channel + intent
    channel_summary = await execute_query(f"""
        SELECT channel, direction, intent,
               COUNT(*) AS n,
               MIN(occurred_at) AS first_at,
               MAX(occurred_at) AS last_at
        FROM customer_events
        WHERE customer_id = :cid
          AND occurred_at > NOW() - INTERVAL '{interval}'
          AND event_category IN ('channel', 'interaction')
        GROUP BY channel, direction, intent
        ORDER BY n DESC
    """, {"cid": customer_id})

    # Stage transitions in window
    stage_transitions = await execute_query(f"""
        SELECT event_type, occurred_at, payload->>'reason' AS reason,
               payload->>'triggered_by' AS triggered_by
        FROM customer_events
        WHERE customer_id = :cid
          AND event_type LIKE 'stage_change:%'
          AND occurred_at > NOW() - INTERVAL '{interval}'
        ORDER BY occurred_at ASC
    """, {"cid": customer_id})

    # AI agent decisions in window
    agent_actions = await execute_query(f"""
        SELECT agent_type, action_type, confidence, status, rationale, created_at
        FROM agent_actions
        WHERE customer_id = :cid
          AND created_at > NOW() - INTERVAL '{interval}'
        ORDER BY created_at DESC
        LIMIT 30
    """, {"cid": customer_id})

    # Strategy evaluations in window
    decisions = await execute_query(f"""
        SELECT strategy_version, policy_name,
               decision->'segment'->>'value_segment' AS value_segment,
               decision->'segment'->>'risk_tier' AS risk_tier,
               decision->'segment'->>'dpd_bucket' AS dpd_bucket,
               decision->'treatment'->>'action' AS action,
               decision->'compliance'->>'can_contact' AS can_contact,
               evaluated_at
        FROM strategy_audit_log
        WHERE customer_id = :cid
          AND evaluated_at > NOW() - INTERVAL '{interval}'
        ORDER BY evaluated_at DESC
        LIMIT 30
    """, {"cid": customer_id})

    # Compliance gate results in window (pass + fail both)
    compliance_summary = await execute_query(f"""
        SELECT (payload->>'passed')::boolean AS passed,
               payload->>'reason' AS reason,
               payload->>'action_blocked' AS action_blocked,
               COUNT(*) AS n,
               MAX(occurred_at) AS last_at
        FROM customer_events
        WHERE customer_id = :cid
          AND event_category = 'compliance'
          AND occurred_at > NOW() - INTERVAL '{interval}'
        GROUP BY passed, reason, action_blocked
        ORDER BY n DESC
        LIMIT 20
    """, {"cid": customer_id})

    # Escalations
    escalations = await execute_query(f"""
        SELECT escalation_id, reason, urgency, specialist_type, status,
               sla_due_at, created_at, source_agent, assigned_to, resolved_at
        FROM human_escalations
        WHERE customer_id = :cid
          AND created_at > NOW() - INTERVAL '{interval}'
        ORDER BY created_at DESC
    """, {"cid": customer_id})

    # PTPs
    ptps = await execute_query(f"""
        SELECT ptp_id, promised_amount, promised_date, channel, status, created_at, resolved_at
        FROM promises_to_pay
        WHERE customer_id = :cid
          AND created_at > NOW() - INTERVAL '{interval}'
        ORDER BY created_at DESC
    """, {"cid": customer_id})

    # Validation notice (Reg F §1006.34)
    val_notice = await execute_query("""
        SELECT status, first_contact_at, notice_due_at, notice_sent_at, channel
        FROM validation_notices
        WHERE customer_id = :cid
        ORDER BY created_at DESC LIMIT 1
    """, {"cid": customer_id})

    # Active compliance flags
    flags = await execute_query("""
        SELECT flag_type, reason, created_at FROM compliance_flags
        WHERE customer_id = :cid AND status = 'ACTIVE'
    """, {"cid": customer_id})

    # Strategy assignment (champion/challenger)
    strat_assign = await execute_query("""
        SELECT csa.strategy_version, csa.assigned_at, sv.role, sv.description
        FROM customer_strategy_assignments csa
        LEFT JOIN strategy_versions sv ON sv.strategy_version = csa.strategy_version
        WHERE csa.customer_id = :cid
    """, {"cid": customer_id})

    acct = accounts[0] if accounts else {}
    context = {
        "window": window,
        "customer": {
            "name": f"{p.get('first_name', '')} {p.get('last_name', '')}",
            "customer_id": customer_id,
            "risk_score": p.get("risk_score"),
            "behavioral_score": p.get("behavioral_score"),
            "preferred_channel": p.get("preferred_channel"),
            "tenure_years": _years_since(p.get("relationship_start")),
            "segment": p.get("segment"),
        },
        "account": {
            "product": acct.get("product_type"),
            "balance": float(acct.get("current_balance") or 0),
            "past_due": float(acct.get("total_past_due") or 0),
            "minimum_payment": float(acct.get("minimum_payment") or 0),
            "dpd": acct.get("days_past_due"),
            "delinquency_stage": acct.get("delinquency_stage"),
            "last_payment_date": str(acct.get("last_payment_date")) if acct.get("last_payment_date") else None,
            "last_payment_amount": float(acct.get("last_payment_amount") or 0),
        },
        "active_compliance_flags": flags,
        "strategy_assignment": strat_assign[0] if strat_assign else None,
        "validation_notice": val_notice[0] if val_notice else None,
        "in_window": {
            "channel_summary": channel_summary,
            "stage_transitions": stage_transitions,
            "agent_actions": agent_actions,
            "strategy_decisions": decisions,
            "compliance_summary": compliance_summary,
            "escalations": escalations,
            "ptps": ptps,
        },
        "counts": {
            "channel_buckets": len(channel_summary),
            "stage_transitions": len(stage_transitions),
            "agent_actions": len(agent_actions),
            "strategy_decisions": len(decisions),
            "compliance_evaluations": sum(int(r.get("n") or 0) for r in compliance_summary),
            "escalations": len(escalations),
            "ptps": len(ptps),
        },
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "window": window,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "summary": None,
            "fallback": _structured_digest_fallback(context),
            "highlights": _heuristic_highlights(context),
            "context_size": context["counts"],
            "model": None,
            "note": "ANTHROPIC_API_KEY not set — structured fallback returned",
        }

    system = (
        "You are producing a structured ACTIVITY DIGEST for one customer's collections journey. "
        "The reader is a senior operator (collections head, compliance officer, or risk manager) "
        "who does NOT want to scroll through time-series logs. They need to know — in 60 seconds — "
        "what happened across every dimension, what's notable, and what needs attention.\n\n"
        "Return strict markdown with EXACTLY these sections, in this order. Use the section "
        "headings verbatim. If a section is genuinely empty for the window, write 'No activity' "
        "rather than omit it:\n\n"
        "## Snapshot\n"
        "One sentence summarizing where the customer is right now (stage, DPD, balance, key flag).\n\n"
        "## Profile & Account\n"
        "1-2 sentences on the customer profile and account that's relevant to the journey "
        "(tenure, risk band, preferred channel, product, payment history shape).\n\n"
        "## Customer Activity in Window\n"
        "What the customer did, grouped by channel and intent. Cite counts and time spans. "
        "Use a bullet list if there are 3+ distinct activity types.\n\n"
        "## System Actions\n"
        "What the orchestrator did: strategy evaluations (cite version, segment, treatment), "
        "outbound actions dispatched, stage transitions. Be specific.\n\n"
        "## AI Agent Decisions\n"
        "What AI agents did and why. Group by agent_type. Cite confidence levels, escalation "
        "reasoning, and rationale excerpts in `inline code` or quoted form.\n\n"
        "## Compliance\n"
        "Validation notice status (Reg F §1006.34). Active compliance flags and what they suppress. "
        "Action-gate evaluations: how many passed, how many blocked, and what rules fired.\n\n"
        "## Strategy\n"
        "Which version is assigned (champion/challenger), any segment/treatment/routing notable "
        "changes within the window.\n\n"
        "## Open Items\n"
        "Pending escalations, active PTPs, validation notice deadlines, any in-flight commitments.\n\n"
        "## What Needs Attention\n"
        "1-4 bullet points of concrete things a human should look at or do. Highest priority "
        "first. If nothing needs attention, say so plainly.\n\n"
        "Rules:\n"
        "- Use `inline code` for IDs, dollar amounts, and policy/rule names.\n"
        "- Use **bold** for stage names, urgency levels, and severity words.\n"
        "- Do NOT invent facts not in the input. Do NOT speculate beyond the data.\n"
        "- Do NOT include preamble like 'Here is the digest'.\n"
        "- Keep total length under ~800 words.\n\n"
        "After the markdown, on a NEW LINE, output a single JSON object on one line prefixed "
        "with `HIGHLIGHTS_JSON:` containing 2-4 of the most important items as: "
        '{"items":[{"dimension":"compliance|risk|operations|ai|profile","severity":"low|medium|high|critical","text":"one-line summary"}]}'
    )
    user_prompt = (
        f"Time window: {window}\n\nCustomer context (real data from the orchestration platform):\n"
        f"```json\n{json.dumps(context, default=str, indent=2)[:32000]}\n```"
    )

    client = AsyncAnthropic(api_key=api_key)
    try:
        msg = await client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1800,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "\n".join(b.text for b in msg.content if b.type == "text").strip()

        # Split off the HIGHLIGHTS_JSON line if present
        highlights = _heuristic_highlights(context)
        summary_md = text
        for marker in ("HIGHLIGHTS_JSON:", "\nHIGHLIGHTS_JSON:"):
            idx = text.rfind(marker)
            if idx >= 0:
                summary_md = text[:idx].rstrip()
                tail = text[idx + len(marker):].strip()
                try:
                    parsed = json.loads(tail.splitlines()[0] if "\n" in tail else tail)
                    if isinstance(parsed, dict) and isinstance(parsed.get("items"), list):
                        highlights = parsed["items"][:4]
                except Exception:
                    pass
                break

        return {
            "window": window,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "summary": summary_md,
            "highlights": highlights,
            "context_size": context["counts"],
            "model": msg.model,
            "tokens": {
                "input": msg.usage.input_tokens,
                "output": msg.usage.output_tokens,
            },
        }
    except Exception as e:
        logger.exception("Activity digest generation failed")
        return {
            "window": window,
            "as_of": datetime.utcnow().isoformat() + "Z",
            "summary": None,
            "fallback": _structured_digest_fallback(context),
            "highlights": _heuristic_highlights(context),
            "context_size": context["counts"],
            "error": str(e),
        }


def _heuristic_highlights(ctx: dict) -> list[dict]:
    """Fallback highlights when LLM is unavailable — purely deterministic."""
    h: list[dict] = []
    flags = ctx.get("active_compliance_flags") or []
    if flags:
        h.append({
            "dimension": "compliance",
            "severity": "high",
            "text": f"Active compliance flag(s): {', '.join(f['flag_type'] for f in flags)}",
        })
    esc = ctx.get("in_window", {}).get("escalations") or []
    open_esc = [e for e in esc if e.get("status") == "queued"]
    if open_esc:
        h.append({
            "dimension": "operations",
            "severity": "high" if any(e.get("urgency") == "immediate" for e in open_esc) else "medium",
            "text": f"{len(open_esc)} pending escalation(s) for a human specialist",
        })
    ptps = ctx.get("in_window", {}).get("ptps") or []
    active_ptps = [p for p in ptps if p.get("status") == "ACTIVE"]
    if active_ptps:
        h.append({
            "dimension": "operations",
            "severity": "medium",
            "text": f"{len(active_ptps)} active promise-to-pay commitment(s)",
        })
    val = ctx.get("validation_notice")
    if val and val.get("status") != "sent":
        h.append({
            "dimension": "compliance",
            "severity": "high",
            "text": "Reg F §1006.34 validation notice not yet sent",
        })
    return h[:4]


def _structured_digest_fallback(ctx: dict) -> str:
    """Markdown structured digest when the LLM isn't available."""
    c = ctx.get("customer", {})
    a = ctx.get("account", {})
    counts = ctx.get("counts", {})
    flags = ctx.get("active_compliance_flags") or []
    val = ctx.get("validation_notice") or {}
    strat = ctx.get("strategy_assignment") or {}

    parts = [
        f"## Snapshot",
        f"{c.get('name', 'Customer')} ({c.get('customer_id')}) is **{a.get('delinquency_stage') or 'CURRENT'}**, "
        f"{a.get('dpd', 0)} DPD on a {a.get('product') or 'unspecified product'} with "
        f"${a.get('past_due', 0):,.0f} past due of ${a.get('balance', 0):,.0f} balance.",
        "",
        f"## Profile & Account",
        f"Tenure: {c.get('tenure_years', '?')} years. Risk: {c.get('risk_score')}. "
        f"Preferred channel: {c.get('preferred_channel') or 'unknown'}.",
        "",
        f"## Customer Activity in Window",
        f"{counts.get('channel_buckets', 0)} channel/intent groupings observed in the window.",
        "",
        f"## System Actions",
        f"{counts.get('strategy_decisions', 0)} strategy evaluations, {counts.get('stage_transitions', 0)} stage transitions.",
        "",
        f"## AI Agent Decisions",
        f"{counts.get('agent_actions', 0)} AI agent decisions logged.",
        "",
        f"## Compliance",
        f"Active flags: {', '.join(f['flag_type'] for f in flags) if flags else 'none'}. "
        f"Validation notice: **{val.get('status', 'unknown')}**. "
        f"{counts.get('compliance_evaluations', 0)} action-gate evaluations in window.",
        "",
        f"## Strategy",
        f"Assigned version: `{strat.get('strategy_version', 'v1.0.0')}` ({strat.get('role', '?')}).",
        "",
        f"## Open Items",
        f"{counts.get('escalations', 0)} escalations, {counts.get('ptps', 0)} PTPs in window.",
        "",
        f"## What Needs Attention",
        "_LLM unavailable — see structured counts above._",
    ]
    return "\n".join(parts)


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
