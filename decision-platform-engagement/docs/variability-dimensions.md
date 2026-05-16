# Variability dimensions — what changes engagement to engagement

This document catalogs the questions to ask at the start of any engagement. The methodology stays constant; the answers here determine which adapters to use, which patterns to emphasize, and which stakeholders to design for.

These dimensions are codified into `/engagement-init` and the `engagement-discoverer` subagent.

---

## A. Domain & problem statement

**A1. What industry is this for?**
- Collections & recovery (banking)
- Lending & origination (banking, fintech)
- Claims processing (insurance, healthcare)
- AML / KYC / fraud (banking, fintech)
- Customer support orchestration (any)
- Supply chain exception management (manufacturing, retail)
- Prior authorization (healthcare)
- Trade surveillance (capital markets)
- Other

**A2. What's the specific problem being solved?**
- Real-time decisioning across many cases
- Workflow orchestration with branching paths
- Cross-channel customer engagement
- Risk-based prioritization
- Compliance enforcement at the action layer
- Audit & explainability for a regulator
- ML/AI-augmented operations

**A3. What's the scope of the demo?**
- Greenfield POC (build from scratch)
- Replatform (replace existing system)
- Augment (sit alongside existing system)
- Integration (connect existing systems)

---

## B. Regulatory framework

**B1. Which regulations apply?** (select all)
- **US:** FDCPA, Reg F (CFPB §1006), FCRA, HMDA, BSA/AML, PCI-DSS, HIPAA, SOX, SR 11-7
- **EU:** GDPR, MiFID II, PSD2, DORA, AI Act
- **APAC:** MAS (Singapore), HKMA (Hong Kong), APRA (Australia), RBI (India), JFSA (Japan)
- **Cross-border:** FATF AML guidelines, SOC 2, ISO 27001
- **Other regional** — specify

**B2. Audit requirements:**
- SOX (financial reporting controls)
- SOC 2 Type II (security + availability + confidentiality)
- HIPAA audit (healthcare PHI)
- Reg E / Reg Z disclosure tracking
- CFPB / OCC / FDIC exam readiness
- Internal audit only

**B3. Geographic scope:**
- Single-country
- US multi-state (each with own overlays)
- EU-wide (GDPR baseline + national overlays)
- Multi-region with data residency requirements

---

## C. Stakeholders

**C1. Who is the demo buyer?** (the person whose budget pays for this)
- CEO / President
- CTO / CIO
- CRO (Chief Risk Officer)
- CCO (Chief Compliance Officer)
- COO / Head of Operations / Head of Collections
- CDO (Chief Data Officer)
- Other line-of-business leader

**C2. Who else will be in the room?** (select all)
- Architecture review board
- Internal audit
- Legal / Privacy counsel
- SRE / Platform engineering
- Data science / ML
- Product
- Vendor management / procurement

**C3. AI maturity of the buying organization:**
- Skeptical — needs proof of governance before AI is acceptable
- Neutral — open but cautious
- Enthusiastic — already invested, wants to see new use cases
- Sophisticated — has AI governance in place, will deeply test

---

## D. Tech stack (current and target)

**D1. Workflow / orchestration engine:**
- Temporal (preferred for durable workflows)
- AWS Step Functions
- Cadence
- Apache Airflow
- Camunda / BPMN
- Custom / in-app
- None yet

**D2. Event bus / streaming:**
- Apache Kafka (self-hosted or MSK / Confluent Cloud)
- AWS EventBridge
- AWS Kinesis
- Google Pub/Sub
- Azure Service Bus / Event Hubs
- RabbitMQ
- None / synchronous-only

**D3. OLTP database:**
- PostgreSQL (preferred for WORM-trigger support)
- MySQL / MariaDB
- Microsoft SQL Server
- Oracle
- DynamoDB / CosmosDB
- MongoDB

**D4. Object storage / lakehouse target:**
- AWS S3
- Google Cloud Storage
- Azure Blob Storage / ADLS Gen2
- On-prem (MinIO, Ceph, HDFS)
- Hybrid

**D5. Lakehouse table format:**
- Plain Parquet (good for POC)
- Apache Iceberg (production-grade)
- Delta Lake (production-grade, Databricks-friendly)
- Apache Hudi
- None / raw files only

**D6. Analytics engine:**
- DuckDB (embedded, recommended for POC)
- Apache Athena
- BigQuery external tables
- Snowflake external tables
- Spark / Databricks
- Trino / Presto
- Redshift Spectrum

**D7. Policy engine:**
- Open Policy Agent (OPA) — recommended
- Drools
- AWS Cedar
- Custom rules engine
- Embedded if/else in application code

**D8. LLM provider:**
- Anthropic direct (Claude API)
- AWS Bedrock (Claude / Llama / Titan)
- Google Vertex AI (Claude / Gemini)
- Azure OpenAI Service
- On-prem (Llama, Mistral, self-hosted)
- None / no LLM

**D9. Frontend:**
- React + TypeScript (reference engagement)
- Vue / Angular
- Server-rendered (Next.js, Remix, Rails, Django)
- No UI — API-only

**D10. Deployment target:**
- AWS (ECS / EKS / Fargate)
- Google Cloud Run / GKE
- Azure (Container Apps / AKS)
- On-prem Kubernetes
- Hybrid (control plane on-prem, data plane in cloud)
- Sovereign cloud (regional requirement)

---

## E. Scale & timeline

**E1. Scale signals:**
- Number of customers / cases / records
- Events per second target
- Concurrent in-flight workflows
- Data volume at 30/90/365 days

**E2. Timeline:**
- 2-week proof
- 6-week POC
- 12-week MVP
- Quarter+ production deployment

**E3. Operational constraints:**
- Data residency (must stay in country X)
- Air-gapped environment (no internet)
- Existing SSO / IdP integration required
- Specific HSM / KMS requirements
- 24/7 ops vs business hours only

---

## F. Output form

**F1. What is the deliverable?**
- Demo only (browser walk-through, no install)
- POC code that runs on a laptop
- Cloud-deployed staging environment
- Production-ready system with IaC
- Methodology transfer (training the in-house team)

**F2. Audience format:**
- 1-on-1 executive briefing
- Architecture review board (5-15 people)
- Steering committee
- Board presentation
- Public conference / vendor showcase

---

## G. Existing systems

**G1. What's already in place that we must integrate with?**
- Core banking / claims / ERP system (name and version)
- CRM (Salesforce, Microsoft Dynamics, custom)
- Data warehouse / lakehouse already in use
- Identity provider (Okta, Azure AD, Auth0, custom)
- Logging & observability (Splunk, Datadog, ELK)
- Existing decision engines / rule engines

**G2. What organizational data is available?**
- Real customer / case data (with appropriate handling)
- Synthetic data only
- Historical event data for ML training
- Existing policies / rule books / SOPs

---

## How these dimensions drive the build

The `/engagement-init` command produces a `variability-profile.md` answering all of the above. From that profile:

- **Stack adapter choice.** If they said Kafka + Postgres + S3 + OPA + Claude, use the reference stack. If they said EventBridge + DynamoDB + Cedar + Bedrock, adapt the same patterns with those substitutions.
- **Skill emphasis.** A SOX-focused engagement leans heavily on `worm-audit-trail`. A new-product launch leans on `champion-challenger`. A heavily AI-skeptical org needs `structured-ai-decisions` front and center.
- **Demo flow.** The `/engagement-demo-flow` command tailors the 12-min path based on who's in the room (C2 + C3).
- **Stakeholder brief.** `/engagement-brief` produces an HTML document highlighting the capabilities most relevant to the audience.
- **Roadmap.** `/engagement-roadmap` sequences the work based on F1 (deliverable form) and E2 (timeline).

---

## Common engagement profiles

For quick reference, here are a few "preset" profiles the questionnaire often lands on:

| Profile | Industry | Stack | Stakeholders | Lead skills |
|---|---|---|---|---|
| **Bank collections** | Collections | Kafka + Postgres + OPA + S3 + Claude | CRO, CCO, COO | compliance-as-policy, worm-audit-trail, champion-challenger |
| **Insurance claims** | Claims | Kafka + Postgres + Cedar + S3 + Bedrock | COO, CCO, CMO | structured-ai-decisions, medallion-lakehouse, narrative-summarization |
| **Lending decisioning** | Lending | Kafka + Postgres + OPA + S3 + Vertex | CRO, CCO, Product | compliance-as-policy, champion-challenger, data-lineage-ui |
| **AML / fraud** | Fraud | Kinesis + DynamoDB + custom-rules + S3 + Bedrock | CCO, CRO, SRE | worm-audit-trail, cost-observability, structured-ai-decisions |
| **Healthcare prior auth** | Healthcare | Kafka + Postgres + Drools + S3 + Azure OpenAI | CMO, CCO, Legal | compliance-as-policy, narrative-summarization, stakeholder-driven-ui |
| **Trade surveillance** | Capital markets | Kafka + Postgres + OPA + Iceberg/S3 + on-prem LLM | CCO, CTO, Audit | worm-audit-trail, data-lineage-ui, cost-observability |

These are starting points. The questionnaire refines them.
