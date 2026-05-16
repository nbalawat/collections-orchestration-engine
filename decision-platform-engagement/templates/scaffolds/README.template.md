# {{engagement_name}}

{{engagement_description}}

## Orchestration boundary

See `docs/boundary.md`. The short version: only channel-side adapters are simulated. Everything else is real.

## Running locally

```bash
# 1. Infrastructure
docker compose up -d

# 2. Apply DB foundation (idempotent)
docker exec -i {{db_container}} psql -U {{db_user}} -d {{db_name}} < data/sql/init.sql

# 3. All backend services
uv run python -m scripts.run_services

# 4. Frontend
cd web && pnpm dev
```

## URLs

- **API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Frontend:** http://localhost:5173
- **Temporal UI:** http://localhost:8080
- **OPA:** http://localhost:8181

## Methodology

This engagement follows the [decision-platform-engagement methodology](../decision-platform-engagement/docs/methodology.md):

- **Audit before adding.** Run `/engagement-audit` regularly. Mocks inside the orchestration boundary are not allowed.
- **Compliance as code.** Regulatory rules live in `strategies/` as OPA Rego files with citations.
- **WORM audit at the DB.** Try `DELETE FROM strategy_audit_log` — the trigger raises.
- **Champion/challenger from day one.** New strategies roll out via `strategy_versions.allocation_pct` adjustment.
- **AI governance.** Every agent invocation must close with `record_decision`. No keyword matching.

## Next steps

1. Implement the first persona surface — see `decision-platform-engagement/skills/stakeholder-driven-ui/code/`
2. Wire the first AI agent using `decision-platform-engagement/skills/structured-ai-decisions/code/base_agent.py`
3. Add your first regulation as an OPA policy module
4. Run `/engagement-stakeholders` to map capabilities onto the room
5. Run `/engagement-demo-flow` and `/engagement-brief` before the first demo
