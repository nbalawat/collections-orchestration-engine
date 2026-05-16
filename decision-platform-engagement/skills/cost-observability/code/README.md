# cost-observability · reference code

Per-day per-agent token spend + $ cost from the Anthropic rate card. FinOps for AI.

## Files

- `ai_cost_endpoint.py` — FastAPI route + rate card + aggregation SQL

## Adaptation

1. Make sure your AI agent harness captures `tokens_used`, `latency_ms`, and `model` per invocation (the `base_agent.py` in `structured-ai-decisions/code/` does this).
2. Ensure those fields land in your event store (e.g. `customer_events` with `event_category = 'ai_reasoning'`).
3. Mount the route: `app.include_router(router, prefix="/api/risk", tags=["risk"])`.
4. Build a simple table UI; per-day per-agent per-model rows with dollar cost.

## Rate card

The rates in `RATES_PER_M` are for Anthropic direct (Claude Opus / Sonnet / Haiku). For Bedrock / Vertex / Azure OpenAI, add their published rates to the dict.

## Why this is a demo asset

Three questions a CFO/CTO asks within 5 minutes of seeing AI:

1. "What does it cost?"
2. "What's the unit cost?"
3. "Are you logging AI use?"

The dashboard answers all three at once.
