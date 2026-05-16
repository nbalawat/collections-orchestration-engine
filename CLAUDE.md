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

## Running Locally
```bash
# 1. Infrastructure
docker compose up -d

# 2. Seed database (first time only)
uv run python -m data.generators.customer_generator
uv run python -m data.generators.seed_database

# 3. All backend services (one command)
uv run python -m scripts.run_services

# 4. Frontend
cd web && pnpm dev

# 5. Demo scenarios
uv run python -m scripts.demo all              # run all scenarios
uv run python -m scripts.demo cross_channel    # single scenario
uv run python -m scripts.demo ai_agents        # exercise all 5 AI agents

# 6. Event replay
uv run python -m scripts.replay --customer CUST-0032 --list
uv run python -m scripts.replay --customer CUST-0032 --speed 2
uv run python -m scripts.replay --category interaction --dry-run
```

## URLs
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:5173
- **Temporal UI**: http://localhost:8233
- **OPA**: http://localhost:8181

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
