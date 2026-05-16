# Orchestration patterns — how personas collaborate

The engagement-lead persona drives all engagement work by spawning specialist persona agents in proven coordination patterns. This document catalogs the canonical patterns.

---

## Pattern A — Bootstrap a new engagement

Used when starting from greenfield (or a thin POC that needs proper foundation).

```
engagement-lead
  ├─ /engagement-init                          → docs/engagement-profile.md
  │                                              (uses engagement-discoverer agent)
  ├─ spawn solution-architect
  │     reads engagement-profile.md
  │     produces docs/architecture.md + docs/boundary.md
  │     proposes capability list
  │
  ├─ spawn cloud-engineer
  │     reads engagement-profile.md + architecture.md
  │     produces docker-compose.yml, .env.example, secrets pattern
  │     verifies docker compose up works
  │
  ├─ /engagement-scaffold                      → foundation files (data/sql/init.sql, strategies/, etc.)
  │
  ├─ spawn data-engineer + compliance-engineer   ← IN PARALLEL
  │     data-engineer:        events/, signal-bridge, projector, lake_sink, compactor, gold builder, lineage
  │     compliance-engineer:  OPA policies, WORM triggers, validation-notice tracking
  │
  ├─ spawn ai-engineer
  │     reads compliance-engineer's policies (for guardrails)
  │     produces base_agent harness + first agent class
  │     wires auto-invocation in workflow
  │
  ├─ spawn risk-engineer + ml-engineer            ← IN PARALLEL (if profile includes ML/risk)
  │     risk-engineer:  champion/challenger schema + allocator + A/B significance
  │     ml-engineer:    feature store + risk model + roll-rate
  │
  ├─ spawn sre-engineer
  │     wires service heartbeats into every long-running service
  │     builds Platform Ops endpoints (Kafka topology, consumer lag, OPA feed)
  │
  ├─ spawn frontend-engineer
  │     uses the API surface to build the first persona page (usually Operations Floor)
  │     adds Markdown wrapper for AI text
  │
  └─ reports completion to user; recommends /engagement-audit as next step
```

**Estimated wall-clock** (Claude with appropriate parallelism): 30-90 min for the technical work, then iterative refinement.

---

## Pattern B — Add a new capability

Used when extending an existing engagement with a new feature.

```
engagement-lead
  ├─ identifies the capability domain (e.g. "real-time STT for voice")
  ├─ determines lead persona (e.g. ai-engineer for STT + ml-engineer for transcript scoring)
  ├─ optionally spawns solution-architect for structural decisions
  │
  ├─ spawn lead persona
  │     produces the core implementation
  │
  ├─ spawn supporting personas (often parallel)
  │     compliance-engineer: any regulatory implications
  │     data-engineer:        new event types or schema changes
  │     frontend-engineer:    surface in UI
  │
  └─ updates docs/capability-matrix.md
```

### Common "add a capability" recipes

| Capability to add | Lead | Support |
|---|---|---|
| New regulation (e.g. NY DFS overlay) | compliance-engineer | data-engineer (compute new inputs) + frontend-engineer (surface) |
| New AI agent (e.g. Settlement Negotiator) | ai-engineer | compliance-engineer (guardrails) + frontend-engineer (UI) |
| New event source (e.g. WhatsApp channel) | data-engineer | ai-engineer (intent classification) + compliance-engineer (channel rules) |
| New analytical mart | data-engineer (gold builder) | frontend-engineer (chart) |
| New persona page | frontend-engineer | data-engineer (API support) |
| New ML model | ml-engineer | data-engineer (feature data) + risk-engineer (validation) |
| Production deployment | cloud-engineer | sre-engineer (runbook) + compliance-engineer (compliance attestations) |

---

## Pattern C — Demo preparation

Used in the week before a major stakeholder presentation.

```
engagement-lead
  ├─ /engagement-stakeholders                  → docs/capability-matrix.md
  ├─ /engagement-demo-flow                     → docs/demo-flow.md
  ├─ /engagement-brief                         → docs/stakeholder-brief.html
  │
  ├─ spawn each relevant persona in parallel    ← each reviews their section of the brief
  │     solution-architect:   architecture diagram accuracy
  │     compliance-engineer:  regulatory claims accuracy
  │     ai-engineer:          AI capability descriptions
  │     data-engineer:        lakehouse claims
  │     risk-engineer:        A/B + model card claims
  │     frontend-engineer:    UI references accurate
  │     sre-engineer:         observability story complete
  │     cloud-engineer:       deployment story complete
  │
  ├─ consolidate review feedback into final brief
  ├─ /engagement-roadmap                       → docs/roadmap.md (companion document)
  └─ tag the repo with v0.X-<engagement-state>
```

**Estimated wall-clock**: 1-3 days, mostly iteration on the brief.

---

## Pattern D — Audit & remediate

Used periodically (every 1-2 weeks during build) to ensure mocks haven't crept in.

```
engagement-lead
  ├─ /engagement-audit                         → docs/audit-findings.md
  │                                              (uses mock-auditor subagent for parallelism)
  ├─ groups findings by owning persona based on file path:
  │     services/*_agent.py, agent tools     → ai-engineer
  │     workflows/activities/compliance*,
  │     strategies/*.rego                    → compliance-engineer
  │     services/lake_sink.py, lakehouse_*   → data-engineer
  │     services/ml/*                        → ml-engineer
  │     web/src/pages/*                      → frontend-engineer
  │     observability code                   → sre-engineer
  │     infrastructure code                  → cloud-engineer
  │
  ├─ spawn each owning persona in parallel
  │     each fixes the findings in their domain
  │     each updates docs/audit-findings.md with status
  │
  ├─ re-run /engagement-audit to verify
  └─ if findings remain, iterate
```

**Estimated wall-clock**: 1-2 days for a typical engagement with 10-20 findings.

---

## Pattern E — Production hardening

Used when moving from demo-ready to production-deployable.

```
engagement-lead
  ├─ spawn cloud-engineer (Horizon 1: auth + secrets + IaC + cost guardrails)
  ├─ spawn sre-engineer (Horizon 1: OpenTelemetry + alerting + runbooks)
  ├─ spawn compliance-engineer (Horizon 1: state-specific overlays + regulatory reports)
  ├─ spawn data-engineer (Horizon 2: Iceberg/Delta upgrade, schema registry)
  ├─ spawn ml-engineer (Horizon 2: MLOps platform — training pipeline, model registry)
  │
  └─ all in parallel; engagement-lead consolidates progress
```

---

## How engagement-lead spawns personas

Always pass a **self-contained briefing** — personas have no memory of prior conversation. Include:

1. The engagement context (1-2 sentences from the profile)
2. What specifically the persona should produce (concrete artifacts)
3. What inputs they should read (file paths)
4. Who they hand off to next
5. Any constraints unique to this engagement

### Good briefing example

```
Agent({
  subagent_type: "compliance-engineer",
  description: "Add NY DFS overlay to compliance policies",
  prompt: "
    Engagement profile at docs/engagement-profile.md says this is a US
    multi-state collections platform; we need to add a NY DFS overlay
    beyond the existing federal Reg F.

    Read:
    - docs/engagement-profile.md (regulatory frame section)
    - strategies/compliance.rego (existing federal policies)
    - skills/compliance-as-policy/code/compliance.rego (reference patterns)

    Produce:
    - strategies/compliance_ny_dfs.rego — overlay with NY-specific rules
      (NY DFS Part 1, Part 2 collection conduct standards)
    - Update wrapper.py to select overlay based on customer's address_state
    - Add a test fixture covering a NY customer to verify the overlay fires

    Hand off to data-engineer to ensure address_state is in the OPA input,
    and to frontend-engineer to surface state-specific compliance in the UI.
  "
})
```

### Bad briefing example (don't do this)

```
Agent({
  subagent_type: "compliance-engineer",
  prompt: "Add state-specific compliance rules."
})
```

Why bad: no context, no specific output, no inputs, no handoff — the persona has to guess.

---

## When to NOT spawn a persona

Sometimes the engagement-lead should just do the work directly:

- Updating a doc that's 3 sentences
- Fixing a typo in a Rego file
- Rerunning `/engagement-audit` after a small change

Spawn personas when:
- The work is substantive (>30 min of focused work)
- The work is in a specialized domain (architecture, IaC, ML)
- Parallelism would save wall-clock time
- The work would benefit from a fresh context window (avoiding context pollution)
