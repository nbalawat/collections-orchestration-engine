# Decision Platform Engagement

A Claude Code plugin that turns one successful platform engagement into a repeatable method. Built from a real, bank-grade collections orchestration POC, packaged so any future engagement — different industry, different tech stack, different regulatory frame — can apply the same methodology and reuse the same artifacts.

## What this plugin gives you

**Seven slash commands** that drive an engagement end-to-end:

| Command | What it does |
|---|---|
| `/engagement-init` | Walks the variability questionnaire (industry, stack, regulator, stakeholders) and produces an engagement profile |
| `/engagement-scaffold` | Bootstraps the foundation files (docker-compose, src/, DB migrations with WORM triggers, OPA policies, agent skeleton) from the engagement profile |
| `/engagement-audit` | Systematic audit of a codebase for mocks/stubs/fakes inside the orchestration boundary |
| `/engagement-stakeholders` | Maps platform capabilities onto the specific stakeholders in the room |
| `/engagement-demo-flow` | Generates an N-minute demo path tailored to the engagement profile |
| `/engagement-brief` | Produces a self-contained stakeholder brief HTML (the leave-behind document) |
| `/engagement-roadmap` | 3-horizon roadmap (4 weeks / 3 months / 9 months) from current state |

**Ten methodology skills** that auto-trigger when the user works on the corresponding pattern. Each skill contains the pattern doc (SKILL.md) AND a `code/` subdirectory with copyable reference implementations lifted from the reference engagement:

| Skill | Pattern doc | Reference code |
|---|---|---|
| `mock-audit` | Hidden-mock hunting | `code/find-mocks.sh` — grep-based first pass |
| `structured-ai-decisions` | Governable AI | `code/base_agent.py`, `code/record_decision.py`, `code/agent_actions.sql` |
| `medallion-lakehouse` | Bronze→Silver→Gold | `code/lake_sink.py` — Kafka → S3 gzip JSONL |
| `compliance-as-policy` | Regulatory enforcement | `code/compliance.rego`, `code/transcript_audit.rego`, `code/wrapper.py` |
| `worm-audit-trail` | DB-layer tamper-evidence | `code/audit_immutable.sql`, `code/apply_triggers.sql`, `code/verify.sh` |
| `champion-challenger` | Safe A/B rollout | `code/schema.sql`, `code/allocator.py`, `code/ab_significance.py`, `code/api.py` |
| `data-lineage-ui` | Trace event across tiers | `code/lineage_endpoint.py` — 6-tier walk |
| `stakeholder-driven-ui` | Persona pages | `code/page-layout-template.tsx`, `code/pulse-tile.tsx` |
| `narrative-summarization` | AI-generated summaries | `code/system_prompt.txt` — 9-section structure |
| `cost-observability` | FinOps for AI | `code/ai_cost_endpoint.py` — per-day rate-card |

**Two specialist subagents:**

- `engagement-discoverer` — runs the variability questionnaire interactively
- `mock-auditor` — does a thorough multi-file mock hunt across a codebase

**Five artifact templates** that the slash commands populate:

- `stakeholder-brief.html` — print-quality executive brief
- `architecture-diagram.txt` — ASCII architecture diagram
- `capability-matrix.md` — capability × stakeholder × proof grid
- `demo-flow.md` — N-stop demo path with persona tags and one-liner scripts
- `variability-profile.md` — captured engagement profile from /engagement-init

**Four reference documents:**

- `docs/methodology.md` — the 12 principles
- `docs/variability-dimensions.md` — the catalog of questions to ask
- `docs/stakeholder-archetypes.md` — common personas and their first ten questions
- `docs/case-study-collections.md` — anonymized record of what was built on the reference engagement

## Installation

### As a Claude Code plugin (recommended)

```bash
# Clone or download this directory
cp -R decision-platform-engagement ~/.claude/plugins/

# Verify
ls ~/.claude/plugins/decision-platform-engagement/
```

The commands, skills, and agents will be auto-discovered the next time Claude Code starts.

### As a workspace asset (no installation)

Keep the directory inside any repository and reference it as documentation. Skills and commands can still be invoked manually by pasting them into Claude Code.

## Typical engagement flow

```
Day 0 ────────────────► /engagement-init
                        Discover the variability: industry, stack, regulator,
                        stakeholders. Produces docs/engagement-profile.md.

Day 1 ────────────────► /engagement-audit
                        Find every mock inside the orchestration boundary.
                        Produces docs/audit-findings.md.

Day 2-5 ──────────────► De-mock + build the foundation
                        Skills auto-fire: structured-ai-decisions,
                        compliance-as-policy, worm-audit-trail, champion-challenger.

Day 5-10 ─────────────► Build stakeholder surfaces
                        Skills auto-fire: stakeholder-driven-ui,
                        narrative-summarization.

Day 10-14 ────────────► Add the lakehouse + analytics
                        Skills auto-fire: medallion-lakehouse, data-lineage-ui.

Day 14-21 ────────────► Risk & ML platform
                        Real model, real A/B significance, cost observability.

Day 21 ───────────────► /engagement-stakeholders
                        /engagement-demo-flow
                        /engagement-brief
                        Produce the leave-behind artifacts.

Day 22 ───────────────► /engagement-roadmap
                        Forward plan: 4-week / 3-month / 9-month horizons.
```

## What the methodology is good for

This plugin captures a methodology that works in any setting where:

- A platform decisions in real time across many cases (customers, claims, orders, tickets)
- Regulatory or audit constraints make tamper-evidence non-negotiable
- AI is moving from feature to flywheel and needs governance
- Multiple stakeholders (CTO / CRO / CCO / COO) each need their own answer
- The platform must demo as "real" to a senior buying committee

Industries it has been or could be applied to:

- **Collections & recovery** (reference engagement: bank-grade collections orchestration)
- **Lending & origination** — underwriting decisions with policy + AI
- **Claims processing** — insurance, healthcare
- **AML / KYC / fraud** — decisioning with regulatory audit
- **Customer support orchestration** — multi-channel, AI-assisted
- **Supply chain exception management**
- **Healthcare prior authorization**
- **Trade surveillance**

## The reference engagement (case study)

The reference engagement was a real-time collections orchestration platform demonstrating:

- Per-customer Temporal workflows over a Kafka event spine
- OPA-driven segmentation, treatment, routing, and compliance gating
- Five Claude-powered AI agents with structured decision capture
- Reg F §1006.6 / §1006.14 / §1006.34 enforcement with WORM audit
- Real AWS S3 medallion lakehouse with end-to-end data lineage
- Real sklearn GradientBoosting risk model with feature store
- Markov roll-rate forecasting and A/B significance testing
- Eight stakeholder UI surfaces, one for each persona

See `docs/case-study-collections.md` for the full record. Patterns from that engagement seed every skill in this plugin.

## Testing

The plugin ships with a test harness in `tests/`:

```bash
# Structural tests (fast, free, ~5 seconds)
./tests/run-evals.sh --structural

# Full evals including behavioral (requires ANTHROPIC_API_KEY)
./tests/run-evals.sh --all

# Single skill or command
./tests/run-evals.sh --skill mock-audit
./tests/run-evals.sh --command engagement-init
```

**Structural checks** validate that every skill / command / agent / template is well-formed: required frontmatter, correct field names, trigger conditions present, body sections complete, manifest references valid, etc. Runs in ~5 seconds with no API cost. **130 checks pass at v0.1.0.**

**Behavioral checks** validate that each skill triggers when it should (and not when it shouldn't), and each slash command produces the expected output artifacts. Defined in `tests/scenarios/`; manual run procedure in `tests/CHECKLIST.md`. Costs ~$0.70 per full run.

**Test fixtures** in `tests/fixtures/` include a synthetic codebase with 5 deliberately planted mocks of varying severity — used to verify that the `mock-audit` skill and `mock-auditor` agent find them all and rank them correctly.

Run the structural tests on every commit. Run the behavioral suite before tagging a release.

## License & attribution

Open methodology, encoded as a Claude Code plugin. Adapt for any engagement, attribution appreciated.
