# Stakeholder archetypes

Eight personas appear in nearly every regulated-industry decision-platform engagement. Each has a different first ten questions and a different proof bar. Designing one surface per persona means each one walks out repeating their own one-liner — and that's the demo working.

---

## 1. CEO / President

**Frame of mind:** strategic, business outcomes, ROI, board-level narrative.

**First questions:**
- "Does this move the business?"
- "What does this replace?"
- "What's the time-to-value?"
- "How does this position us vs competitors?"

**Proof bar:** sees a working portfolio dashboard with cure rate, recovery, compliance enforcement — feels operational, not theoretical.

**The one-liner they should repeat:**
> "This is the platform our [collections / claims / lending] engine becomes."

**Don't waste their time on:** transition matrices, Parquet partitioning, Rego syntax.

---

## 2. CTO / CIO

**Frame of mind:** architecture, scalability, technology choices, deployment, integration.

**First questions:**
- "Can we actually deploy this?"
- "What's the operational footprint?"
- "Where does it run? AWS / GCP / Azure / on-prem?"
- "How does it integrate with our existing stack?"
- "What's the auth story? SSO? RBAC?"

**Proof bar:** sees the architecture diagram + Platform Operations page + data lineage flow — concludes "this is a real architecture, not a slide."

**The one-liner they should repeat:**
> "The architecture is real — three independent consumer groups, end-to-end lineage, no proprietary lock-in."

**Show them:** Platform Operations, Data Lakehouse topology + lineage, architecture diagram.

---

## 3. Chief Risk Officer (CRO)

**Frame of mind:** model risk management (SR 11-7 if US bank), portfolio analytics, lift, forecasting.

**First questions:**
- "What's the model? Trained on what?"
- "What's the lift over the existing strategy?"
- "What's the statistical significance?"
- "How do you forecast roll rates?"
- "What's the cohort recovery curve?"

**Proof bar:** sees a real model card with AUC + feature importance + retrain button. Sees A/B test with p-value + 95% CI + required-n. Sees roll-rate Markov projection.

**The one-liner they should repeat:**
> "This is how we'll run model risk management for [collections / lending]."

**Show them:** Risk & ML page, Strategy Console A/B section, Cohort vintage.

---

## 4. Chief Compliance Officer (CCO) / Legal

**Frame of mind:** regulatory exam readiness, audit trail, what would survive a CFPB review.

**First questions:**
- "Show me how Reg F is enforced."
- "Can the audit trail be tampered with?"
- "Where's the validation notice tracking?"
- "What happens when a customer is in bankruptcy?"
- "How do we handle cease-and-desist?"

**Proof bar:** sees policy code citing specific regulations. Sees PASS and FAIL compliance events emitted on every action. Tries to UPDATE an audit row and gets blocked by the trigger.

**The one-liner they should repeat:**
> "We can defend every action we took on this account."

**Show them:** Customer Story compliance section, Strategy Console compliance firing table, the SQL `DELETE` demo on `strategy_audit_log`.

---

## 5. COO / Head of Operations / Head of Collections

**Frame of mind:** does this actually help my team? Will my supervisors use it?

**First questions:**
- "What does my supervisor see?"
- "How do agents handle escalations?"
- "What happens when a customer breaks a PTP?"
- "Can I see one customer's full story end-to-end?"
- "How do I know the AI isn't doing something stupid?"

**Proof bar:** sees the Operations Floor as a live war room. Clicks into a customer and gets a narrative summary instead of a log file. Reads the AI rationale and finds it sensible.

**The one-liner they should repeat:**
> "My supervisors can answer 'why?' on any case in two clicks."

**Show them:** Operations Floor, Customer Story (narrative + Activity Digest), AI Explorer.

---

## 6. Chief Data Officer (CDO) / Head of Analytics

**Frame of mind:** how does this fit my data platform? Lock-in? Lineage?

**First questions:**
- "Where does the data land?"
- "What's the table format? Parquet / Iceberg / Delta?"
- "Can my data scientists query it without going through the application?"
- "How do you handle schema evolution?"
- "What's the lineage story?"

**Proof bar:** sees real S3 buckets with real Parquet files queryable from any external engine. Sees the end-to-end lineage feature that proves the architecture isn't hand-waved.

**The one-liner they should repeat:**
> "The platform writes into a real, queryable lakehouse from day one — no lock-in."

**Show them:** Data Lakehouse topology, lineage flow, ad-hoc DuckDB SQL.

---

## 7. SRE / Platform Engineering

**Frame of mind:** what's the operational footprint? Observability? Failure modes?

**First questions:**
- "How do you know what's running?"
- "What's the consumer lag?"
- "How do you trace a single event?"
- "What's the SLO?"
- "How do you handle backpressure?"

**Proof bar:** sees service heartbeats with throughput + p99. Sees Kafka topology with per-partition offsets + consumer lag. Pastes an event_id and gets a full trace.

**The one-liner they should repeat:**
> "I know what's red, why it's red, and what it'll take to fix."

**Show them:** Platform Operations, trace viewer.

---

## 8. Internal Audit / SOX / SOC 2

**Frame of mind:** is this auditable? Can we produce evidence?

**First questions:**
- "Can the audit log be silently changed?"
- "Where is the evidence for control X?"
- "How do you handle separation of duties?"
- "What's the data retention policy?"
- "How long would it take to respond to a discovery request?"

**Proof bar:** sees the trigger function definition. Verifies it raises on UPDATE/DELETE. Sees that decisions are persisted with full input + output + correlation_id. Reads through the audit table schema.

**The one-liner they should repeat:**
> "We can produce evidence for any control test in minutes, not weeks."

**Show them:** the migration SQL (`migrate_v03_audit.sql`), live `DELETE` demo, Customer Story audit panel.

---

## Less common but still worth designing for

### Product Manager
- "What's the user journey?"
- "How do we A/B test new strategies?"
- Show: Champion / Challenger A/B framework.

### CFO
- "What does this cost to run?"
- "What's the ROI?"
- Show: AI cost dashboard, projected savings from automation.

### Customer Experience Lead
- "How empathetic is the AI?"
- "What does the customer see?"
- Show: AI agent rationale, compliance-aware messaging.

### Procurement / Vendor Management
- "What's the license cost?"
- "What's the lock-in?"
- Show: open-source-first stack, multi-cloud portability.

---

## Industry-specific variations

### Banking
The full eight personas plus:
- **Chief Credit Officer** — wants risk model details
- **Head of Recoveries** — operational deep-dive
- **Compliance Counsel** — regulation interpretation

### Insurance
- **Chief Underwriter** — instead of CRO; same proof bar
- **Chief Medical Officer** — for health insurance, similar role to CCO
- **Claims Operations** — equivalent to Head of Collections

### Healthcare
- **Chief Medical Officer** — clinical credibility
- **Privacy Officer (HIPAA)** — equivalent to CCO + Audit combined
- **Revenue Cycle leader** — for billing/auth workflows

### Capital Markets / Trading
- **Chief Risk Officer** — market risk + credit risk
- **Head of Compliance / Surveillance** — equivalent to CCO
- **Head of Quant** — for ML model credibility

### Telecom / Tech
- **Chief Data Officer** — usually the strongest voice
- **VP Engineering** — equivalent to CTO
- **Head of Customer Operations** — equivalent to COO
