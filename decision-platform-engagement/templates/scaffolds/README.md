# Engagement foundation scaffolds

These are starting points the `/engagement-scaffold` command uses to bootstrap a new engagement. Each scaffold is parameterized (`{{placeholder}}` markers) — the command substitutes engagement-specific values from `docs/engagement-profile.md`.

## Files

- `docker-compose.template.yml` — base docker-compose with OLTP + event bus + OPA, parameterized
- `pyproject.template.toml` — Python project layout with the standard deps
- `run-services.template.py` — multi-service runner pattern
- `README.template.md` — engagement README that points at the boundary contract
- `boundary.template.md` — the orchestration boundary contract
- `architecture.template.md` — engagement-specific architecture doc
- `initial-migration.template.sql` — DB foundation: WORM function, audit tables, champion/challenger, agent_actions

## How they're used

The `/engagement-scaffold` command:

1. Reads `docs/engagement-profile.md`
2. Picks the appropriate scaffolds based on the chosen stack
3. Substitutes `{{placeholder}}` markers with profile values
4. Writes the populated files into the engagement repo
5. Reports back with a "what was created" summary and next steps
