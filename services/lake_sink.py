"""Lake Sink — Kafka → S3 bronze tier.

This is the third consumer alongside the operational projectors (Postgres + Redis).
It runs in a separate consumer group (`lake-sink-bronze`) so it doesn't compete
with the OLTP path. Events are buffered per `(topic, date, hour)` partition and
flushed as gzipped JSON Lines to S3 every N seconds or M events — whichever
comes first.

Bronze layout (Hive-style):

    s3://<bronze-bucket>/
        topic=<topic>/
            date=YYYY-MM-DD/
                hour=HH/
                    events_<flush-utc-iso>_<n-events>.jsonl.gz

This is the canonical "raw landing" — schema-on-read, immutable, replayable.
Silver compaction reads from here.
"""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import signal
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import aioboto3
from dotenv import load_dotenv

# Load .env before anything else that touches settings.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from events.topics import Topics
from services.shared.config import get_settings
from services.shared.heartbeat import HeartbeatEmitter
from services.shared.kafka_client import KafkaConsumer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


class LakeSink:
    """Buffered Kafka → S3 bronze writer."""

    def __init__(self):
        self.settings = get_settings()
        self.bucket = self.settings.lakehouse_bronze_bucket
        self.region = self.settings.lakehouse_s3_region
        self.flush_interval = self.settings.lakehouse_flush_interval_s
        self.flush_max = self.settings.lakehouse_flush_max_events
        if not self.bucket:
            raise RuntimeError("LAKEHOUSE_BRONZE_BUCKET not configured in environment")

        self.session = aioboto3.Session()
        self.consumer = KafkaConsumer(topics=Topics.ALL, group_id="lake-sink-bronze")
        self.heartbeat = HeartbeatEmitter("lake-sink", extra={
            "bucket": self.bucket, "region": self.region,
            "flush_interval_s": self.flush_interval, "flush_max_events": self.flush_max,
        })

        # Buffers keyed by (topic, YYYY-MM-DD, HH); each value is a list of dict events.
        self._buffers: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        self._last_flush_at = time.monotonic()
        self._stop = asyncio.Event()

        # Counters surfaced via heartbeat extra
        self._events_in = 0
        self._events_flushed = 0
        self._files_flushed = 0
        self._bytes_flushed = 0

    async def start(self):
        await self.heartbeat.start()
        await self.consumer.start()
        logger.info(
            "LakeSink started — bucket=s3://%s, region=%s, flush every %ds or %d events",
            self.bucket, self.region, self.flush_interval, self.flush_max,
        )
        await asyncio.gather(
            self._consume_loop(),
            self._periodic_flush_loop(),
        )

    async def _consume_loop(self):
        await self.consumer.consume(self._handle)

    async def _handle(self, topic: str, key: bytes | None, value: dict):
        # value is already a dict (orjson-decoded) thanks to KafkaConsumer.
        # Tag with the source topic in the bronze payload itself for self-describing data.
        record = {
            "_topic": topic,
            "_ingested_at": datetime.now(timezone.utc).isoformat(),
            **value,
        }
        occurred = value.get("occurred_at") or record["_ingested_at"]
        try:
            occurred_dt = datetime.fromisoformat(str(occurred).replace("Z", "+00:00"))
        except Exception:
            occurred_dt = datetime.now(timezone.utc)
        date_part = occurred_dt.strftime("%Y-%m-%d")
        hour_part = occurred_dt.strftime("%H")

        key_tuple = (topic, date_part, hour_part)
        self._buffers[key_tuple].append(record)
        self._events_in += 1
        self.heartbeat.record_event()

        # Trigger flush if any single bucket gets large.
        if len(self._buffers[key_tuple]) >= self.flush_max:
            await self._flush(only_key=key_tuple)

    async def _periodic_flush_loop(self):
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.flush_interval)
            except asyncio.TimeoutError:
                pass
            if self._buffers:
                await self._flush()
            # Update heartbeat extras
            self.heartbeat.extra.update({
                "events_in": self._events_in,
                "events_flushed": self._events_flushed,
                "files_flushed": self._files_flushed,
                "bytes_flushed": self._bytes_flushed,
                "buffered": sum(len(v) for v in self._buffers.values()),
            })

    async def _flush(self, only_key: tuple | None = None):
        if not self._buffers:
            return
        keys = [only_key] if only_key else list(self._buffers.keys())
        async with self.session.client("s3", region_name=self.region) as s3:
            for k in keys:
                records = self._buffers.pop(k, [])
                if not records:
                    continue
                topic, date_part, hour_part = k
                flush_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                obj_key = (
                    f"topic={topic}/"
                    f"date={date_part}/"
                    f"hour={hour_part}/"
                    f"events_{flush_ts}_{len(records)}.jsonl.gz"
                )

                # Gzip JSON Lines in-memory then upload.
                buf = io.BytesIO()
                with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
                    for rec in records:
                        gz.write((json.dumps(rec, default=str) + "\n").encode("utf-8"))
                body = buf.getvalue()

                try:
                    await s3.put_object(
                        Bucket=self.bucket,
                        Key=obj_key,
                        Body=body,
                        ContentType="application/x-ndjson",
                        ContentEncoding="gzip",
                        Metadata={
                            "topic": topic,
                            "date": date_part,
                            "hour": hour_part,
                            "events": str(len(records)),
                            "ingested_at": flush_ts,
                        },
                    )
                    self._events_flushed += len(records)
                    self._files_flushed += 1
                    self._bytes_flushed += len(body)
                    logger.info(
                        "Flushed bronze object: s3://%s/%s (%d events, %d bytes)",
                        self.bucket, obj_key, len(records), len(body),
                    )
                except Exception:
                    logger.exception("Failed to flush bronze object %s", obj_key)
                    # Re-add to buffer so we don't lose data.
                    self._buffers[k].extend(records)

        self._last_flush_at = time.monotonic()

    async def stop(self):
        self._stop.set()
        # Final flush
        try:
            await self._flush()
        except Exception:
            logger.exception("Final flush failed")
        await self.consumer.stop()
        await self.heartbeat.stop()


async def main():
    sink = LakeSink()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(sink.stop()))
    try:
        await sink.start()
    except KeyboardInterrupt:
        await sink.stop()


if __name__ == "__main__":
    asyncio.run(main())
