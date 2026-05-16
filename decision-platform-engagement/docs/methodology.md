# The Decision Platform Engagement Method

Twelve principles, learned the hard way on one engagement, refined to be applicable to many. Each principle answers a question that comes up in every senior buying conversation in regulated industries.

---

## 1. Audit before adding

**Question it answers:** "Is this real or is it a demo?"

Before you add a single feature, walk the existing codebase systematically and find every mock, stub, fake, hardcoded fallback, sleep-based simulation, and try/except that swallows errors. Catalog them in a findings document. Rank by severity (orchestration core > read paths > write paths > observability).

The audit is the foundation. Building on a system you haven't audited produces a fragile demo that collapses under any senior-level scrutiny. Reviewers can smell hand-waving from across the room.

**Reference engagement:** the initial audit found 18 distinct mocks inside the orchestration boundary — keyword-matching AI agents, stub tools, fabricated recovery estimates, hardcoded OPA inputs. Fixing them was a week of focused work and the highest-leverage thing in the entire engagement.

**Use the skill:** `mock-audit` (auto-triggered when the user mentions "audit", "real vs fake", "production-ready", or asks if a system is demoable).

---

## 2. Define the orchestration boundary explicitly

**Question it answers:** "What's real and what's simulated?"

State, in writing, where simulation stops. In our reference engagement: "Only the channel simulator (inbound SMS/email/voice/dialer from customers) may be simulated. Everything downstream is real production logic."

This contract is the most important sentence in the engagement. It is enforced by code review, by tests, and by audit. When a stakeholder asks "is that fake?" the answer is short and citable.

**Common boundaries by industry:**
- **Collections:** external channel events are simulated; orchestration, AI, compliance, persistence are real.
- **Claims:** claim filings are simulated; eligibility, fraud screening, payment authorization are real.
- **Lending:** loan applications are simulated; underwriting, KYC, decisioning are real.
- **Fraud:** transaction stream is simulated; rules, ML scoring, case management are real.

---

## 3. Real over fake — no exceptions inside the boundary

**Question it answers:** "Does the AI actually do that?"

When the boundary says something is real, it is real. The AI agent makes a real Anthropic/Bedrock call with a real tool runner. The policy engine is a real OPA process evaluated via HTTP. The persistence is real Postgres rows that survive a restart. The lakehouse writes real Parquet to a real object store.

The temptation to fake "for the demo" is the single largest source of credibility loss in this kind of engagement. Resist it. If a piece needs to be faked because the real version isn't ready, mark it explicitly in the UI — don't dress it up.

**Use the skill:** `structured-ai-decisions` (auto-triggered when the user is building AI agents).

---

## 4. Stakeholder-driven UI — one surface per persona

**Question it answers:** "What do *my* people see?"

Every senior buyer needs to picture their team using the platform. A single dashboard can't serve a CRO and a Head of Collections and a CCO — their first ten questions are different. Give each persona their own landing surface, and make every other surface one click away.

**Reference engagement** UI surfaces, each tailored:
- Operations Floor — for the Head of Collections (live portfolio + escalations)
- Customer Story — for case investigators (narrative + timeline + audit)
- AI Explorer — for AI/ML leaders (governed agent activity + manual playground)
- Strategy Console — for CRO / CCO (4 stories: why, A/B, heatmaps, audit)
- Platform Operations — for CTO / SRE (services, Kafka, OPA, traces)
- Data Lakehouse — for CDO (medallion + lineage + ad-hoc SQL)
- Risk & ML — for CRO + data science (model card, scoring, forecasts)

**Use the skill:** `stakeholder-driven-ui`.

---

## 5. Stories over forms

**Question it answers:** "What does this *do*?"

A JSON textarea with an Evaluate button is a developer toy. A pre-scripted case ("Pre-delinquent VIP", "Mid-stage hardship", "Bankruptcy filed") with a one-click flow that renders the policy stack as a horizontal pipeline is a story a stakeholder can repeat.

Convert every interactive surface into 3-5 canonical cases. Each case tells a different policy story. Stakeholders walk away saying "ah, so when X happens, the system does Y."

---

## 6. Compliance as code

**Question it answers:** "How do we know we comply?"

Externalize every regulatory rule into a policy engine (OPA, Drools, custom). Cite the specific regulation section in the policy module. Evaluate the policy at every decision point — and emit a compliance event on both PASS and FAIL.

**Reference engagement** policies citing federal regs:
- `compliance.rego` — §1006.6(b) quiet hours, §1006.14(b) frequency caps
- `transcript_audit.rego` — §1006.34 validation notice, FDCPA §807 prohibited language

The policy engine is the regulator's audit asset. They get a single file per rule, version-controlled, with a citation. Compare to "compliance is enforced inside the application code somewhere" — which is a non-starter for an exam.

**Use the skill:** `compliance-as-policy`.

---

## 7. WORM audit at the database layer

**Question it answers:** "Could someone tamper with the audit trail?"

Tamper-evidence at the application layer is not tamper-evidence. Anyone with database access can `UPDATE` an audit row from outside the application. Enforce immutability at the database layer with triggers that raise on UPDATE/DELETE.

Narrow carve-outs are fine — e.g. on a workflow status column — but the decision fields (action, rationale, confidence, customer_id, created_at) must be locked.

**Verify it works** by trying it: open a SQL prompt, `DELETE FROM strategy_audit_log WHERE …` — the trigger raises with the audit_id in the error message. That is the SOX/SOC2 evidence.

**Use the skill:** `worm-audit-trail`.

---

## 8. Correlation IDs end-to-end

**Question it answers:** "Can we trace this event?"

Every inbound event seeds a correlation_id. It propagates through every downstream system: Kafka headers, workflow state, all downstream events, all log lines, all database rows. Expose a trace endpoint (`/api/trace/{event_id}`) that walks every storage tier and shows the same event materialized at each hop.

This is a single feature with disproportionate stakeholder impact. SRE loves it because debugging becomes a single SQL query. Audit loves it because evidence collection becomes a single API call. The CDO loves it because it proves data lineage isn't a slide.

**Use the skill:** `data-lineage-ui`.

---

## 9. Champion / challenger from day one

**Question it answers:** "How do you safely roll out strategy changes?"

A platform that only knows about one strategy version is a platform that can't ship new strategies safely. Build the A/B framework into the platform from day one — a `strategy_versions` table with allocation %, customer-level random assignment persisted in `customer_strategy_assignments`, every evaluation tagged with version.

Then surface the A/B comparison live: customers, evaluations, agent actions, escalations, cure rate per version. Add a two-proportion z-test for statistical significance with 95% CI and required-n.

This single feature gives the CRO a story they recognize from every clinical trial or ML experiment they've ever run.

**Use the skill:** `champion-challenger`.

---

## 10. Medallion lakehouse — same data, two cost curves

**Question it answers:** "Where does the data team plug in?"

Operational reads need to be sub-second. Analytical reads need to scan billions of rows cheaply. These are two cost curves and they should be served from two data stores — but the source of truth is the same event stream.

The medallion pattern (Bronze raw → Silver typed → Gold curated) is standard, portable, and immediately recognizable to any data professional. On AWS that's S3 + Parquet + DuckDB/Athena. On Azure: ADLS + Parquet + Synapse. On GCP: GCS + Parquet + BigQuery external tables. The pattern is the same.

Two key properties:
- **Idempotent compaction.** Silver compactor tracks processed Bronze keys in a manifest — re-runs are safe.
- **Replayable.** Drop Silver, re-run from Bronze → identical result. Drop Bronze, replay from Kafka → identical result.

**Use the skill:** `medallion-lakehouse`.

---

## 11. Data lineage as a UI feature

**Question it answers:** "Prove the architecture is real."

A great architecture diagram is a slide. Real data lineage is a button. Build a UI where a user can paste any event_id and see the same record materialized at every storage tier — including the exact line number within the exact gzipped object in Bronze, the Parquet row pulled via DuckDB from Silver, the mart contributions in Gold.

This is the single most impactful UI feature you can build for technical stakeholders. It converts skepticism into excitement in 30 seconds.

---

## 12. AI governance — structured, audited, costed

**Question it answers:** "How do we keep the AI on a leash?"

Three rules:

1. **Every AI agent must close with a structured `record_decision` tool call** — action, confidence (calibrated, not hardcoded 0.85), rationale, parameters. No keyword matching on free text. No inferring action from response text.

2. **Persist every invocation.** A row in `agent_actions` with the structured decision; a reasoning trace with all the tool calls and intermediate outputs. WORM-protected (see #7).

3. **Cost dashboard from day one.** Per-agent per-day token spend, $ from the published rate card, average latency, escalation rate. FinOps is part of the demo, not an afterthought.

**Use the skills:** `structured-ai-decisions`, `cost-observability`.

---

## The 12 principles, one sentence each

1. **Audit before adding** — find the mocks before building.
2. **Define the boundary** — explicit contract for what's real.
3. **Real over fake** — no exceptions inside the boundary.
4. **One surface per persona** — each stakeholder gets their own answer.
5. **Stories over forms** — replace JSON playgrounds with case studies.
6. **Compliance as code** — externalize every regulatory rule with citations.
7. **WORM at the DB** — tamper-evidence at the trigger layer.
8. **Correlation IDs everywhere** — every event traceable across every hop.
9. **A/B from day one** — champion/challenger is a platform capability.
10. **Medallion lakehouse** — same data, two cost curves.
11. **Lineage as a UI feature** — prove the architecture with a button.
12. **AI governance** — structured decisions, persisted reasoning, cost dashboard.

A platform that follows these twelve principles survives every senior review I have seen.
