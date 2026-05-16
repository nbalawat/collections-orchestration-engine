# Orchestration boundary — {{engagement_name}}

## Allowed to be simulated

- **Channel-side adapters.** Inbound events from the external world that, in production, would come from real customer interactions or third-party integrations. In this engagement:
  - {{simulated_channel_1}}
  - {{simulated_channel_2}}
  - {{simulated_channel_3}}

## Must be real

Everything inside the orchestration boundary:

- **Workflow / orchestration code** ({{workflow_engine}}). Real workflows, real signals, real state.
- **Policy / compliance evaluation** ({{policy_engine}}). Real HTTP calls to the policy engine — never compute compliance in app code.
- **AI agents.** Real LLM API calls ({{llm_provider}}). Structured `record_decision` tool required. No keyword matching on free text. No hardcoded confidence.
- **Persistence.** Real {{oltp_database}} writes with WORM triggers on audit tables. No try/except swallowing errors with a fake success.
- **Event bus.** Real {{event_bus}} producers and consumers. Independent consumer groups for operational vs analytics paths.
- **Lakehouse.** Real {{lakehouse_target}} object storage. Bronze → Silver → Gold pattern. Idempotent compaction. Replayable from Bronze.
- **API & UI.** Real database reads, no hardcoded responses, no mock backends.

## Verification

Run `/engagement-audit` periodically to verify nothing inside the boundary has slipped into a mock state. The audit produces `docs/audit-findings.md` ranked by severity.

## Why this matters

Stakeholders in regulated industries can detect dressed-up demos from across the room. The boundary contract is the single most important sentence in the engagement — it gives every reviewer a citable answer to "is that real?"
