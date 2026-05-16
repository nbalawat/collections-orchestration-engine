---
name: engagement-audit
description: Systematic audit of a codebase for mocks, stubs, fakes, hardcoded fallbacks, and silent error-swallowing inside the orchestration boundary. Produces a findings document ranked by severity.
---

# /engagement-audit

You are auditing this codebase for **mocks inside the orchestration boundary**. This is the single highest-leverage activity in any decision-platform engagement — what looks like a working POC almost always has 10-20 hidden mocks that will collapse under stakeholder scrutiny.

## Pre-requisite

Read `docs/engagement-profile.md` if it exists. The profile defines the orchestration boundary — what's allowed to be simulated (typically channel-side inputs) vs what must be real (everything downstream).

If no profile exists, ask the user to run `/engagement-init` first OR ask them one question: "What's the orchestration boundary? Where does simulation stop?"

## The audit method

Apply the skill `mock-audit` (which is auto-triggered by this command) and walk the codebase systematically:

### 1. Catalog the inside-boundary surfaces

Identify every file that lives inside the orchestration boundary. Typically:

- Workflow / orchestration code (Temporal workflows + activities, Step Functions, etc.)
- AI agent code (LLM-invoking modules + their tools)
- Policy / rule / compliance evaluation code
- Persistence code (DB writers, projectors, replay consumers)
- API routes (the BFF — must read from real stores, not hardcoded responses)
- Backend integrations (anything labelled "backend-mocks" deserves close attention)

### 2. Search patterns

For each file, look for:

| Pattern | Why it matters | Example |
|---|---|---|
| `random.choice` / `random.randint` for business outcomes | Fabricated decisions presented as real | random PTP amounts, fake compliance approval |
| Hardcoded responses | Endpoint returns canned data not from a store | `return {"approved": True}` |
| `TODO`, `pass`, `raise NotImplementedError` | Stub implementations | unfinished agent tools |
| Try/except swallowing errors with a fake success | Silent failure masquerading as success | `except: return {"status": "ok"}` |
| AI agent calls that don't invoke an LLM SDK | Fake AI | string template "responses" without `client.messages.create` |
| Compliance / strategy that computes locally instead of calling the policy engine | Fake compliance | if/else in app code instead of OPA call |
| Hardcoded OPA inputs (`voice_attempts_7d=0`, `customer_local_hour=14`) | Compliance rules silently broken | placeholder values that prevent rules from firing |
| Sleep-based "simulations" | Fakes processing time without doing real work | `time.sleep(2); return "done"` |
| Mock/fake/stub modules or imports | Direct evidence | `from unittest.mock import Mock`, fake adapter packages |
| References to non-existent backend services | Phantom integrations | `https://api.example.com` |

### 3. Rank findings by severity

| Severity | Definition |
|---|---|
| **Critical** | Inside orchestration core. Fabricates business decisions (e.g. keyword-matching an LLM response to infer action; computing compliance verdicts in Python instead of OPA). |
| **High** | Stub tools the AI calls (returns echo data); hardcoded OPA inputs preventing rules from firing; missing required regulatory artifacts (validation notice, etc.) |
| **Medium** | Fabricated analytics (made-up recovery multipliers); fake AI tools that the LLM can call but that don't actually persist or dispatch |
| **Low** | Cosmetic placeholders, hardcoded strategy version, unused defensive fallbacks |

### 4. For each finding, record

- File path and line number
- Pattern name (from the table above)
- What the mock is faking
- What it should do instead
- Recommended fix (specific code change, not abstract)
- Severity

### 5. Use a subagent for parallelism

For codebases > 20 files, spawn the `mock-auditor` subagent (defined in this plugin) to do the search in parallel. Pass the orchestration boundary definition as context.

## Output

Write findings to `docs/audit-findings.md` with this structure:

```markdown
# Audit findings — <timestamp>

## Orchestration boundary

<one paragraph quoting the boundary from engagement-profile.md>

## Findings (N total, ranked by severity)

### Critical (N)
For each: file:line, pattern, what's mocked, fix, citations.

### High (N)
…

### Medium (N)
…

### Low (N)
…

## Clean files

List files that were inspected and are genuinely real — so we know what to leave alone.

## Recommended de-mock sequence

A small ordered list (highest-leverage first) of which findings to fix first, with estimated effort.
```

## What to do next

After the audit, recommend the user proceed with the de-mock work. Typical sequence:

1. Fix Critical findings first (orchestration core lies)
2. Replace stub tools with real implementations (skill: `structured-ai-decisions`)
3. Compute real OPA inputs from real event data
4. Add immutable audit triggers (skill: `worm-audit-trail`)
5. Verify each fix by running the system and checking real persistence

## Anti-pattern guard

Do **not**:
- Recommend "add a feature flag" instead of fixing the mock
- Recommend "we'll fix this later" — that's how mocks survive
- Skip files because they look "trivial"
- Trust comments that say "this is real" — verify the code

Trust nothing in the orchestration boundary that isn't proven real.
