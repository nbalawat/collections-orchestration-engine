"""Service heartbeats — every service emits one every ~5 seconds.

Reads/writes via asyncpg to the service_heartbeats table. The Platform Operations
page reads this table to render service health + throughput.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from collections import deque

import asyncpg

from services.shared.config import get_settings

logger = logging.getLogger(__name__)
HEARTBEAT_INTERVAL_S = float(os.environ.get("HEARTBEAT_INTERVAL_S", "5"))


class HeartbeatEmitter:
    """Tracks per-process throughput + latency, emits a heartbeat row every N seconds.

    Usage:
        hb = HeartbeatEmitter("signal-bridge")
        await hb.start()
        ...
        hb.record_event(latency_ms=42)   # call after each unit of work
        hb.record_error()                # call on exception
        ...
        await hb.stop()
    """

    def __init__(self, service_name: str, instance_id: str | None = None, extra: dict | None = None):
        self.service_name = service_name
        self.instance_id = instance_id or f"{socket.gethostname()}-{os.getpid()}"
        self.extra = extra or {}
        self._events_since_last = 0
        self._errors_since_last = 0
        self._latencies = deque(maxlen=500)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_emit_ts = time.monotonic()

    def record_event(self, latency_ms: int | None = None) -> None:
        self._events_since_last += 1
        if latency_ms is not None:
            self._latencies.append(int(latency_ms))

    def record_error(self) -> None:
        self._errors_since_last += 1

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("Heartbeat emitter started for %s/%s", self.service_name, self.instance_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=HEARTBEAT_INTERVAL_S + 1)
            except asyncio.TimeoutError:
                self._task.cancel()
        await self._emit("stopped")

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=HEARTBEAT_INTERVAL_S)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            try:
                await self._emit("healthy")
            except Exception:
                logger.exception("Failed to emit heartbeat")

    async def _emit(self, status: str) -> None:
        now = time.monotonic()
        window = max(now - self._last_emit_ts, 0.001)
        throughput = self._events_since_last / window
        p99 = _percentile(list(self._latencies), 99) if self._latencies else None

        try:
            conn = await asyncpg.connect(get_settings().postgres_dsn_sync)
            try:
                await conn.execute("""
                    INSERT INTO service_heartbeats (service_name, instance_id, status,
                                                     throughput_per_sec, error_count_5m,
                                                     p99_latency_ms, extra, last_seen_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                    ON CONFLICT (service_name) DO UPDATE
                       SET instance_id = EXCLUDED.instance_id,
                           status = EXCLUDED.status,
                           throughput_per_sec = EXCLUDED.throughput_per_sec,
                           error_count_5m = EXCLUDED.error_count_5m,
                           p99_latency_ms = EXCLUDED.p99_latency_ms,
                           extra = EXCLUDED.extra,
                           last_seen_at = NOW()
                """,
                    self.service_name,
                    self.instance_id,
                    status,
                    round(throughput, 2),
                    self._errors_since_last,
                    p99,
                    json.dumps(self.extra),
                )
            finally:
                await conn.close()
        except Exception:
            logger.exception("Heartbeat DB write failed")

        self._events_since_last = 0
        self._errors_since_last = 0
        self._latencies.clear()
        self._last_emit_ts = now


def _percentile(values: list[int], p: int) -> int | None:
    if not values:
        return None
    sorted_v = sorted(values)
    k = max(0, min(len(sorted_v) - 1, int(round((p / 100.0) * (len(sorted_v) - 1)))))
    return sorted_v[k]
