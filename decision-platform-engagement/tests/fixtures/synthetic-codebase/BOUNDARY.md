# Orchestration boundary — synthetic test codebase

## Allowed to be simulated
- Inbound channel events from the external world (`services/channel_simulator.py` if present)

## Must be real
- All workflow code (`workflows/`)
- All AI agent code (`services/*_agent.py`)
- All policy / compliance evaluation
- All persistence (DB writes, projectors)
- All API routes
