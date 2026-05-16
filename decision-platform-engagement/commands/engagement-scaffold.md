---
name: engagement-scaffold
description: Bootstrap a new engagement's foundation files based on the engagement profile. Lays down docker-compose, src/ layout, initial DB migrations (with WORM triggers), initial OPA policies, agent skeleton. Run this after /engagement-init when starting from greenfield.
---

# /engagement-scaffold

You are bootstrapping a fresh engagement by laying down the foundation files. The output is a directory the user can immediately `docker compose up` and start iterating on.

## Pre-requisites

Read `docs/engagement-profile.md`. The profile tells you:
- Workflow engine choice → which scaffold to use
- Event bus choice → which producer/consumer code
- OLTP database choice → which DB scaffold + migration
- Policy engine choice → OPA or alternative
- LLM provider → which client library and auth pattern
- Frontend choice → which UI scaffold

If the profile is missing, ask the user to run `/engagement-init` first.

## What to scaffold

For each engagement, create at minimum:

### Root files
- `README.md` — what this engagement is, how to run it
- `.gitignore` (Python + Node + IDE defaults + `.env`)
- `.env.example` (referenced from README; never commit secrets)
- `docker-compose.yml` — services per the profile (OLTP, event bus, OPA, etc.)

### Backend
- `pyproject.toml` (or `package.json`, `go.mod`, etc. per stack)
- `services/` — directory structure for each long-running service
- `workflows/` — workflow definitions (Temporal / Step Functions / etc.)
- `events/` — Pydantic / Protobuf event models
- `data/sql/` — DB migrations including:
  - Domain schema (customers, accounts, events, audit tables)
  - WORM triggers (from `skills/worm-audit-trail/code/`)
  - Champion/challenger schema (from `skills/champion-challenger/code/`)
  - Agent_actions table (from `skills/structured-ai-decisions/code/`)
- `strategies/` — OPA Rego files (from `skills/compliance-as-policy/code/`)

### Frontend (if profile says React)
- `web/package.json` with TanStack Query, lucide-react, react-markdown
- `web/src/` minimal scaffold with one persona page (use `skills/stakeholder-driven-ui/code/page-layout-template.tsx`)

### Documentation
- `docs/architecture.md` — architecture diagram filled in for this engagement
- `docs/boundary.md` — explicit orchestration boundary contract (NEW; this anchors everything)

## Adaptation per profile

| Profile says | Use scaffold from |
|---|---|
| `workflow_engine: temporal` | templates/scaffolds/temporal-worker.py |
| `workflow_engine: step-functions` | templates/scaffolds/step-functions-statemachine.json |
| `event_bus: kafka` | templates/scaffolds/kafka-clients.py |
| `event_bus: eventbridge` | templates/scaffolds/eventbridge-clients.py |
| `oltp: postgres` | templates/scaffolds/postgres-migration-base.sql |
| `oltp: dynamodb` | templates/scaffolds/dynamodb-table-defs.yml |
| `policy_engine: opa` | copy `skills/compliance-as-policy/code/*.rego` |
| `llm: anthropic` | copy `skills/structured-ai-decisions/code/base_agent.py` |

## Process

1. **Read the profile.** Extract every stack choice.
2. **Create the directory tree.** Use Bash + Write.
3. **Drop in the code from the skill code/ directories.** Adapt placeholder names (table names, bucket names, env vars) to the engagement's chosen names.
4. **Generate docs/boundary.md** — the orchestration boundary contract. Default:
   > "Only the channel-side adapters (inbound events from the external world) may be simulated. Everything downstream — orchestration, policy evaluation, AI agents, persistence, lakehouse — must be real production logic."
5. **Generate docs/architecture.md** by filling in `templates/architecture-diagram.txt` with engagement-specific values.
6. **Write a README.md** explaining how to run the scaffold.

## Output guarantees

- The user can run `docker compose up -d && uv run python -m scripts.run_services` (or stack equivalent) on the scaffold and have services start
- WORM triggers are in the initial DB migration — no need to add them later
- Champion/challenger schema is seeded with v1.0.0 (champion, 100%) so A/B work can start
- An example OPA policy is loaded
- An example AI agent skeleton compiles
- A README explains the boundary contract and points to next steps

## What to do next

After scaffolding, the user should:

1. `docker compose up -d`
2. Apply the DB migrations
3. Run the services
4. Run `/engagement-audit` periodically to make sure no mocks creep in
5. Build out the persona-specific UI surfaces using `skills/stakeholder-driven-ui/code/`
