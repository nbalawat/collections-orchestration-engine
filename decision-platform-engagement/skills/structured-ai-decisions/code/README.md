# structured-ai-decisions · reference code

The base agent harness + `record_decision` tool + audit table schema. Lift and adapt to your domain.

## Files

- `agent_actions.sql` — audit table for AI agent decisions
- `record_decision.py` — the required closing tool every agent must call
- `base_agent.py` — base class enforcing structured decisions, no keyword matching, no hardcoded confidence

## Adaptation

1. Apply `agent_actions.sql` to your DB.
2. Apply the WORM trigger from the `worm-audit-trail` skill's `code/` to this table.
3. Inherit from `CollectionsAgent` (rename to `<YourDomain>Agent`).
4. Provide `get_system_prompt()`, `get_tools()`, `_build_user_message(context)` in your subclass.
5. The harness auto-adds `record_decision` to every agent's tool list.

## What this enforces

- The LLM must call `record_decision` before ending its turn (system prompt addendum demands it).
- Action / confidence / rationale come from the structured tool call — NOT from string-matching the response text.
- Every invocation persists a row to `agent_actions` plus a reasoning trace event.
- Calibrated confidence (not hardcoded 0.85) — the LLM is explicitly told to reflect uncertainty honestly.
