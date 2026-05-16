# Engagement profile — Test Bank Collections (fixture)

**Discovered at:** 2026-05-16T00:00:00Z
**Industry:** Banking — collections & recovery
**Problem statement:** Replace fragmented multi-vendor collections stack with a unified real-time orchestration platform that enforces Reg F at the action gate, supports AI-augmented case handling, and produces auditable evidence for CFPB exams.

## Stakeholders

- **Demo buyer:** CRO
- **Room composition:** CRO, CCO, CTO, COO (Head of Collections)
- **AI maturity:** neutral — open but cautious; needs structured-AI-decision evidence

## Regulatory frame

- **Regulations in scope:** FDCPA, Reg F (§1006.6, §1006.14, §1006.34), SOX, SOC 2 Type II
- **Audit requirements:** SOX (controls over financial reporting), SOC 2, CFPB exam readiness
- **Geographic scope:** US multi-state — needs state overlays (NY DFS, CA Rosenthal, MA, TX, FL)

## Tech stack

| Layer | Choice |
|---|---|
| Workflow engine | Temporal |
| Event bus | Apache Kafka (MSK in target deployment) |
| OLTP database | PostgreSQL (RDS in target) |
| Lakehouse target | AWS S3 |
| Lakehouse format | Parquet (Iceberg in Horizon 2) |
| Policy engine | OPA |
| LLM provider | Anthropic Claude (Bedrock in production) |
| Frontend | React + TypeScript |
| Deployment target | AWS (ECS Fargate / EKS) |

## Scale & timeline

- **Scale signals:** 1.2M active customers, ~50K events/sec peak, ~3K concurrent in-flight journeys
- **Timeline:** 6-week POC → 12-week MVP → quarter+ production
- **Operational constraints:** Customer PII must stay in us-east-1; SSO via Okta; SOC 2 evidence required for production

## Deliverable

- **Form:** laptop-runnable POC + cloud-deployed staging environment
- **Audience format:** architecture review board (8-12 people) + steering committee

## Existing systems

- **Must integrate with:** core banking (FIS), CRM (Salesforce), data warehouse (Snowflake), Okta, Datadog
- **Data available:** synthetic data for POC; real anonymized historical data for ML training in staging

## Recommended preset

**Bank collections** — see `docs/variability-dimensions.md` in this plugin.

## Skill emphasis for this engagement

Top 5 methodology skills:

1. **compliance-as-policy** — Reg F enforcement is the central CCO concern
2. **worm-audit-trail** — SOX + SOC 2 evidence
3. **structured-ai-decisions** — AI maturity is neutral; need governance proof
4. **champion-challenger** — CRO needs safe-rollout story
5. **data-lineage-ui** — CTO + CDO want architecture-is-real proof

## Next commands

1. `/engagement-audit` — audit the existing codebase for mocks
2. `/engagement-stakeholders` — map capabilities to personas in the room
3. `/engagement-demo-flow` — generate the demo path
4. `/engagement-brief` — produce the stakeholder leave-behind HTML
5. `/engagement-roadmap` — generate the 3-horizon roadmap
