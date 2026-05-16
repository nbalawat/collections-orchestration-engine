---
name: medallion-lakehouse
description: Medallion (bronze/silver/gold) lakehouse pattern over any object store. Same Kafka event spine feeds both OLTP (low-latency operational reads) and analytics (cheap large scans). Trigger when the user mentions data lake, lakehouse, S3, GCS, Parquet, Iceberg, Delta, analytics-vs-OLTP separation, or "where does the data team plug in".
metadata:
  type: pattern
  tags: [data, lakehouse, analytics]
---

# Medallion lakehouse — same data, two cost curves

## What this solves

Operational reads need to be sub-second. Analytical reads need to scan billions of rows cheaply. These are two cost curves. Serve them from two stores, but make sure the source of truth is the same Kafka spine — no ETL drift, no double-writes from the application.

## The three tiers

### Bronze — raw landing

- **Format:** gzipped JSON Lines, schema-on-read
- **Layout:** Hive-partitioned `s3://bronze/topic=<t>/date=YYYY-MM-DD/hour=HH/<file>.jsonl.gz`
- **Producer:** dedicated Kafka consumer in its own consumer group (do not share with operational projectors)
- **Flush trigger:** time-based (every 30s) AND size-based (every N events per partition), whichever first
- **Properties:** immutable, replayable, schema-permissive

### Silver — typed Parquet

- **Format:** snappy-compressed Parquet with explicit pyarrow schema
- **Layout:** `s3://silver/topic=<t>/date=YYYY-MM-DD/part-<ts>-<rows>.parquet`
- **Producer:** scheduled compactor that reads new Bronze keys (tracked via manifest), dedupes by event_id, writes one Parquet per (topic, date) per run
- **Cadence:** every 2-5 minutes
- **Idempotency:** manifest at `s3://silver/_manifest/processed_keys.json` records which Bronze keys are processed → re-runs are safe

### Gold — curated marts

- **Format:** snapshot Parquet (single rewriteable file per mart, not append)
- **Layout:** `s3://gold/<mart_name>/snapshot.parquet`
- **Producer:** scheduled DuckDB queries that read Silver via `httpfs` extension
- **Cadence:** every 5-15 minutes
- **Manifest:** `s3://gold/_manifest/last_run.json` with timestamps + build_number

## Standard gold marts to build first

| Mart | Grain | Used by |
|---|---|---|
| `customer_360` | one row per customer | Customer story page, ML features |
| `portfolio_daily` | one row per day | Executive dashboard |
| `strategy_performance` | one row per strategy version | A/B comparison |
| `compliance_audit_daily` | one row per (day, check_type, rule_name) | Regulatory reporting |

## Properties to advertise

- **Idempotent compaction.** Silver compactor manifest → re-runs are safe → operations stay simple.
- **Replayable.** Drop Silver, re-run from Bronze → identical Silver. Drop Bronze, replay Kafka → identical Bronze.
- **Schema evolution.** Bronze is JSON (permissive). Silver has explicit schema (controlled). Gold uses `JSON_EXTRACT` against `payload_json` for forward compatibility.
- **Open formats.** Plain Parquet is queryable by DuckDB / Athena / Spark / BigQuery external tables / Snowflake external tables / Trino. No vendor lock-in.

## Optional upgrades

- **Iceberg or Delta on top.** Adds ACID + time travel + schema evolution + branching. Worth it once you have multiple writers or strict compliance requirements.
- **Partition evolution.** As data volume grows, repartition by hour → day or day → month for query efficiency.
- **Z-ordering / clustering.** Optimize the most-queried filter columns (e.g. customer_id, occurred_at).

## Cloud equivalents

| Layer | AWS | GCP | Azure | On-prem |
|---|---|---|---|---|
| Object store | S3 | GCS | ADLS Gen2 | MinIO / Ceph |
| Format | Parquet (+ Iceberg/Delta) | Parquet (+ Iceberg) | Parquet (+ Delta) | Parquet |
| Query engine | Athena / DuckDB | BigQuery external / DuckDB | Synapse / DuckDB | Trino / DuckDB |
| Catalog (optional) | Glue Data Catalog | Dataplex | Purview | Hive Metastore / Nessie |

The pattern is identical across clouds. The skill is portable.

## Common failure modes to avoid

- **Same consumer group for OLTP and lakehouse.** Sharing means an analytics-tier failure stalls operational projection. Always separate.
- **Writing JSON Lines without compression.** Bronze gets large fast; gzip cuts 70%.
- **Letting pyarrow infer the Silver schema.** Empty columns get dropped; schema drifts run-to-run. Define explicitly.
- **Appending to Gold instead of rewriting.** Snapshots are simpler — stakeholders always read "current view of the world."

## Worked example from the reference engagement

Three real AWS S3 buckets, `us-east-1`. Lake Sink as a third Kafka consumer group (`lake-sink-bronze`). Silver compactor every 120s with manifest-based idempotency. Gold builder every 300s producing four marts via embedded DuckDB.

End-to-end latency from event to Bronze: ~30 seconds. Bronze to Silver: ~2 minutes. Silver to Gold: ~5 minutes. Same Kafka events land in Postgres (OLTP) in real time AND in Bronze for analytics — independent consumer groups, independent failure domains.
