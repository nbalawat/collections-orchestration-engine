"""Lake Sink — Kafka → S3 Bronze tier (gzipped JSON Lines, Hive-partitioned).

Separate consumer group from operational projectors. Buffers per
(topic, date, hour); flushes every 30s OR 500 events per partition.

Adapt:
  - TOPICS: your Kafka topic list
  - bucket / region: from your environment
"""
from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

import aioboto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BRONZE_BUCKET    = os.environ["LAKEHOUSE_BRONZE_BUCKET"]
REGION           = os.environ.get("LAKEHOUSE_S3_REGION", "us-east-1")
KAFKA_BOOTSTRAP  = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9094")
FLUSH_INTERVAL_S = int(os.environ.get("LAKEHOUSE_FLUSH_INTERVAL_S", "30"))
FLUSH_MAX_EVENTS = int(os.environ.get("LAKEHOUSE_FLUSH_MAX_EVENTS", "500"))

TOPICS = [
    # Replace with your topic list
    "channel.events.raw",
    "interactions.normalized",
    "events.decisions",
    "events.actions",
    "events.lifecycle",
    "events.compliance",
    "events.ai.reasoning",
    "events.ai.quality",
]


class LakeSink:
    def __init__(self):
        self.session = aioboto3.Session()
        self._buffers: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        self._stop = asyncio.Event()
        self._last_flush_at = time.monotonic()

    async def start(self):
        # Replace with your Kafka client (aiokafka, confluent-kafka, etc.)
        # consumer = AIOKafkaConsumer(*TOPICS, bootstrap_servers=KAFKA_BOOTSTRAP,
        #                              group_id="lake-sink-bronze",
        #                              value_deserializer=lambda v: orjson.loads(v))
        # await consumer.start()
        # await asyncio.gather(self._consume(consumer), self._periodic_flush())
        raise NotImplementedError("wire up your Kafka client here")

    async def _handle(self, topic: str, value: dict):
        record = {"_topic": topic, "_ingested_at": datetime.now(timezone.utc).isoformat(), **value}
        occurred = value.get("occurred_at") or record["_ingested_at"]
        try:
            occurred_dt = datetime.fromisoformat(str(occurred).replace("Z", "+00:00"))
        except Exception:
            occurred_dt = datetime.now(timezone.utc)
        date_part = occurred_dt.strftime("%Y-%m-%d")
        hour_part = occurred_dt.strftime("%H")

        key = (topic, date_part, hour_part)
        self._buffers[key].append(record)
        if len(self._buffers[key]) >= FLUSH_MAX_EVENTS:
            await self._flush(only_key=key)

    async def _periodic_flush(self):
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=FLUSH_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
            if self._buffers:
                await self._flush()

    async def _flush(self, only_key: tuple | None = None):
        keys = [only_key] if only_key else list(self._buffers.keys())
        async with self.session.client("s3", region_name=REGION) as s3:
            for k in keys:
                records = self._buffers.pop(k, [])
                if not records:
                    continue
                topic, date_part, hour_part = k
                flush_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                obj_key = f"topic={topic}/date={date_part}/hour={hour_part}/events_{flush_ts}_{len(records)}.jsonl.gz"

                buf = io.BytesIO()
                with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
                    for rec in records:
                        gz.write((json.dumps(rec, default=str) + "\n").encode("utf-8"))
                body = buf.getvalue()

                try:
                    await s3.put_object(
                        Bucket=BRONZE_BUCKET, Key=obj_key, Body=body,
                        ContentType="application/x-ndjson", ContentEncoding="gzip",
                        Metadata={"topic": topic, "date": date_part, "hour": hour_part, "events": str(len(records))},
                    )
                    logger.info("Flushed bronze: s3://%s/%s (%d events, %d bytes)",
                                BRONZE_BUCKET, obj_key, len(records), len(body))
                except Exception:
                    logger.exception("Bronze flush failed for %s", obj_key)
                    self._buffers[k].extend(records)


if __name__ == "__main__":
    asyncio.run(LakeSink().start())
