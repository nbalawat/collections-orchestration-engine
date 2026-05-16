# medallion-lakehouse · reference code

Three services that implement the Bronze → Silver → Gold pipeline. Lift, adapt the topic / table names, deploy.

## Files

- `lake_sink.py` — Kafka consumer → S3 Bronze gzipped JSONL (own consumer group, 30s flush)
- `compactor.py` — Bronze JSONL → Silver Parquet, idempotent via manifest
- `gold_builder.py` — DuckDB SQL over Silver → Gold curated marts
- `mart_definitions.py` — example mart SQL templates

## Adaptation

1. Set env vars: `LAKEHOUSE_BRONZE_BUCKET`, `LAKEHOUSE_SILVER_BUCKET`, `LAKEHOUSE_GOLD_BUCKET`, `LAKEHOUSE_S3_REGION`, `KAFKA_BOOTSTRAP`.
2. Edit the topic list in `lake_sink.py` (the Topics enum).
3. Edit `mart_definitions.py` to define your gold marts. Standard four:
   - `customer_360` (per-entity rollup)
   - `portfolio_daily` (daily KPIs)
   - `strategy_performance` (champion vs challenger)
   - `compliance_audit_daily` (regulatory reporting)
4. Run all three as long-running services (e.g. add to your run_services.py).

## Cloud equivalents

| Layer | AWS (this code) | GCP | Azure |
|---|---|---|---|
| Bronze write | `aioboto3.put_object` | `google-cloud-storage` | `azure-storage-blob` |
| Silver write | same | same | same |
| Gold query  | DuckDB `httpfs` | DuckDB `httpfs` or BigQuery external | DuckDB `httpfs` or Synapse |

The pattern is portable; only the object-store client changes.
