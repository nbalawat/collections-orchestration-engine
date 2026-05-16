# Architecture — {{engagement_name}}

## One-page architecture

```
External world                                      Real-time path
─────────────                                       ────────────────

{{external_sources}}                       {{simulator_layer}}
                  │                                │
                  ▼                                ▼
                                           ┌──────────────────────────┐
                                           │  {{event_bus}}            │  ← canonical event spine
                                           │  ({{n_topics}} topics)    │
                                           └─┬───────────┬─────────┬──┘
                                             │           │         │
                              ┌──────────────┘           │         └────────────┐
                              ▼                          ▼                      ▼
                       {{signal_target}}          {{oltp_projector}}    {{lake_sink}}
                              │                          │                      │
                              ▼                          ▼                      ▼
                  ┌──────────────────────┐       ┌──────────────┐      ┌──────────────────┐
                  │ {{workflow_engine}}   │       │ {{oltp_db}}   │      │ Bronze (S3)      │
                  │ per-{{entity}} flow  │       │ + WORM        │      │ raw ndjson.gz    │
                  │                      │       └──────────────┘      └────────┬─────────┘
                  │  - lookup            │                                       │
                  │  - evaluate_strategy ─────► {{policy_engine}}                │ compaction
                  │  - check_compliance  ─────► (with citations)                ▼
                  │  - dispatch_action   │                              ┌──────────────────┐
                  │  - invoke_ai_agent ──────► {{llm_provider}}          │ Silver (S3)      │
                  │    record_decision   │      ({{n_agents}} agents)    │ typed Parquet    │
                  └──────────────────────┘                              └────────┬─────────┘
                                                                                 │
                                                                                 ▼
                                                                       ┌──────────────────┐
                                                                       │ Gold (S3)        │
                                                                       │ curated marts:   │
                                                                       │ {{mart_list}}    │
                                                                       └────────┬─────────┘
                                                                                │ DuckDB
                                                                                ▼
                                                                       ┌──────────────────┐
                                                                       │ API + UI + ML    │
                                                                       └──────────────────┘
```

## Properties

- **Independent failure domains:** {{n_consumer_groups}} consumer groups, each isolated
- **At-least-once delivery; idempotent dedup at every tier**
- **Replayable:** drop Silver, recompact → identical; replay {{event_bus}} → identical Bronze
- **Same correlation_id flows through every hop** — traceable end-to-end via `/api/lineage/{event_id}`
- **Two cost curves, one source of truth:** {{oltp_db}} for ops, Parquet for analytics
- **WORM audit at the database trigger layer** — tamper-evident, not just app-evident

## Stakeholder UI surfaces

| Surface | Persona | First-impression metric |
|---|---|---|
| Operations Floor | COO | live portfolio pulse |
| Customer Story | Investigator / CCO | Claude-generated narrative |
| AI Explorer | AI/ML lead | live auto-fired agent counts |
| Strategy Console | CRO / CCO | champion vs challenger comparison |
| Platform Operations | CTO / SRE | services + Kafka + OPA |
| Data Lakehouse | CDO | medallion topology + lineage |
| Risk & ML | CRO + data science | model card + scoring |

## Regulatory frame

- **Regulations:** {{regulations}}
- **Audit requirements:** {{audit_requirements}}
- **WORM-protected tables:** strategy_audit_log, customer_events, ai_reasoning_traces, agent_actions, validation_notices
- **Compliance events emitted on PASS and FAIL** — full evaluation log, not denial log
