---
name: engagement-roadmap
description: Generate a 3-horizon roadmap (4 weeks / 3 months / 9 months) tailored to current engagement state and target deliverable.
---

# /engagement-roadmap

You are producing a **3-horizon roadmap** that bridges the engagement's current state to its target deliverable. The output goes into the stakeholder brief and serves as the post-demo conversation guide.

## Pre-requisites

Read:
- `docs/engagement-profile.md` (deliverable form, timeline, constraints)
- `docs/audit-findings.md` if present (open issues)
- `docs/capability-matrix.md` (current capabilities)

## The three horizons

### Horizon 1 — Now → 4 weeks

What's needed to make the current build production-defensible. Typical items:

- Auth & RBAC on the API (JWT or session)
- Secrets management (Vault / Secrets Manager pattern)
- Cost & rate-limit guardrails on LLM calls (circuit breaker)
- OpenTelemetry tracing
- State-specific compliance overlays (if applicable)
- Test suite (pytest, Playwright)
- Real STT pipeline (if voice channel is in scope)
- Real outbound dispatch adapters (SMS, email)

### Horizon 2 — 4 weeks → 3 months

What's needed to deploy to a real environment. Typical items:

- Production deployment IaC (Terraform / CDK)
- Migrate to managed services (MSK / RDS / equivalent)
- Multi-tenant + multi-portfolio architecture
- Schema registry for events
- Customer-facing portal (the other side of orchestration)
- Skip tracing / identity verification integration
- Additional channels (WhatsApp, Apple Messages for Business)

### Horizon 3 — 3 → 9 months

Strategic / flywheel items. Typical:

- Full MLOps platform (training, model registry, online serving)
- Champion / challenger with Bayesian uplift modeling
- RAG over policy docs + resolved-case precedents
- Customer 360 embeddings + similarity search
- Iceberg or Delta on the lakehouse with time travel
- Regulatory reporting dashboards (CFPB / SOX exam-ready exports)
- Cross-account / cross-product orchestration

## Tailoring to the engagement

| If the profile says | Adjust the roadmap by |
|---|---|
| "Demo only" deliverable | Compress horizons; focus on what makes the demo durable for follow-ups |
| "Production-ready" deliverable | Expand Horizon 1 to include the auth + deployment items |
| Heavy regulatory frame | Move state-specific overlays into Horizon 1 |
| Heavy AI maturity | Move RAG + embeddings into Horizon 2 |
| Air-gapped / sovereign cloud | Move LLM on-prem options into Horizon 1; emphasize portability |
| Existing data warehouse | Move Iceberg / Delta into Horizon 1; align with their existing lakehouse |

## Sequencing principle

Sequence for **compounding value**:
- Each item should unblock or accelerate the items below it.
- Avoid items that would be thrown away if priorities shift.
- Items in Horizon 1 should produce visible artifacts (deployed environment, dashboards, signed-off security review) by their end.

## Output format

Write to `docs/roadmap.md`:

```markdown
# Roadmap — <engagement name>

**Current state:** <one paragraph summarizing where we are>
**Target deliverable:** <from profile>
**Timeline:** <from profile>

## Horizon 1 · Now → 4 weeks

**Goal:** <what this horizon achieves>

- Item 1 — <description>
  - Effort: S/M/L
  - Why: <unblocks X / addresses concern Y>
- Item 2 …

## Horizon 2 · 4 weeks → 3 months

…

## Horizon 3 · 3 → 9 months

…

## Sequencing rationale

Two paragraphs explaining why this order, what each horizon enables.
```

## Output guarantees

- `docs/roadmap.md` exists with all three horizons
- Each item has effort estimate and rationale
- Final "Sequencing rationale" explains the compounding logic

## What to do next

The roadmap is typically the last engagement artifact. After this, tag the codebase at the current milestone for reproducibility (`git tag -a v0.X-<name>`).
