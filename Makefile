.DEFAULT_GOAL := help
.PHONY: help up down restart logs ps build seed clean shell-api shell-db psql open \
        deploy deploy-bootstrap deploy-push deploy-logs deploy-ssh destroy

# ─── Local development ────────────────────────────────────────────────

help:  ## Show this help
	@awk 'BEGIN {FS=":.*##"; printf "Usage: make <target>\n\nTargets:\n"} \
	     /^[a-zA-Z_-]+:.*?##/ {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up:  ## Start everything. Reuses existing images (builds only if missing). Fast.
	@echo "→ Starting infrastructure…"
	docker compose up -d postgres redis kafka temporal opa
	@echo "→ Waiting for infrastructure to be healthy…"
	@docker compose up -d --wait postgres redis kafka 2>&1 | grep -v "^$$" || true
	@echo "→ Seeding database (idempotent — truncates then loads)…"
	docker compose run --rm seed
	@echo "→ Starting backend services + web…"
	docker compose up -d api worker signal-bridge event-projector traffic-generator lake-sink silver-compactor gold-builder temporal-ui web
	@echo ""
	@echo "✓ All services up."
	@echo ""
	@echo "  Frontend (Caddy):  http://localhost"
	@echo "  API docs:          http://localhost:8000/docs"
	@echo "  Temporal UI:       http://localhost:8233"
	@echo ""
	@echo "Tail logs:  make logs           (all)"
	@echo "            make logs SVC=api   (one)"
	@echo "Changed code? Run 'make rebuild' to rebuild only what changed, then 'make up'."

rebuild:  ## Rebuild images (layer-cached — only rebuilds what changed), then restart app
	docker compose build
	docker compose up -d --force-recreate api worker signal-bridge event-projector traffic-generator lake-sink silver-compactor gold-builder web

down:  ## Stop all services (preserves data)
	docker compose down

restart:  ## Restart everything (down + up, no rebuild)
	docker compose down
	$(MAKE) up

logs:  ## Tail logs. Use SVC=<name> for one service (e.g. make logs SVC=api)
	@if [ -n "$(SVC)" ]; then docker compose logs -f $(SVC); else docker compose logs -f --tail=100; fi

ps:  ## Show running services
	docker compose ps

build:  ## Rebuild images (use after code changes)
	docker compose build

seed:  ## Re-seed the database (truncates + reloads from generators)
	docker compose run --rm seed

clean:  ## Stop everything AND remove all data (Postgres, Caddy state, named volumes)
	docker compose down -v
	@echo "✓ All containers + volumes removed. Next 'make up' starts fresh."

shell-api:  ## Open a shell inside the running api container
	docker compose exec api sh

shell-db:  ## Open a shell inside the postgres container
	docker compose exec postgres sh

psql:  ## Open psql on the collections database
	docker compose exec postgres psql -U collections -d collections

open:  ## Open the frontend in your browser
	@command -v open >/dev/null 2>&1 && open http://localhost || echo "Open http://localhost"

# ─── AWS deploy ───────────────────────────────────────────────────────
# Provisions a single EC2 t3.xlarge in us-east-1, installs Docker, runs the
# same compose stack with TLS + basic auth via the production overlay.

deploy: deploy-bootstrap deploy-push  ## Full deploy: provision EC2 + push code + bring up

deploy-bootstrap:  ## Provision EC2 (idempotent — skips if instance already exists)
	@bash scripts/deploy/provision.sh

deploy-push:  ## Push current code + .env to the EC2 box, then `compose up -d`
	@bash scripts/deploy/push.sh

deploy-logs:  ## Tail logs on the deployed instance
	@bash scripts/deploy/logs.sh

deploy-ssh:  ## SSH into the deployed instance
	@bash scripts/deploy/ssh.sh

destroy:  ## Terminate the EC2 instance + clean up SG, key, etc.
	@bash scripts/deploy/destroy.sh
