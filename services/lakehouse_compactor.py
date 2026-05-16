"""Silver compaction — bronze JSONL → typed Parquet.

Reads bronze JSON Lines, deduplicates by event_id, writes Parquet to silver
partitioned by topic and date. Idempotent: a metadata sidecar tracks which
bronze keys have already been compacted so re-runs are safe.

Silver layout:

    s3://<silver-bucket>/
        topic=<topic>/
            date=YYYY-MM-DD/
                part-<utc-iso>-<n-rows>.parquet
        _manifest/
            processed_keys.json   (set of bronze keys we've already compacted)

Runs as a scheduled task — wake every COMPACTION_INTERVAL_S seconds.
"""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import os
import signal
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import aioboto3
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from events.topics import Topics
from services.shared.config import get_settings
from services.shared.heartbeat import HeartbeatEmitter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COMPACTION_INTERVAL_S = int(os.environ.get("LAKEHOUSE_COMPACTION_INTERVAL_S", "120"))
MANIFEST_KEY = "_manifest/processed_keys.json"


class SilverCompactor:
    def __init__(self):
        self.settings = get_settings()
        self.bronze = self.settings.lakehouse_bronze_bucket
        self.silver = self.settings.lakehouse_silver_bucket
        self.region = self.settings.lakehouse_s3_region
        if not (self.bronze and self.silver):
            raise RuntimeError("LAKEHOUSE_BRONZE_BUCKET and LAKEHOUSE_SILVER_BUCKET must be configured")
        self.session = aioboto3.Session()
        self.heartbeat = HeartbeatEmitter("lakehouse-compactor", extra={
            "bronze": self.bronze, "silver": self.silver, "interval_s": COMPACTION_INTERVAL_S,
        })
        self._stop = asyncio.Event()
        self._files_in = 0
        self._rows_in = 0
        self._files_out = 0
        self._rows_out = 0
        self._bytes_out = 0

    async def start(self):
        await self.heartbeat.start()
        logger.info(
            "SilverCompactor started — bronze=s3://%s silver=s3://%s region=%s interval=%ds",
            self.bronze, self.silver, self.region, COMPACTION_INTERVAL_S,
        )
        # Run one immediate pass at startup, then loop on the interval.
        try:
            await self._compact_once()
        except Exception:
            logger.exception("Initial compaction failed")
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=COMPACTION_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            try:
                await self._compact_once()
            except Exception:
                logger.exception("Compaction pass failed")
            self.heartbeat.extra.update({
                "bronze_files_processed": self._files_in,
                "silver_files_written": self._files_out,
                "rows_in": self._rows_in,
                "rows_out": self._rows_out,
                "bytes_written": self._bytes_out,
            })

    async def stop(self):
        self._stop.set()
        await self.heartbeat.stop()

    async def _load_manifest(self, s3) -> set[str]:
        try:
            obj = await s3.get_object(Bucket=self.silver, Key=MANIFEST_KEY)
            body = await obj["Body"].read()
            data = json.loads(body)
            return set(data.get("processed_keys", []))
        except Exception:
            return set()

    async def _save_manifest(self, s3, keys: set[str]) -> None:
        await s3.put_object(
            Bucket=self.silver,
            Key=MANIFEST_KEY,
            Body=json.dumps({
                "processed_keys": sorted(keys),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).encode("utf-8"),
            ContentType="application/json",
        )

    async def _compact_once(self):
        async with self.session.client("s3", region_name=self.region) as s3:
            processed = await self._load_manifest(s3)

            # List all bronze objects across all topics.
            new_keys_by_partition: dict[tuple[str, str], list[str]] = defaultdict(list)
            paginator = s3.get_paginator("list_objects_v2")
            async for page in paginator.paginate(Bucket=self.bronze):
                for obj in page.get("Contents", []) or []:
                    key = obj["Key"]
                    if not key.endswith(".jsonl.gz"):
                        continue
                    if key in processed:
                        continue
                    # Key shape: topic=…/date=…/hour=…/events_*.jsonl.gz
                    parts = key.split("/")
                    if len(parts) < 4:
                        continue
                    topic = parts[0].split("=", 1)[1] if "=" in parts[0] else parts[0]
                    date = parts[1].split("=", 1)[1] if "=" in parts[1] else parts[1]
                    new_keys_by_partition[(topic, date)].append(key)

            if not new_keys_by_partition:
                logger.info("No new bronze objects to compact")
                return

            for (topic, date), keys in new_keys_by_partition.items():
                rows: list[dict] = []
                ids_seen: set[str] = set()
                for k in keys:
                    obj = await s3.get_object(Bucket=self.bronze, Key=k)
                    body = await obj["Body"].read()
                    self._files_in += 1
                    text = gzip.decompress(body).decode("utf-8")
                    for line in text.splitlines():
                        if not line.strip():
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        eid = rec.get("event_id")
                        if eid and eid in ids_seen:
                            continue
                        if eid:
                            ids_seen.add(eid)
                        rows.append(rec)
                        self._rows_in += 1

                if not rows:
                    processed.update(keys)
                    continue

                # Normalize for Parquet: flatten and stringify rich payload.
                normalized = [
                    {
                        "event_id": r.get("event_id"),
                        "correlation_id": r.get("correlation_id"),
                        "topic": r.get("_topic", topic),
                        "customer_id": r.get("customer_id"),
                        "account_id": r.get("account_id"),
                        "workflow_id": r.get("workflow_id"),
                        "event_type": r.get("event_type") or r.get("decision_type") or "",
                        "channel": r.get("channel"),
                        "direction": r.get("direction"),
                        "intent": r.get("intent"),
                        "strategy_version": r.get("strategy_version"),
                        "policy_name": r.get("policy_name"),
                        "agent_type": r.get("agent_type"),
                        "confidence": _safe_float(r.get("confidence")),
                        "escalated": r.get("escalated"),
                        "source_service": r.get("source_service"),
                        "occurred_at": _parse_ts(r.get("occurred_at")),
                        "ingested_at": _parse_ts(r.get("_ingested_at")),
                        "payload_json": json.dumps(
                            {k: v for k, v in r.items()
                             if k not in {"event_id", "correlation_id", "_topic", "_ingested_at"}},
                            default=str,
                        ),
                    }
                    for r in rows
                ]

                # Build the table with explicit schema (so empty columns survive).
                schema = pa.schema([
                    ("event_id", pa.string()),
                    ("correlation_id", pa.string()),
                    ("topic", pa.string()),
                    ("customer_id", pa.string()),
                    ("account_id", pa.string()),
                    ("workflow_id", pa.string()),
                    ("event_type", pa.string()),
                    ("channel", pa.string()),
                    ("direction", pa.string()),
                    ("intent", pa.string()),
                    ("strategy_version", pa.string()),
                    ("policy_name", pa.string()),
                    ("agent_type", pa.string()),
                    ("confidence", pa.float64()),
                    ("escalated", pa.bool_()),
                    ("source_service", pa.string()),
                    ("occurred_at", pa.timestamp("us", tz="UTC")),
                    ("ingested_at", pa.timestamp("us", tz="UTC")),
                    ("payload_json", pa.string()),
                ])
                table = pa.Table.from_pylist(normalized, schema=schema)

                # Write Parquet to memory then upload.
                buf = io.BytesIO()
                pq.write_table(table, buf, compression="snappy")
                body = buf.getvalue()

                flush_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                silver_key = f"topic={topic}/date={date}/part-{flush_ts}-{len(rows)}.parquet"
                await s3.put_object(
                    Bucket=self.silver,
                    Key=silver_key,
                    Body=body,
                    ContentType="application/octet-stream",
                    Metadata={
                        "topic": topic, "date": date,
                        "rows": str(len(rows)), "compacted_at": flush_ts,
                    },
                )
                self._files_out += 1
                self._rows_out += len(rows)
                self._bytes_out += len(body)
                logger.info(
                    "Compacted silver: s3://%s/%s (%d rows, %d bytes) from %d bronze files",
                    self.silver, silver_key, len(rows), len(body), len(keys),
                )
                processed.update(keys)

            await self._save_manifest(s3, processed)


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_ts(v) -> datetime | None:
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


async def main():
    compactor = SilverCompactor()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(compactor.stop()))
    try:
        await compactor.start()
    except KeyboardInterrupt:
        await compactor.stop()


if __name__ == "__main__":
    asyncio.run(main())
