---
name: engagement-init
description: Variability discovery — interactively walks the questionnaire and produces a written engagement profile that drives all subsequent commands.
---

# /engagement-init

You are kicking off a new decision-platform engagement. Your job in this command is to **discover the variability** that will shape every subsequent decision in the project, then **persist that discovery** as an engagement profile document.

## How to run

Use `AskUserQuestion` to walk the user through the questionnaire below. Group related questions. Do not interrogate — explain *why* you're asking, especially when the answer steers a later technical decision.

After the questionnaire, **write the result to `docs/engagement-profile.md`** (create the `docs/` directory in the current working directory if it doesn't exist). Use the template at `templates/variability-profile.md` in this plugin as the structure.

## The questionnaire

Reference `docs/variability-dimensions.md` in this plugin for the full catalog. Ask in this order:

### Pass 1 — Domain & stakeholders (frames everything)

1. **Industry & problem.** What industry is this for, and what's the specific problem? (Collections, lending, claims, fraud, …)
2. **Demo buyer.** Who's the person whose budget pays for this? (CEO, CTO, CRO, CCO, COO, CDO, other)
3. **Room composition.** Who else will be in the buying-decision meetings? (Architecture board, audit, legal, SRE, data science, product, procurement)
4. **AI maturity.** How AI-mature is the org? (Skeptical / neutral / enthusiastic / sophisticated)

### Pass 2 — Regulatory frame

5. **Regulations in scope.** Which apply? (FDCPA, GDPR, HIPAA, PCI-DSS, SOX, AML/KYC, MiFID II, MAS, FCA, RBI, others)
6. **Audit requirements.** SOX, SOC 2, HIPAA, CFPB exam, internal audit only?
7. **Geographic scope.** Single-country, multi-state, multi-region with residency requirements?

### Pass 3 — Tech stack

8. **Workflow engine.** Temporal, Step Functions, Cadence, Airflow, custom?
9. **Event bus.** Kafka, EventBridge, Kinesis, Pub/Sub, Service Bus, RabbitMQ?
10. **OLTP database.** Postgres, MySQL, SQL Server, Oracle, DynamoDB, Cosmos?
11. **Lakehouse target.** S3, GCS, Azure Blob, MinIO, on-prem?
12. **Lakehouse format.** Parquet, Iceberg, Delta, Hudi, none?
13. **Policy engine.** OPA, Drools, Cedar, custom, embedded?
14. **LLM provider.** Anthropic direct, Bedrock, Vertex, Azure OpenAI, on-prem?
15. **Frontend.** React, Vue, Angular, server-rendered, API-only?
16. **Deployment target.** AWS, GCP, Azure, on-prem, hybrid, sovereign cloud?

### Pass 4 — Scale, timeline, output

17. **Scale signals.** Number of customers/cases, events/sec, concurrent workflows.
18. **Timeline.** 2-week, 6-week, 12-week, quarter+?
19. **Operational constraints.** Data residency, air-gap, existing SSO, HSM requirements?
20. **Deliverable form.** Demo only, laptop POC, cloud staging, production-ready, methodology transfer?
21. **Audience format.** 1-on-1, architecture board (5-15), steering committee, board, public?

### Pass 5 — Existing systems

22. **Systems to integrate with.** Core systems, CRM, data warehouse, IdP, observability, existing rule engines?
23. **Data available.** Real data (with handling), synthetic only, historical for ML training, existing policies?

## What to do after the questionnaire

1. **Produce the profile.** Write to `docs/engagement-profile.md`. Include all answers, the recommended preset (from variability-dimensions.md "Common engagement profiles"), and the skills most relevant to this engagement.

2. **Recommend skill emphasis.** Based on the answers, list the 3-5 most important methodology skills for this engagement. For example:
   - SOX-heavy → `worm-audit-trail` front and center
   - AI-skeptical org → `structured-ai-decisions` is critical
   - New product launch → `champion-challenger` is the headline

3. **Set expectations.** Tell the user what they'll do next:
   - `/engagement-audit` — find the mocks
   - `/engagement-demo-flow` — generate the demo path once we have something to demo
   - `/engagement-brief` — generate the stakeholder leave-behind

## Style notes

- Don't ask all 23 questions in one wall of text. Use 4-5 questions per `AskUserQuestion` call, grouped logically.
- For each answer that's an enum (e.g. workflow engine), offer the most likely 2-4 options and let "Other" capture the rest.
- If the user has clear context (e.g. "we're a US bank doing collections"), pre-populate the obvious answers and confirm rather than re-ask.
- The profile is a living document. The user will return to it as they build.

## Output guarantees

- `docs/engagement-profile.md` exists and is well-formed
- A clear "next steps" section at the bottom of your final message naming `/engagement-audit` as the recommended next command
