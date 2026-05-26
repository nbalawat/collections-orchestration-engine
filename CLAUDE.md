# Collections Orchestration Engine

## Project Overview
Real-time collections orchestration engine with AI agents. Local Docker Compose development, AWS-ready architecture.

## Tech Stack
- **Python 3.12** — all backend services, Temporal workflows, AI agents
- **FastAPI** — REST API + WebSocket
- **Temporal** — workflow orchestration
- **Kafka (KRaft)** — event bus
- **PostgreSQL 16** — operational store + event store
- **Redis 7** — caching + real-time counters
- **OPA** — strategy/policy engine (Rego)
- **Claude API** — AI agents (anthropic SDK, `@beta_async_tool` + `tool_runner`)
- **React 18 + TypeScript + Tailwind v4 + Recharts** — frontend

## Package Management
- Python: `uv` (pyproject.toml at repo root)
- Node: `pnpm` (web/ directory)

## Running Locally — one command
```bash
make up            # build images + start everything + seed DB
make down          # stop all (keeps data)
make clean         # stop + wipe all volumes (fresh start)
make logs          # tail logs (all services)
make logs SVC=api  # tail one service
make ps            # show running services
make psql          # open psql in postgres container
make seed          # re-seed the database
make help          # list all targets
```

`make up` brings up the entire stack — infra (Postgres / Redis / Kafka / Temporal / OPA), all 8 backend services, the traffic generator, and Caddy serving the frontend at http://localhost. First-time build takes ~5 min; subsequent runs ~30s.

A `traffic_generator` service runs continuously and pushes realistic events through the platform, so the UI populates on its own — no manual `scripts/demo` step needed. (The scripts are still there if you want curated scenarios.)

## URLs (local)
- **Frontend**: http://localhost (served by Caddy, proxies /api → backend)
- **API direct**: http://localhost:8000 (handy for /docs)
- **API Docs**: http://localhost:8000/docs
- **Temporal UI**: http://localhost:8233
- **OPA**: http://localhost:8181

## Deploy to AWS
```bash
make deploy           # provision EC2 + push code + bring up (~10 min first time)
make deploy-logs      # tail logs on EC2
make deploy-ssh       # SSH into EC2
make destroy          # tear down (confirms first)
```

Provisions a single t3.xlarge in us-east-1, security group restricts SSH to your current IP, opens 80/443 to the world. Caddy serves the site at `https://collections.aifirstapplication.com` with a real Let's Encrypt cert and basic auth (default password: `collections-demo-2026`, override with `DEPLOY_BASIC_AUTH_PASSWORD=...`). Cost ~$130/mo (compute + 50GB EBS) plus Anthropic usage.

State is tracked in `.deploy-state` (gitignored). Domain hosted zone: `Z05446501WDE1E8N4CZ0K`.

## Project Structure
- `events/` — Pydantic event models (canonical contract for all services)
- `services/shared/` — Kafka, DB, Redis, config utilities
- `services/ai_agents/` — Claude-powered AI agents with tool use (Agent SDK tool runner)
- `services/channel_simulators/` — Simulated SMS/email/voice/dialer events
- `services/backend-mocks/` — Simulated core banking, payments, CRM
- `services/signal-bridge/` — Kafka consumer → Temporal signal router
- `services/event-projector/` — Kafka consumer → Postgres writer
- `services/api/` — FastAPI BFF (REST + WebSocket)
- `workflows/` — Temporal workflows + activities
- `strategies/` — OPA Rego policies
- `data/` — Synthetic data generators + seed fixtures + SQL schema
- `web/` — React frontend
- `scripts/` — Demo and utility scripts

## Conventions
- All events use Pydantic models from `events/models.py`
- Kafka topic names defined in `events/topics.py`
- Services communicate only through Kafka or Temporal — no direct service-to-service calls
- AI agent actions flow through the Temporal workflow (signal or activity) — agents don't bypass the orchestrator
- Every AI agent action produces a reasoning trace event
- OPA policies are the single source of truth for strategies and compliance rules
- Use `uv run` to execute Python — the venv is managed by uv
