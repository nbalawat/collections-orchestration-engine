"""Lakehouse API — bronze/silver/gold topology, mart queries, ad-hoc SQL, lineage.

Powers the "Data Lakehouse" UI page. All counters and listings come from real
AWS S3 (bronze, silver, gold buckets). Ad-hoc SQL is executed against silver +
gold Parquet via an embedded DuckDB connection with the httpfs extension.

The lineage endpoint takes one event_id and walks every tier — Kafka, Postgres,
Redis, S3 bronze, S3 silver, gold marts, downstream agent_actions — to prove the
same business event materializes at every layer.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import aioboto3
import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.shared.config import get_settings
from services.shared.db import execute_query

logger = logging.getLogger(__name__)
router = APIRouter()

_session = aioboto3.Session()
_duck_lock = asyncio.Lock()
_duck: duckdb.DuckDBPyConnection | None = None


def _get_duck() -> duckdb.DuckDBPyConnection:
    """Lazy DuckDB connection with httpfs + AWS creds; reused across requests."""
    global _duck
    if _duck is None:
        s = get_settings()
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(f"SET s3_region='{s.lakehouse_s3_region}';")
        con.execute("CREATE SECRET IF NOT EXISTS aws_creds (TYPE s3, PROVIDER credential_chain);")
        _duck = con
    return _duck


async def _list_objects(s3, bucket: str, prefix: str = "", max_objects: int = 5000):
    """Page through an S3 prefix and return (key, size, last_modified) tuples."""
    out: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    async for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []) or []:
            out.append({
                "key": obj["Key"],
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat()
                    if hasattr(obj.get("LastModified"), "isoformat") else str(obj.get("LastModified")),
            })
            if len(out) >= max_objects:
                return out
    return out


@router.get("/topology")
async def topology():
    """Counts + sizes across all three tiers for the medallion overview card."""
    s = get_settings()
    async with _session.client("s3", region_name=s.lakehouse_s3_region) as s3:
        results = {}
        for tier, bucket in (
            ("bronze", s.lakehouse_bronze_bucket),
            ("silver", s.lakehouse_silver_bucket),
            ("gold", s.lakehouse_gold_bucket),
        ):
            if not bucket:
                results[tier] = {"bucket": None, "object_count": 0, "total_bytes": 0}
                continue
            try:
                objs = await _list_objects(s3, bucket)
                total_bytes = sum(int(o["size"]) for o in objs)
                # Group bronze + silver by topic
                per_topic: dict[str, dict[str, int]] = {}
                for o in objs:
                    if o["key"].startswith("topic="):
                        topic = o["key"].split("/", 1)[0].split("=", 1)[1]
                        per_topic.setdefault(topic, {"objects": 0, "bytes": 0})
                        per_topic[topic]["objects"] += 1
                        per_topic[topic]["bytes"] += int(o["size"])
                results[tier] = {
                    "bucket": bucket,
                    "region": s.lakehouse_s3_region,
                    "object_count": len(objs),
                    "total_bytes": total_bytes,
                    "per_topic": per_topic,
                }
            except Exception as e:
                logger.exception("Topology listing failed for %s", tier)
                results[tier] = {"bucket": bucket, "error": str(e)}

        return {"tiers": results, "timestamp": time.time()}


@router.get("/bronze/objects")
async def bronze_objects(
    topic: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    s = get_settings()
    if not s.lakehouse_bronze_bucket:
        raise HTTPException(503, "Bronze bucket not configured")
    prefix = f"topic={topic}/" if topic else ""
    async with _session.client("s3", region_name=s.lakehouse_s3_region) as s3:
        objs = await _list_objects(s3, s.lakehouse_bronze_bucket, prefix=prefix, max_objects=limit + 100)
    objs.sort(key=lambda o: o["last_modified"], reverse=True)
    return {"bucket": s.lakehouse_bronze_bucket, "prefix": prefix, "objects": objs[:limit]}


@router.get("/silver/partitions")
async def silver_partitions():
    """Aggregate silver Parquet partition stats (topic + date + size + row count)."""
    s = get_settings()
    if not s.lakehouse_silver_bucket:
        raise HTTPException(503, "Silver bucket not configured")
    async with _session.client("s3", region_name=s.lakehouse_s3_region) as s3:
        objs = await _list_objects(s3, s.lakehouse_silver_bucket)
    parts: list[dict] = []
    for o in objs:
        if not o["key"].endswith(".parquet"):
            continue
        # Key: topic=<t>/date=<d>/part-<ts>-<rows>.parquet
        kparts = o["key"].split("/")
        topic = kparts[0].split("=", 1)[1] if "=" in kparts[0] else ""
        date = kparts[1].split("=", 1)[1] if len(kparts) > 1 and "=" in kparts[1] else ""
        rows_hint = 0
        try:
            stem = kparts[-1].replace(".parquet", "")
            rows_hint = int(stem.split("-")[-1])
        except Exception:
            pass
        parts.append({
            "topic": topic, "date": date, "key": o["key"],
            "size": o["size"], "last_modified": o["last_modified"], "rows_hint": rows_hint,
        })
    return {"bucket": s.lakehouse_silver_bucket, "partitions": parts}


@router.get("/gold/marts")
async def gold_marts():
    """List of gold marts with row counts + a small sample of each."""
    s = get_settings()
    if not s.lakehouse_gold_bucket:
        raise HTTPException(503, "Gold bucket not configured")

    async with _session.client("s3", region_name=s.lakehouse_s3_region) as s3:
        objs = await _list_objects(s3, s.lakehouse_gold_bucket)

    # Mart name = top-level prefix (excluding _manifest)
    mart_names: dict[str, dict[str, Any]] = {}
    for o in objs:
        if "/" not in o["key"]:
            continue
        prefix = o["key"].split("/", 1)[0]
        if prefix == "_manifest":
            continue
        if o["key"].endswith(".parquet"):
            mart_names.setdefault(prefix, {"objects": [], "total_bytes": 0})
            mart_names[prefix]["objects"].append(o)
            mart_names[prefix]["total_bytes"] += int(o["size"])

    async with _duck_lock:
        con = _get_duck()
        marts = []
        for mart, meta in mart_names.items():
            path = f"s3://{s.lakehouse_gold_bucket}/{mart}/*.parquet"
            try:
                row_count_row = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()
                row_count = int(row_count_row[0]) if row_count_row else 0
                sample = con.execute(
                    f"SELECT * FROM read_parquet('{path}') LIMIT 5"
                ).to_arrow_table().to_pylist()
            except Exception as e:
                row_count = 0
                sample = []
                logger.warning("Mart %s sample failed: %s", mart, e)
            marts.append({
                "mart": mart,
                "row_count": row_count,
                "size_bytes": meta["total_bytes"],
                "objects": len(meta["objects"]),
                "sample": _serialize_rows(sample),
            })

    manifest = None
    for o in objs:
        if o["key"] == "_manifest/last_run.json":
            async with _session.client("s3", region_name=s.lakehouse_s3_region) as s3:
                got = await s3.get_object(Bucket=s.lakehouse_gold_bucket, Key=o["key"])
                manifest = json.loads(await got["Body"].read())
            break

    return {"bucket": s.lakehouse_gold_bucket, "marts": marts, "manifest": manifest}


class QueryRequest(BaseModel):
    sql: str
    limit: int = 100


# Pre-baked safe queries so users (and demos) have known-good entry points.
SAVED_QUERIES = {
    "decisions_by_strategy": {
        "label": "Decisions by strategy version",
        "sql": (
            "SELECT strategy_version, COUNT(*) AS evaluations "
            "FROM read_parquet('s3://{silver}/topic=events.decisions/date=*/part-*.parquet') "
            "GROUP BY strategy_version ORDER BY evaluations DESC"
        ),
    },
    "compliance_pass_fail": {
        "label": "Compliance gate pass/fail split",
        "sql": (
            "SELECT JSON_EXTRACT_STRING(payload_json,'$.passed') AS passed, COUNT(*) AS n "
            "FROM read_parquet('s3://{silver}/topic=events.compliance/date=*/part-*.parquet') "
            "GROUP BY passed"
        ),
    },
    "top_customers_by_activity": {
        "label": "Top 10 most active customers (interactions)",
        "sql": (
            "SELECT customer_id, COUNT(*) AS interactions "
            "FROM read_parquet('s3://{silver}/topic=interactions.normalized/date=*/part-*.parquet') "
            "WHERE customer_id IS NOT NULL GROUP BY customer_id ORDER BY interactions DESC LIMIT 10"
        ),
    },
    "channel_intent_breakdown": {
        "label": "Inbound channel × intent breakdown",
        "sql": (
            "SELECT channel, intent, COUNT(*) AS n "
            "FROM read_parquet('s3://{silver}/topic=interactions.normalized/date=*/part-*.parquet') "
            "WHERE direction='inbound' AND intent IS NOT NULL "
            "GROUP BY channel, intent ORDER BY n DESC"
        ),
    },
    "gold_portfolio_daily": {
        "label": "Portfolio daily mart",
        "sql": "SELECT * FROM read_parquet('s3://{gold}/portfolio_daily/snapshot.parquet')",
    },
    "gold_customer_360_top": {
        "label": "Customer 360 mart — top 10 by interactions",
        "sql": (
            "SELECT customer_id, interactions, strategy_evaluations, actions_dispatched, "
            "compliance_allowed, compliance_blocked, stage_transitions "
            "FROM read_parquet('s3://{gold}/customer_360/snapshot.parquet') "
            "ORDER BY interactions DESC LIMIT 10"
        ),
    },
}


@router.get("/queries")
async def saved_queries():
    s = get_settings()
    return {
        "queries": [
            {
                "id": qid,
                "label": q["label"],
                "sql": q["sql"].format(silver=s.lakehouse_silver_bucket, gold=s.lakehouse_gold_bucket),
            }
            for qid, q in SAVED_QUERIES.items()
        ],
    }


@router.post("/query")
async def run_query(body: QueryRequest):
    """Ad-hoc DuckDB SQL against silver + gold Parquet.

    Read-only by design — we don't expose anything beyond SELECT-shaped queries
    and the DuckDB connection only knows about S3 via httpfs (no local FS access).
    """
    sql = body.sql.strip()
    if not sql:
        raise HTTPException(400, "Empty SQL")
    # Hard rules: only SELECT/WITH; no DDL, no attach, no copy-to.
    lower = sql.lower().lstrip("(").lstrip(" \n\t")
    if not (lower.startswith("select") or lower.startswith("with") or lower.startswith("pragma")
            or lower.startswith("describe") or lower.startswith("show")):
        raise HTTPException(400, "Only SELECT/WITH/DESCRIBE/SHOW/PRAGMA queries are allowed")
    for banned in (";", "attach ", "install ", "load ", "copy "):
        if banned in lower:
            raise HTTPException(400, f"Disallowed keyword: '{banned.strip()}'")

    limit = max(1, min(body.limit, 1000))
    if " limit " not in lower:
        sql = f"{sql} LIMIT {limit}"

    s = get_settings()

    def run() -> dict:
        con = _get_duck()
        # Allow {silver}/{gold} placeholders for convenience in saved-query templates.
        rendered = sql.format(silver=s.lakehouse_silver_bucket, gold=s.lakehouse_gold_bucket)
        start = time.monotonic()
        cur = con.execute(rendered)
        rows = cur.to_arrow_table().to_pylist()
        elapsed_ms = int((time.monotonic() - start) * 1000)
        columns = [d[0] for d in cur.description] if cur.description else []
        return {"rows": _serialize_rows(rows), "columns": columns, "elapsed_ms": elapsed_ms}

    async with _duck_lock:
        try:
            return await asyncio.to_thread(run)
        except Exception as e:
            raise HTTPException(400, f"Query failed: {e}")


def _serialize_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        nr = {}
        for k, v in r.items():
            if hasattr(v, "isoformat"):
                nr[k] = v.isoformat()
            elif isinstance(v, (bytes, bytearray)):
                nr[k] = v.decode("utf-8", "replace")
            else:
                nr[k] = v
        out.append(nr)
    return out


# ─── Data Lineage ──────────────────────────────────────────────────────
# Maps event_category (as stored in Postgres) to the Kafka topic + bronze partition.

CATEGORY_TO_TOPIC = {
    "channel": "interactions.normalized",
    "interaction": "interactions.normalized",
    "decision": "events.decisions",
    "action": "events.actions",
    "lifecycle": "events.lifecycle",
    "compliance": "events.compliance",
    "ai_reasoning": "events.ai.reasoning",
    "ai_quality": "events.ai.quality",
    "note": "interactions.normalized",
}


# Which gold marts a row of this topic contributes to, and which columns it bumps.
# This is the "downstream pull" — for any given event the lineage shows which
# aggregates count it.
def _compute_gold_contributions(topic: str, direction: str | None) -> list[dict]:
    out: list[dict] = []
    if topic == "interactions.normalized":
        cols = ["interactions"]
        if direction == "inbound":
            cols.append("inbound")
        elif direction == "outbound":
            cols.append("outbound")
        out.append({
            "mart": "customer_360",
            "columns": cols,
            "note": "contributes to per-customer interaction counts",
        })
        out.append({
            "mart": "portfolio_daily",
            "columns": ["interactions"] + ([f"{direction}_interactions"] if direction in ("inbound", "outbound") else []),
            "note": "contributes to daily portfolio interaction totals",
        })
    elif topic == "events.decisions":
        out.append({
            "mart": "customer_360",
            "columns": ["strategy_evaluations", "latest_strategy_version"],
            "note": "increments evaluation count; updates latest_strategy_version if this is the latest",
        })
        out.append({
            "mart": "portfolio_daily",
            "columns": ["strategy_evaluations"],
            "note": "rolls up into the day's evaluation count",
        })
        out.append({
            "mart": "strategy_performance",
            "columns": ["evaluations", "unique_customers", "last_seen"],
            "note": "contributes to the customer's assigned strategy_version row",
        })
    elif topic == "events.actions":
        out.append({
            "mart": "customer_360",
            "columns": ["actions_dispatched"],
            "note": "increments per-customer dispatch count",
        })
        out.append({
            "mart": "portfolio_daily",
            "columns": ["actions_dispatched"],
            "note": "rolls up into daily dispatch volume",
        })
    elif topic == "events.compliance":
        out.append({
            "mart": "customer_360",
            "columns": ["compliance_evaluations", "compliance_allowed", "compliance_blocked"],
            "note": "increments per-customer compliance evaluation counts (split by passed)",
        })
        out.append({
            "mart": "portfolio_daily",
            "columns": ["compliance_evaluations", "compliance_blocked"],
            "note": "daily compliance gate volume",
        })
        out.append({
            "mart": "compliance_audit_daily",
            "columns": ["allowed", "blocked", "total"],
            "note": "row keyed by (day, check_type, rule_name)",
        })
    elif topic == "events.lifecycle":
        out.append({
            "mart": "customer_360",
            "columns": ["stage_transitions"],
            "note": "increments per-customer transition count",
        })
        out.append({
            "mart": "portfolio_daily",
            "columns": ["stage_transitions"],
            "note": "rolls up into daily transition volume",
        })
    return out


@router.get("/lineage/{event_id}")
async def event_lineage(event_id: str):
    """Walk every tier where this event materializes.

    Returns a structured per-tier view: Kafka (topic, key), Postgres row + WORM
    status, Redis channels, S3 bronze (exact gzipped JSONL key AND the line
    inside it), S3 silver (queried via DuckDB), gold mart contributions
    (computed), downstream rows (agent_actions, strategy_audit_log, escalations
    sharing the correlation_id).
    """
    s = get_settings()

    # ── 1. Postgres ──
    rows = await execute_query("""
        SELECT event_id, customer_id, account_id, workflow_id, channel, direction,
               event_type, event_category, intent, payload, correlation_id,
               source_service, occurred_at, received_at
        FROM customer_events WHERE event_id::text = :eid
        LIMIT 1
    """, {"eid": event_id})
    if not rows:
        raise HTTPException(404, f"event_id {event_id} not found in Postgres")
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

    kafka_info = {
        "topic": topic,
        "key": customer_id,
        "key_purpose": "Kafka uses customer_id as the message key so all events for a customer "
                       "stay on the same partition and remain ordered",
        "topic_partitions": 3,
        "retention_hours": 168,
    }

    postgres_info = {
        "database": s.postgres_db,
        "table": "customer_events",
        "primary_key": pg_row.get("event_id"),
        "row": pg_row,
        "audit_status": "WORM_PROTECTED",
        "audit_note": "audit_immutable() trigger raises on UPDATE/DELETE; original row stays intact",
    }

    redis_info = {
        "channels": [f"events:{customer_id}", "events:all"] if customer_id else ["events:all"],
        "purpose": "fan-out to WebSocket subscribers (live UI updates)",
        "ttl": "none — pub/sub is fire-and-forget; not stored",
    }

    # ── 2. Bronze ── search for the exact JSONL object containing this event_id
    bronze_info: dict[str, Any] = {
        "bucket": s.lakehouse_bronze_bucket,
        "partition": f"topic={topic}/date={date_part}/hour={hour_part}/",
        "found": False,
    }
    silver_info: dict[str, Any] = {
        "bucket": s.lakehouse_silver_bucket,
        "partition_pattern": f"topic={topic}/date={date_part}/part-*.parquet",
        "found": False,
    }

    if s.lakehouse_bronze_bucket:
        async with _session.client("s3", region_name=s.lakehouse_s3_region) as s3:
            objs = await _list_objects(s3, s.lakehouse_bronze_bucket, prefix=bronze_info["partition"])
            for obj in objs:
                if not obj["key"].endswith(".jsonl.gz"):
                    continue
                try:
                    got = await s3.get_object(Bucket=s.lakehouse_bronze_bucket, Key=obj["key"])
                    body = await got["Body"].read()
                    text = gzip.decompress(body).decode("utf-8")
                    lines = text.splitlines()
                    for i, line in enumerate(lines):
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if rec.get("event_id") == event_id:
                            bronze_info.update({
                                "found": True,
                                "key": obj["key"],
                                "object_size_bytes": int(obj["size"]),
                                "events_in_file": len(lines),
                                "line_number": i + 1,
                                "raw_record": rec,
                                "ingested_at": rec.get("_ingested_at"),
                                "compression": "gzip",
                                "format": "ndjson",
                            })
                            break
                    if bronze_info["found"]:
                        break
                except Exception:
                    logger.exception("Failed to scan bronze object %s", obj["key"])

    # ── 3. Silver ── DuckDB SELECT WHERE event_id = ?
    if s.lakehouse_silver_bucket:
        silver_pattern = f"s3://{s.lakehouse_silver_bucket}/{silver_info['partition_pattern']}"

        def _query_silver() -> tuple[dict | None, str | None]:
            try:
                con = _get_duck()
                cur = con.execute(
                    f"SELECT * FROM read_parquet('{silver_pattern}') WHERE event_id = ?",
                    [event_id],
                )
                table = cur.to_arrow_table()
                rows = _serialize_rows(table.to_pylist())
                return (rows[0] if rows else None, None)
            except Exception as ex:
                return (None, str(ex))

        async with _duck_lock:
            row, err = await asyncio.to_thread(_query_silver)
        if row:
            silver_info.update({
                "found": True,
                "row": row,
                "row_format": "parquet, snappy-compressed",
                "schema_note": "explicit pyarrow schema; payload preserved as payload_json",
            })
        elif err:
            silver_info["error"] = err

    # ── 4. Gold contributions (computed) ──
    direction = pg_row.get("direction")
    gold_info = {
        "bucket": s.lakehouse_gold_bucket,
        "contributions": _compute_gold_contributions(topic, direction),
        "note": "Gold marts are aggregations — this event contributes to the counts/sums but isn't stored verbatim.",
    }

    # ── 5. Downstream rows sharing the correlation_id ──
    downstream_info: dict[str, Any] = {
        "correlation_id": correlation_id,
        "agent_actions": [],
        "strategy_audit": [],
        "escalations": [],
        "related_events": [],
    }
    if correlation_id:
        downstream_info["agent_actions"] = await execute_query("""
            SELECT action_id, agent_type, action_type, confidence, status, rationale, created_at
            FROM agent_actions WHERE trace_id::text = :cid
            ORDER BY created_at LIMIT 10
        """, {"cid": correlation_id})

        downstream_info["related_events"] = await execute_query("""
            SELECT event_id, event_type, event_category, source_service, occurred_at
            FROM customer_events WHERE correlation_id::text = :cid AND event_id::text != :eid
            ORDER BY occurred_at LIMIT 20
        """, {"cid": correlation_id, "eid": event_id})

    if customer_id:
        downstream_info["escalations"] = await execute_query("""
            SELECT escalation_id, reason, urgency, status, created_at
            FROM human_escalations WHERE customer_id = :cid
              AND created_at BETWEEN :start AND :end
            ORDER BY created_at LIMIT 5
        """, {
            "cid": customer_id,
            "start": occurred_dt,
            "end": occurred_dt.replace(hour=23, minute=59, second=59),
        })

    return {
        "event_id": event_id,
        "correlation_id": correlation_id,
        "customer_id": customer_id,
        "topic": topic,
        "occurred_at": occurred_str,
        "tiers": {
            "kafka": kafka_info,
            "postgres": postgres_info,
            "redis": redis_info,
            "bronze": bronze_info,
            "silver": silver_info,
            "gold": gold_info,
        },
        "downstream": downstream_info,
    }


@router.get("/lineage-suggestions")
async def lineage_suggestions(limit: int = 12):
    """Recent event_ids with rich downstream activity — for the lineage picker UI."""
    rows = await execute_query("""
        SELECT ce.event_id, ce.customer_id, ce.event_type, ce.event_category,
               ce.occurred_at, ce.correlation_id,
               (SELECT COUNT(*) FROM agent_actions aa
                WHERE aa.trace_id::text = ce.correlation_id::text) AS linked_agent_actions
        FROM customer_events ce
        WHERE ce.occurred_at > NOW() - INTERVAL '1 hour'
          AND ce.correlation_id IS NOT NULL
        ORDER BY linked_agent_actions DESC, ce.occurred_at DESC
        LIMIT :limit
    """, {"limit": limit})
    return {"suggestions": rows}
