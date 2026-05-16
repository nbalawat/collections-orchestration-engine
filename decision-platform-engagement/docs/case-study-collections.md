# Reference engagement — collections orchestration platform

The methodology in this plugin was distilled from a single end-to-end engagement: a real-time collections orchestration platform for a bank-grade demo. This document records what was built, what worked, and which patterns are now reusable skills in this plugin.

---

## The engagement at a glance

**Industry:** Banking — collections & recovery
**Regulatory framework:** US federal — Reg F §1006 (CFPB), FDCPA, SOX, SOC 2
**Stakeholders in scope:** CTO, CRO, CCO, COO, CDO, SRE, Audit
**Tech stack:** Temporal · Kafka · OPA · PostgreSQL · Redis · AWS S3 · DuckDB · Anthropic Claude · React + TypeScript
**Engagement form:** working POC, locally runnable + real AWS S3
**Timeline:** intensive build over a single session

---

## What was built

### The orchestration core

- **Channel simulator + traffic generator** — the only simulated piece, deliberately at the edge
- **Signal Bridge** — Kafka consumer routing inbound events to Temporal workflows
- **Per-customer CustomerJourney workflow** — stateful, signal-driven, holds journey state
- **Event Projector** — Kafka → PostgreSQL (audit-of-record) + Redis (pub/sub for live UI)
- **Workflow activities** — `lookup_account`, `compute_contact_stats`, `evaluate_strategy`, `check_compliance`, `dispatch_action`, `invoke_digital_channel_agent`, `invoke_quality_compliance_review`, `ensure_validation_notice_scheduled`, `dispatch_validation_notice`

### The policy engine (OPA)

Six Rego policy modules, hot-reloaded:

- `segmentation.rego` — DPD bucket × risk tier × value segment
- `treatment.rego` — action / message tone / requires_ai_review
- `channel_routing.rego` — recommended channels with fallbacks
- `compliance.rego` — §1006.6(b) quiet hours, §1006.14(b) frequency caps, full suppression
- `transcript_audit.rego` — FDCPA §807 prohibited language, Mini-Miranda, recording disclosure
- `ai_guardrails.rego` — per-agent autonomy & escalation rules

Plus a wrapper `action_gate` rule because OPA's data API cannot directly invoke function-shaped rules.

### The AI agent platform

Five Claude-powered agents, two auto-invoked inside the workflow:

| Agent | Role | When invoked |
|---|---|---|
| Digital Channel | Autonomous customer-facing for SMS / chat | Auto on inbound HARDSHIP, DISPUTE, DISTRESS, PTP, SETTLEMENT_INQUIRY, REFUSAL, COMPLAINT |
| Quality Compliance | Reviews interactions for FDCPA / Reg F | Auto on completed voice calls |
| Copilot | Real-time assistant for human agents | On-demand from agent desktop |
| Case Reasoning | Deep analysis for complex cases | On-demand from supervisor UI |
| Portfolio Intelligence | Aggregate analytics across the book | On-demand from analytics UI |

Each invocation:
1. Loads context (customer 360, journey state, recent events)
2. Runs Claude with `tool_runner` and ~25 real tools (DB reads, OPA calls, Kafka publishes)
3. **Must close with a structured `record_decision`** — action, confidence, rationale, parameters
4. Persists row to `agent_actions` (WORM)
5. Emits reasoning trace with all tool calls

### The audit & WORM layer

PostgreSQL trigger function `audit_immutable()` raises on UPDATE / DELETE attempts. Applied to:

- `strategy_audit_log` (every OPA evaluation)
- `customer_events` (the event store)
- `ai_reasoning_traces`
- `validation_notices`
- `agent_actions` — except for narrow status transitions (recorded → dispatched → completed) handled by a separate `agent_actions_protect_decision` trigger that locks only the decision fields

### Compliance enforcement

- §1006.6(b) quiet hours (8 am – 9 pm local) across voice / sms / dialer / digital
- §1006.14(b) frequency caps: voice ≥ 7 in 7 days, sms ≥ 10, email ≥ 14, total ≥ 21
- §1006.34 validation notice: scheduled on first outbound action, dispatched within 5-day window, persisted with delivery_event_id
- Compliance events emitted on PASS and FAIL (full evaluation log)

### The medallion lakehouse (real AWS S3)

Three real S3 buckets in `us-east-1`:

- `coe-<account>-bronze` — raw gzipped JSON Lines, Hive-partitioned by `topic= / date= / hour=`
- `coe-<account>-silver` — typed Parquet, snappy compression, deduplicated by event_id, idempotent compaction via manifest
- `coe-<account>-gold` — four curated marts: `customer_360`, `portfolio_daily`, `strategy_performance`, `compliance_audit_daily`

Three new services:

- `services/lake_sink.py` — separate Kafka consumer group `lake-sink-bronze`, buffers per (topic, date, hour), flushes every 30s or 500 events
- `services/lakehouse_compactor.py` — runs every 120s, reads bronze, applies explicit pyarrow schema, dedupes, writes Parquet
- `services/lakehouse_gold.py` — runs every 300s, runs DuckDB SQL across silver to produce marts as single rewriteable snapshots

### The risk & ML platform

- `services/ml/features.py` — 25-feature extractor (account, profile, 7d activity, intents, agents, escalations)
- `services/ml/risk_model.py` — sklearn `GradientBoostingClassifier` trained on `stage_change` events. Label: "stage worsened in next N minutes" (lookahead). Trained at startup. AUC ~0.67 on real data. Local explanations via z-score × global importance.
- `services/ml/roll_rate.py` — Markov chain from empirical stage transition counts. Current state from latest-per-customer journey stage. Projects 30/60/90 days. CURED + CHARGED_OFF absorbing.
- A/B significance — two-proportion z-test with lift, 95% CI on difference, p-value, required-n for 5% lift at 80% power
- AI cost dashboard — per-day per-agent token spend × Anthropic rate card

### The eight UI surfaces (React + TypeScript)

- **Operations Floor** (home) — live portfolio pulse, channel heatmap, AI workbench, escalation queue
- **Customer Story** — narrative (Claude) + multi-dimensional Activity Digest + enriched timeline
- **AI Explorer** — live auto-fired panel + manual invocation playground
- **Strategy Console** — 4 stories: Why? · Champion/Challenger · Heatmaps · Audit trail
- **Platform Operations** — service heartbeats · Kafka topology · OPA decisions · end-to-end trace viewer
- **Data Lakehouse** — medallion topology · bronze/silver tables · gold marts · ad-hoc DuckDB SQL · end-to-end data lineage
- **Risk & ML** — model card · scoring · roll-rate · A/B sig · cohort vintage · AI cost
- **Scenarios** — pre-scripted demo scenarios

---

## What worked (and is now a skill)

| Principle | Where it's encoded in this plugin |
|---|---|
| Audit before adding | `skills/mock-audit/` |
| Structured AI decisions | `skills/structured-ai-decisions/` |
| Medallion lakehouse | `skills/medallion-lakehouse/` |
| Compliance as code | `skills/compliance-as-policy/` |
| WORM audit at DB | `skills/worm-audit-trail/` |
| Champion / challenger | `skills/champion-challenger/` |
| Lineage as UI feature | `skills/data-lineage-ui/` |
| One surface per persona | `skills/stakeholder-driven-ui/` |
| Narrative summarization | `skills/narrative-summarization/` |
| AI cost dashboard | `skills/cost-observability/` |

---

## What surprised us (and is now an opinion in the methodology)

**1. The mock audit was the highest-leverage activity in the engagement.**
What looked like a working POC had 18 distinct mocks hidden in places we wouldn't have looked without a deliberate audit pass. Fixing them was a week of work and converted the demo from "neat" to "real" in stakeholder perception.

**2. Compliance events on PASS were surprisingly important.**
Initially the platform emitted compliance events only on FAIL. The block rate was therefore 100% by construction — not useful. After emitting on both PASS and FAIL, the metric became meaningful and auditors had a complete evaluation log instead of a denial log.

**3. The data lineage UI is disproportionately impactful.**
Building a single endpoint that walks an event_id through all six storage tiers — and a UI that renders it as a horizontal flow — took half a day and converted skeptical CTO/CDO conversations into excited ones in under a minute.

**4. Real Anthropic credits matter.**
We hit a credit-exhaustion 429 mid-engagement and had to add an `AI_AUTO_INVOKE_ENABLED` flag and an OAuth-token-aware client. Lesson: budget Claude credits explicitly in the engagement, with a circuit breaker and per-day cap as part of the demo, not an afterthought.

**5. Markdown rendering of AI output is not optional.**
AI agents naturally produce markdown (bold, bullets, inline code). Plain-text rendering looks broken. Use `react-markdown` everywhere AI text appears.

**6. The stakeholder brief HTML doc is the leave-behind everyone wants.**
A self-contained HTML file that exec teams can email, print, or attach to a board pack — far higher follow-up engagement than slides.

---

## Tagged milestones (semver)

The reference engagement progressed through three semver tags:

- **v0.1-poc** — original scenario-theater POC
- **v0.3-real-orchestration** — no mocks inside the orchestration boundary; Reg F enforced; WORM audit triggers in place; champion/challenger framework live
- **v0.5-decision-platform** — real AWS S3 lakehouse with end-to-end lineage; Strategy Console rewrite; Risk & ML platform with trained model + A/B significance; stakeholder brief

Future engagements should use the same semver convention to mark major credibility milestones.

---

## What didn't fit in the reference engagement (now in the roadmap)

- JWT auth + RBAC on the API
- State-specific compliance overlays (NY DFS, CA Rosenthal, etc.)
- Real STT transcription pipeline
- OpenTelemetry tracing
- Cost guardrails / circuit breaker on Claude
- Production IaC (Terraform / CDK)
- MSK + RDS migration
- Customer self-service portal
- Full MLOps (training pipeline, model registry, online serving)
- Iceberg or Delta on the lakehouse

These appear in `/engagement-roadmap` as standard 4-week / 3-month / 9-month horizon items, adjustable per engagement.
