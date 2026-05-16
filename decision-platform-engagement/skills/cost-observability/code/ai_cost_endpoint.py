"""AI cost / token-spend dashboard endpoint.

Aggregates per-day per-agent per-model invocations + tokens + latency, applies
the Anthropic rate card to estimate $ cost. Mount with:
    app.include_router(router, prefix="/api/risk", tags=["risk"])
"""
from __future__ import annotations

from fastapi import APIRouter

# Replace with your project's DB helper
async def execute_query(sql: str, params: dict | None = None) -> list[dict]:
    raise NotImplementedError("plug in your project's DB helper")


router = APIRouter()


# ─── Rate card (per million tokens) ──────────────────────────────────
# Anthropic direct rates as of 2026. For Bedrock / Vertex / Azure OpenAI,
# add their published rates.
RATES_PER_M = {
    "claude-opus-4-7":    {"input": 5.00,  "output": 25.00},
    "claude-opus-4-6":    {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-5":  {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00},
    # add Bedrock / Vertex / Azure equivalents as needed
}


@router.get("/ai-cost")
async def ai_cost():
    """Per-day per-agent token spend with $ estimate from the rate card.

    Assumes the AI harness emits AIReasoningTraceEvent records with
    tokens_used, latency_ms, model, agent_type in the payload, persisted
    via the event projector to customer_events.event_category = 'ai_reasoning'.
    """
    rows = await execute_query("""
        SELECT
            DATE_TRUNC('day', occurred_at) AS day,
            payload->>'agent_type' AS agent_type,
            COALESCE(payload->>'model', 'unknown') AS model,
            COUNT(*) AS invocations,
            SUM((payload->>'tokens_used')::int) FILTER (WHERE payload->>'tokens_used' IS NOT NULL) AS tokens,
            AVG((payload->>'latency_ms')::int) FILTER (WHERE payload->>'latency_ms' IS NOT NULL)::int AS avg_latency_ms,
            MAX((payload->>'latency_ms')::int) FILTER (WHERE payload->>'latency_ms' IS NOT NULL) AS max_latency_ms,
            COUNT(*) FILTER (WHERE (payload->>'escalated')::boolean = true) AS escalations
        FROM customer_events
        WHERE event_category = 'ai_reasoning'
          AND occurred_at > NOW() - INTERVAL '7 days'
        GROUP BY day, agent_type, model
        ORDER BY day DESC, tokens DESC NULLS LAST
    """)

    enriched = []
    total_cost = 0.0
    for r in rows:
        model = r.get("model") or "unknown"
        tokens = int(r.get("tokens") or 0)
        # Tokens stored as total. Approximate input/output split as 60/40 if not
        # captured separately (the Anthropic SDK does expose them separately —
        # split them in the trace event for higher accuracy).
        rate = RATES_PER_M.get(model, {"input": 3.00, "output": 15.00})
        input_tokens = int(tokens * 0.6)
        output_tokens = tokens - input_tokens
        cost = (input_tokens / 1_000_000) * rate["input"] + (output_tokens / 1_000_000) * rate["output"]
        total_cost += cost
        enriched.append({
            **r,
            "estimated_cost_usd": round(cost, 4),
            "rate_per_m_input":   rate["input"],
            "rate_per_m_output":  rate["output"],
        })

    return {
        "rows": enriched,
        "total_estimated_cost_usd_7d": round(total_cost, 2),
        "rate_card": RATES_PER_M,
    }
