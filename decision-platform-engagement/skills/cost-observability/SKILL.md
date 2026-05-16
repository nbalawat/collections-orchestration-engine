---
name: cost-observability
description: FinOps dashboard for AI spend — per-agent, per-day, per-model token cost computed from the published rate card. Plus latency and escalation rate. Trigger when the user mentions AI cost, FinOps, token spend, "what does Claude cost", LLM budget, rate limiting, or "the bill".
metadata:
  type: pattern
  tags: [ai, cost, observability, finops]
---

# AI cost & token observability

## What this solves

The first technology question every CTO/CFO asks within 5 minutes of seeing AI: "what does this cost to run?" The answer "we'll figure it out later" loses the meeting. A cost dashboard from day one with per-agent per-day spend is the table-stakes answer.

It also protects against runaway spend — a buggy retry loop or a curious operator hitting refresh on the AI digest 100 times can move from "trivial" to "expensive" in an afternoon.

## The pattern

### 1. Capture tokens + latency per invocation

In the agent harness (see `structured-ai-decisions` skill), capture from the LLM response:

```python
total_tokens = message.usage.input_tokens + message.usage.output_tokens
elapsed_ms = int((time.time() - start_time) * 1000)
```

Persist these in the `AIReasoningTraceEvent` so they land in `customer_events` (and flow through to the lakehouse).

### 2. Maintain a rate card

```python
RATES_PER_M = {
    "claude-opus-4-7":    {"input": 5.00,  "output": 25.00},
    "claude-opus-4-6":    {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00},
    # Add Bedrock / Vertex / Azure rates as applicable
}
```

This is intentionally hardcoded — the rate card changes rarely and explicit values are easier to audit than a price-fetcher.

### 3. Per-day, per-agent, per-model aggregation

```sql
SELECT
    DATE_TRUNC('day', occurred_at) AS day,
    payload->>'agent_type' AS agent_type,
    COALESCE(payload->>'model', 'unknown') AS model,
    COUNT(*) AS invocations,
    SUM((payload->>'tokens_used')::int) AS tokens,
    AVG((payload->>'latency_ms')::int)::int AS avg_latency_ms,
    MAX((payload->>'latency_ms')::int) AS max_latency_ms,
    COUNT(*) FILTER (WHERE (payload->>'escalated')::boolean = true) AS escalations
FROM customer_events
WHERE event_category = 'ai_reasoning'
  AND occurred_at > NOW() - INTERVAL '7 days'
GROUP BY day, agent_type, model
ORDER BY day DESC, tokens DESC;
```

Then in application code, compute $ cost per row from the rate card. Approximate the input/output split as 60/40 (or read each separately if the SDK reports them).

### 4. Surface as a dashboard

A simple table per row: day, agent, model, invocations, tokens, avg latency, escalation count, **estimated cost in $**. Plus a hero card with total 7-day spend.

For the reference engagement: `/risk-ml` page → AI cost section.

### 5. Cap and circuit-breaker

For production, wrap the LLM client in a wrapper that:
- Tracks per-minute token spend
- Returns a 429-equivalent if the budget exceeds a daily cap
- Optionally implements a circuit breaker (after N 429s in a row, stop trying for M minutes)

Without this, a credit-exhaustion scenario like the reference engagement hit will cascade through every agent invocation.

## Why this is a demo asset

- **CTO question 1: "What does it cost?"** → dashboard, here's $0.47 / day / 200 customers, projected $X / month at portfolio scale.
- **CFO question 1: "What's the unit cost?"** → cost per agent action / cost per resolved case.
- **CCO question 1: "Are you logging AI use?"** → yes, every invocation, with tokens + latency + decision.

## Common failure modes to avoid

- **Capturing tokens but not surfacing them.** Token usage data sitting in a table that no one looks at is worse than not collecting it.
- **No rate card.** Tokens without dollars don't mean anything to a CFO.
- **Ignoring latency.** A slow agent is expensive even if the per-call cost is small (because of orchestration time, retries, etc.).
- **No cap.** The day Claude credits run out is the day every agent starts erroring; no one sees it until the dashboard goes red.

## Worked example from the reference engagement

`AIReasoningTraceEvent` captures `tokens_used`, `latency_ms`, and `model` per invocation. Persisted via the Event Projector. `/api/risk/ai-cost` aggregates per day × agent × model with the rate card → returns dashboard rows + 7-day total.

UI: `/risk-ml` page → AI cost & token spend section. Shows total $ in last 7 days, rate card, per-row spend with invocations + tokens + avg latency + escalations + $ cost. Total invocations counter for FinOps.
