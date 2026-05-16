---
name: structured-ai-decisions
description: Pattern for governing AI agent decisions — every invocation must close with a structured tool call capturing action, confidence, rationale, parameters. No keyword matching on free text. Trigger when the user is building Claude/OpenAI/Bedrock agents, when AI agents need to be auditable, when confidence is hardcoded, or when "how do we know what the AI did" comes up.
metadata:
  type: pattern
  tags: [ai, governance, audit]
---

# Structured AI decisions

## What this solves

AI agents that return free-text responses cannot be governed. You can't trust a keyword match on "I'm escalating this" to mean the agent actually escalated. You can't trust a hardcoded `confidence=0.85` to reflect anything real. And you can't satisfy a compliance audit with "well, the AI said something reasonable."

## The pattern

Every AI agent invocation **must** close with a structured tool call: `record_decision(action_type, confidence, rationale, parameters)`. The agent loop continues until the LLM calls this tool, at which point the structured payload is the ground truth.

The base agent harness:

1. Adds `record_decision` to every agent's tool list automatically
2. Appends an addendum to the system prompt requiring the agent to call it before ending
3. Captures the structured payload from the tool call (not from text parsing)
4. Persists a row to `agent_actions` with action, confidence, rationale, parameters, status
5. Emits a reasoning trace event containing every tool call + intermediate output

If the agent ends without calling `record_decision`, treat that as a failure mode → escalate.

## Required record_decision schema

```python
@tool
def record_decision(
    action_type: str,          # The concrete action taken or recommended
    confidence: float,         # 0.0–1.0, CALIBRATED, not hardcoded
    rationale: str,            # 1-3 sentences citing the evidence
    escalate: bool = False,    # True if a human should review
    parameters: str = "{}",    # JSON-encoded structured parameters
) -> str:
    """Record your final decision. You MUST call this before ending your turn."""
```

## System prompt addendum

Add to every agent's system prompt:

```
## FINAL STEP — REQUIRED
Before you finish, you MUST call the `record_decision` tool with:
  - action_type: the concrete action you took or are recommending
  - confidence: 0.0–1.0, calibrated to your actual evidence
    (do not default to 0.85; reflect uncertainty honestly)
  - rationale: 1-3 sentences citing the evidence
  - escalate: true if a human should take over
  - parameters: JSON string with structured parameters

If you cannot complete the analysis, still call record_decision with
action_type='escalated_to_human' and explain why.
```

## What to persist per invocation

| Table | Purpose |
|---|---|
| `agent_actions` | The receipt — one row per decision with action, confidence, rationale, status, trace_id |
| `ai_reasoning_traces` | The reasoning — one row per invocation with all tool_calls, tool_results, latency, token count, model |
| `customer_events` (category=ai_reasoning) | The event-stream view — flows through Kafka so it lands in the lakehouse |

All three must be WORM-protected (see `worm-audit-trail` skill).

## Common failure modes to avoid

- **Keyword matching on response text.** "if 'escalat' in response_text" is the smell. Replace with the structured tool call.
- **Hardcoded confidence.** `confidence = 0.85` for every agent action is a tell. The LLM should provide a calibrated value.
- **No reasoning trace.** "We don't store what the AI thought" → audit will fail.
- **Tools that don't actually do what they say.** A `send_payment_link` tool that doesn't actually send a link is a stub — see `mock-audit` skill.

## Tool inventory pattern

Every agent's tool list should be:
- Read tools (lookup_customer_360, get_journey_state, …) — pull real data
- Policy tools (check_compliance, check_guardrails) — call real OPA
- Write tools (record_ptp, send_payment_link, escalate_to_human) — real persistence + real Kafka publishes
- `record_decision` — auto-appended by the harness

Each write tool must:
- Persist to a real table OR publish to a real Kafka topic
- Return a structured result the LLM can reason about (`{"status": "persisted", "ptp_id": "..."}`)
- Be idempotent if possible

## Worked example from the reference engagement

In the collections engagement, the `DigitalChannelAgent` was originally inferring `action_taken` from keyword-matching the LLM's free-text response and hardcoding `confidence=0.85`. After applying this pattern:

- 6 invocations on a single demo run produced calibrated confidences ranging 0.62–0.97
- Each invocation persisted a row to `agent_actions` with the real action ("escalated_to_human", "initiated_hardship", "responded")
- The rationale text exposed real reasoning ("Customer Alexander Greer cited medical bills as the cause of financial difficulty")
- The reasoning trace captured every tool call the agent made before deciding

This converted the agent from "looks like AI" to "is governed AI."
