# data-lineage-ui · reference code

The /api/lineage/{event_id} endpoint that walks an event across every storage tier, plus the React component that renders it as a horizontal stations flow.

## Files

- `lineage_endpoint.py` — FastAPI route that walks Kafka → Postgres → Redis → S3 Bronze → S3 Silver → Gold
- `DataLineage.tsx` — React component rendering the result as horizontal cards

## Adaptation

1. Edit `lineage_endpoint.py`:
   - Replace `customer_events` with your event table name
   - Adapt `CATEGORY_TO_TOPIC` to your topic names
   - Adapt the S3 bronze partition pattern to your layout
   - Wire your DuckDB connection
2. Mount the route: `app.include_router(router, prefix="/api/lakehouse", tags=["lakehouse"])`
3. Drop `DataLineage.tsx` into your React app; it expects `api.lakehouseLineage(eventId)` and `api.lakehouseLineageSuggestions()` — see your project's API client.
4. Render `<DataLineage />` on the lakehouse page.

## What it gives you

The single highest-impact demo feature for technical stakeholders. A user pastes an event_id, sees the same record materialized at every tier including the exact line within the exact gzipped Bronze object. Converts skeptical CTO/CDO conversations into excited ones in 30 seconds.
