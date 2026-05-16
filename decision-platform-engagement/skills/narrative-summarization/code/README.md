# narrative-summarization · reference code

The Claude-powered Activity Digest endpoint — multi-dimensional structured summary of a customer/case/claim journey with markdown output and severity-ranked highlights.

## Files

- `system_prompt.txt` — the system prompt enforcing the 9-section structure
- `digest_endpoint.py` — FastAPI endpoint that assembles context, calls Claude, parses highlights

## Adaptation

1. Edit `digest_endpoint.py`:
   - Adapt the context-assembly SQL to your tables (events, actions, decisions, etc.)
   - Adjust the window options if your domain has different time-scales
   - Wire your Anthropic client
2. Edit `system_prompt.txt`:
   - Rename "customer" / "collections journey" to your domain (case / claim / loan / trade)
   - Adjust the section names if your domain needs different dimensions (e.g. add "Clinical" for healthcare)
3. Mount as `/api/<domain>/<entity-id>/digest?window=24h|7d|30d|90d|all`
4. Render the response with `react-markdown` + `remark-gfm` (don't render as plain text — looks broken).

## Cost note

Each digest call costs ~$0.05-0.15 (Opus 4.7). Cache the response per (entity_id, window) with a 60-120s TTL. Cap per-entity-per-day digest count to prevent runaway spend.
