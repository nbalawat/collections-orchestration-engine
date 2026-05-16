# Synthetic codebase fixture

Used by the test harness to verify that the `mock-audit` skill and `mock-auditor` agent correctly identify planted mocks. The orchestration boundary is documented in `BOUNDARY.md`.

## Planted mocks (the audit should find all 5)

| # | File | Severity | Type |
|---|---|---|---|
| 1 | `services/fake_agent.py` | Critical | LLM agent without an LLM call (keyword matches free text) |
| 2 | `workflows/compliance_check.py` | Critical | Compliance computed in app code instead of policy engine |
| 3 | `services/stub_dispatcher.py` | High | Stub tool returning echo data with no real persistence |
| 4 | `services/audit_log.py` | High | Audit table writes that swallow errors (try/except → fake success) |
| 5 | `services/channel_writer.py` | Medium | Hardcoded fabricated recovery estimates |

## Files that are NOT mocked (audit should leave them alone)

- `services/real_publisher.py` — actually publishes to Kafka via aiokafka
- `workflows/lookup_account.py` — actually queries Postgres
- `BOUNDARY.md` — documentation
