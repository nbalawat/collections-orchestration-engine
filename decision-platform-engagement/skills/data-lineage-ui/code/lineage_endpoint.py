"""Lineage endpoint — walks an event across every storage tier.

Reference implementation from the collections engagement. Adapt:
  - CATEGORY_TO_TOPIC: your event category → Kafka topic mapping
  - bronze partition pattern: matches your lake_sink output layout
  - silver Parquet read: through DuckDB httpfs against your S3 bucket
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone

import aioboto3
from fastapi import APIRouter, HTTPException

# Replace with your project's helpers
async def execute_query(sql: str, params: dict | None = None) -> list[dict]:
    raise NotImplementedError("plug in your project's DB helper")

def get_duck_connection():
    """Returns a shared DuckDB connection with httpfs + AWS creds loaded."""
    raise NotImplementedError("plug in your project's DuckDB helper")


router = APIRouter()
_session = aioboto3.Session()

# Map event categories (as stored in your event table) to Kafka topics.
# Adapt to your domain — these are the collections-engine names.
CATEGORY_TO_TOPIC = {
    "channel":      "interactions.normalized",
    "interaction":  "interactions.normalized",
    "decision":     "events.decisions",
    "action":       "events.actions",
    "lifecycle":    "events.lifecycle",
    "compliance":   "events.compliance",
    "ai_reasoning": "events.ai.reasoning",
    "ai_quality":   "events.ai.quality",
}


@router.get("/lineage/{event_id}")
async def event_lineage(event_id: str):
    # 1. Postgres
    rows = await execute_query("""
        SELECT event_id, customer_id, event_type, event_category, channel, direction,
               source_service, payload, correlation_id, occurred_at, received_at
        FROM customer_events WHERE event_id::text = :eid LIMIT 1
    """, {"eid": event_id})
    if not rows:
        raise HTTPException(404, f"event_id {event_id} not found")
    pg_row = rows[0]

    occurred_str = str(pg_row.get("occurred_at") or "")
    try:
        occurred_dt = datetime.fromisoformat(occurred_str.replace("Z", "+00:00"))
    except ValueError:
        occurred_dt = datetime.now(timezone.utc)
    date_part = occurred_dt.strftime("%Y-%m-%d")
    hour_part = occurred_dt.strftime("%H")

    category = pg_row.get("event_category") or ""
    topic = CATEGORY_TO_TOPIC.get(category, "interactions.normalized")
    customer_id = pg_row.get("customer_id") or ""
    correlation_id = str(pg_row.get("correlation_id") or "") or None

    # 2. Bronze — scan the partition for the exact JSONL object containing this event
    bronze_bucket = "<YOUR-BRONZE-BUCKET>"
    silver_bucket = "<YOUR-SILVER-BUCKET>"
    region = "us-east-1"

    bronze_info = {
        "bucket": bronze_bucket,
        "partition": f"topic={topic}/date={date_part}/hour={hour_part}/",
        "found": False,
    }
    silver_info = {
        "bucket": silver_bucket,
        "partition_pattern": f"topic={topic}/date={date_part}/part-*.parquet",
        "found": False,
    }

    async with _session.client("s3", region_name=region) as s3:
        paginator = s3.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=bronze_bucket, Prefix=bronze_info["partition"]):
            for obj in (page.get("Contents") or []):
                if not obj["Key"].endswith(".jsonl.gz"):
                    continue
                got = await s3.get_object(Bucket=bronze_bucket, Key=obj["Key"])
                body = await got["Body"].read()
                lines = gzip.decompress(body).decode("utf-8").splitlines()
                for i, line in enumerate(lines):
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("event_id") == event_id:
                        bronze_info.update({
                            "found": True,
                            "key": obj["Key"],
                            "object_size_bytes": int(obj["Size"]),
                            "events_in_file": len(lines),
                            "line_number": i + 1,
                            "raw_record": rec,
                            "compression": "gzip",
                            "format": "ndjson",
                        })
                        break
                if bronze_info["found"]:
                    break

    # 3. Silver — DuckDB SELECT WHERE event_id = ?
    silver_pattern = f"s3://{silver_bucket}/{silver_info['partition_pattern']}"
    try:
        con = get_duck_connection()
        rows = con.execute(
            f"SELECT * FROM read_parquet('{silver_pattern}') WHERE event_id = ?",
            [event_id],
        ).fetchall()
        if rows:
            cols = [d[0] for d in con.description]
            silver_info.update({
                "found": True,
                "row": dict(zip(cols, rows[0])),
                "row_format": "parquet, snappy-compressed",
            })
    except Exception as e:
        silver_info["error"] = str(e)

    # 4. Gold — compute which marts include this event
    direction = pg_row.get("direction")
    gold_info = {
        "bucket": "<YOUR-GOLD-BUCKET>",
        "contributions": _compute_gold_contributions(topic, direction),
        "note": "Gold marts are aggregations — this event contributes to counts/sums but isn't stored verbatim.",
    }

    # 5. Downstream — events / actions / escalations sharing correlation_id
    downstream = {"correlation_id": correlation_id, "related_events": [], "agent_actions": []}
    if correlation_id:
        downstream["related_events"] = await execute_query("""
            SELECT event_id, event_type, event_category, source_service, occurred_at
            FROM customer_events WHERE correlation_id::text = :cid AND event_id::text != :eid
            ORDER BY occurred_at LIMIT 20
        """, {"cid": correlation_id, "eid": event_id})
        downstream["agent_actions"] = await execute_query("""
            SELECT action_id, agent_type, action_type, confidence, status, rationale, created_at
            FROM agent_actions WHERE trace_id::text = :cid ORDER BY created_at LIMIT 10
        """, {"cid": correlation_id})

    return {
        "event_id": event_id,
        "correlation_id": correlation_id,
        "customer_id": customer_id,
        "topic": topic,
        "occurred_at": occurred_str,
        "tiers": {
            "kafka":    {"topic": topic, "key": customer_id, "topic_partitions": 3, "retention_hours": 168},
            "postgres": {"database": "<your-db>", "table": "customer_events", "primary_key": pg_row.get("event_id"),
                         "row": pg_row, "audit_status": "WORM_PROTECTED"},
            "redis":    {"channels": [f"events:{customer_id}", "events:all"] if customer_id else ["events:all"]},
            "bronze":   bronze_info,
            "silver":   silver_info,
            "gold":     gold_info,
        },
        "downstream": downstream,
    }


def _compute_gold_contributions(topic: str, direction: str | None) -> list[dict]:
    """For each topic, which gold marts include this event and which columns it bumps.
    Adapt to your gold mart schemas."""
    out = []
    if topic in ("interactions.normalized",):
        cols = ["interactions"] + ([direction] if direction in ("inbound", "outbound") else [])
        out.append({"mart": "customer_360", "columns": cols,
                    "note": "contributes to per-customer interaction counts"})
        out.append({"mart": "portfolio_daily", "columns": ["interactions"],
                    "note": "rolls up into daily portfolio totals"})
    elif topic == "events.decisions":
        out.append({"mart": "customer_360", "columns": ["strategy_evaluations"],
                    "note": "increments per-customer evaluation count"})
        out.append({"mart": "strategy_performance", "columns": ["evaluations"],
                    "note": "contributes to assigned strategy version row"})
    elif topic == "events.compliance":
        out.append({"mart": "compliance_audit_daily",
                    "columns": ["allowed", "blocked", "total"],
                    "note": "row keyed by (day, check_type, rule_name)"})
    return out
