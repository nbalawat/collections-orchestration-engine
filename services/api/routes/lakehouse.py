"""Lakehouse API — bronze/silver/gold topology, mart queries, ad-hoc SQL.

Powers the "Data Lakehouse" UI page. All counters and listings come from real
AWS S3 (bronze, silver, gold buckets). Ad-hoc SQL is executed against silver +
gold Parquet via an embedded DuckDB connection with the httpfs extension.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aioboto3
import duckdb
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.shared.config import get_settings

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
