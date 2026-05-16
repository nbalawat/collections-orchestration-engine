---
name: mock-audit
description: Systematic audit of a codebase for mocks/stubs/fakes/hardcoded fallbacks inside the orchestration boundary. Trigger when the user asks "is this real or a demo", "audit this code", "find the fakes", "production-ready", "what's mocked", "honest production code", or when starting any decision-platform engagement.
metadata:
  type: pattern
  tags: [audit, methodology, foundation]
---

# Mock audit — find every fake inside the orchestration boundary

## What this solves

Most "working POCs" in regulated industries hide 10-20 mocks that will collapse under senior-stakeholder scrutiny. The audit is the single highest-leverage activity in any decision-platform engagement: it converts a fragile demo into a credible one.

## When to apply

- Beginning of any engagement (always, before adding features)
- Whenever a stakeholder says "but is the AI actually doing that?"
- After integrating a third-party module that claims to be a stub-only adapter
- Before tagging a release as "production-ready"

## The boundary contract

Before auditing, establish the **orchestration boundary** in writing. A typical contract:

> "Only the channel simulator (inbound events from the external world) may be simulated. Everything downstream — orchestration, AI agents, policy engine, compliance, persistence, lakehouse — must be real production logic."

Without this contract the audit is impossible because there's no definition of "fake".

## What to search for

| Pattern | What it usually hides | Severity |
|---|---|---|
| `random.choice`, `random.randint` for business outcomes | Fabricated decisions presented as real | Critical |
| Hardcoded API responses | Endpoints return canned data instead of querying real stores | Critical |
| `# TODO`, `pass`, `raise NotImplementedError` in agent tools | Stub implementations the LLM "calls" | High |
| Try/except swallowing errors with a fake success | Silent failure dressed as success | High |
| LLM agents without `client.messages.create` (or equivalent) | Fake AI returning string templates | Critical |
| Compliance checks that compute in app code instead of calling policy engine | Compliance theater | Critical |
| Hardcoded inputs to a policy engine (e.g. `voice_attempts_7d=0`) | Rules silently never fire | High |
| `time.sleep(N); return "done"` | Fake processing time | High |
| Imports from `unittest.mock` or `*_mock`, `*_fake`, `*_stub` modules | Direct evidence | Critical |
| Keyword-matching free-text LLM output to infer action | Pretends to be structured AI | Critical |

## The audit protocol

1. **List the inside-boundary surfaces.** Workflow code, AI agents + tools, policy evaluation, persistence, BFF API routes.
2. **Walk each file.** Apply the search patterns above. Use `Grep` for fast pattern checks; use `Read` for fuller inspection of suspect files.
3. **Rank by severity.** Critical = lies in orchestration core. High = stub tools / hardcoded policy inputs. Medium = fabricated analytics. Low = cosmetic placeholders.
4. **Write `docs/audit-findings.md`.** For each finding: file:line, pattern, what it's faking, what it should do instead, recommended fix.
5. **Also catalog clean files.** Knowing what's already real prevents re-auditing it.

## Anti-patterns to reject

- "Add a feature flag" — that's not a fix, that's hiding the mock
- "We'll fix it later" — that's how mocks survive into production
- Trusting comments that say "this is real" without verifying the code
- Skipping a file because it looks trivial

## Worked example from the reference engagement

In the collections engagement, the audit found:

- `base_agent.py` keyword-matched the LLM response to infer `action_taken` and hardcoded `confidence=0.85` → **Critical** → replaced with required `record_decision` structured tool call
- 7 stub AI tools (`compose_response`, `send_payment_link`, etc.) returned echo data → **High** → replaced with real Postgres writes + Kafka publishes
- `evaluate_strategy` activity hardcoded `voice_attempts_7d=0, customer_local_hour=14` → **High** → added `compute_contact_stats` activity that reads real event history
- `evaluate_treatment_paths` fabricated recovery estimates with magic multipliers → **Medium** → replaced with cohort-based estimates from `payment_history`

18 findings total. One week of focused work. The single highest-leverage activity in the engagement.

## Tooling hint

For codebases > 20 files, spawn the `mock-auditor` subagent (in this plugin's `agents/`) to parallelize the search.
