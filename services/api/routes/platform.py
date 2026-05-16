"""Platform Operations endpoints — Kafka topology, service health, end-to-end traces.

This is the tech-credibility API. Powers the Platform Operations page that proves
to a bank architect that the orchestration platform is real: live Kafka throughput,
consumer lag per partition, service heartbeats, OPA decision feed, end-to-end
traces showing every hop with timing.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka import AIOKafkaConsumer
from fastapi import APIRouter, HTTPException

from events.topics import Topics
from services.shared.config import get_settings
from services.shared.db import execute_query

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


@router.get("/services")
async def list_services():
    """Live service health from service_heartbeats. The Platform Ops page polls
    this every few seconds to render the service topology."""
    rows = await execute_query("""
        SELECT service_name, instance_id, status, throughput_per_sec,
               error_count_5m, p99_latency_ms, extra, last_seen_at,
               EXTRACT(EPOCH FROM (NOW() - last_seen_at))::int AS seconds_since_last_seen
        FROM service_heartbeats
        ORDER BY service_name
    """)
    # A service is "stale" if its heartbeat is older than 30 seconds.
    for r in rows:
        stale = int(r.get("seconds_since_last_seen") or 0) > 30
        if stale:
            r["status"] = "stale"
    return {"services": rows, "timestamp": time.time()}


_TOPIC_LAST_OFFSETS: dict[str, dict[int, int]] = {}
_TOPIC_LAST_CHECK: dict[str, float] = {}


@router.get("/kafka/topics")
async def kafka_topology():
    """Per-topic state: partition count, total messages, throughput estimate,
    and consumer-group lag. Real AdminClient queries, not synthetic."""
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
    consumer = AIOKafkaConsumer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await admin.start()
    await consumer.start()
    try:
        metadata = await admin.describe_topics(Topics.ALL)
        topics_info: list[dict] = []

        for topic_meta in metadata:
            topic_name = topic_meta["topic"]
            partitions = topic_meta.get("partitions", [])
            partition_ids = [p["partition"] for p in partitions]

            # End offsets per partition
            from aiokafka.structs import TopicPartition
            tps = [TopicPartition(topic_name, pid) for pid in partition_ids]
            try:
                end_offsets = await consumer.end_offsets(tps)
                begin_offsets = await consumer.beginning_offsets(tps)
            except Exception as exc:
                end_offsets = {}
                begin_offsets = {}
                logger.warning("Failed to fetch offsets for %s: %s", topic_name, exc)

            total_messages = sum(end_offsets.values()) - sum(begin_offsets.values())

            # Throughput estimate via offset deltas
            now = time.monotonic()
            prev_offsets = _TOPIC_LAST_OFFSETS.get(topic_name, {})
            prev_check = _TOPIC_LAST_CHECK.get(topic_name)
            curr_offsets = {pid: end_offsets.get(TopicPartition(topic_name, pid), 0) for pid in partition_ids}
            throughput_per_sec = None
            if prev_check is not None and prev_offsets:
                window = max(now - prev_check, 0.001)
                delta = sum(max(0, curr_offsets[pid] - prev_offsets.get(pid, curr_offsets[pid])) for pid in partition_ids)
                throughput_per_sec = round(delta / window, 2)
            _TOPIC_LAST_OFFSETS[topic_name] = curr_offsets
            _TOPIC_LAST_CHECK[topic_name] = now

            topics_info.append({
                "topic": topic_name,
                "partition_count": len(partition_ids),
                "total_messages": total_messages,
                "throughput_per_sec": throughput_per_sec,
                "partitions": [
                    {
                        "id": pid,
                        "leader": partitions_index(partitions, pid).get("leader"),
                        "begin_offset": begin_offsets.get(TopicPartition(topic_name, pid), 0),
                        "end_offset": end_offsets.get(TopicPartition(topic_name, pid), 0),
                    }
                    for pid in partition_ids
                ],
            })

        return {"topics": topics_info, "timestamp": time.time()}
    finally:
        await admin.close()
        await consumer.stop()


def partitions_index(partitions: list[dict], pid: int) -> dict:
    for p in partitions:
        if p["partition"] == pid:
            return p
    return {}


@router.get("/kafka/consumer-lag")
async def consumer_lag():
    """Consumer group lag per topic+partition. Critical health signal — growing lag
    means a consumer is behind."""
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap_servers)
    consumer = AIOKafkaConsumer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await admin.start()
    await consumer.start()
    try:
        group_ids = ["signal-bridge", "event-projector"]
        groups_info = []

        for group_id in group_ids:
            try:
                offsets = await admin.list_consumer_group_offsets(group_id)
            except Exception as exc:
                logger.warning("Failed to read offsets for group %s: %s", group_id, exc)
                continue

            from aiokafka.structs import TopicPartition
            committed = {tp: meta.offset for tp, meta in offsets.items()}
            if not committed:
                groups_info.append({"group_id": group_id, "partitions": []})
                continue

            end = await consumer.end_offsets(list(committed.keys()))
            partition_lag = []
            total_lag = 0
            for tp, comm in committed.items():
                end_off = end.get(tp, 0)
                lag = max(0, end_off - comm)
                total_lag += lag
                partition_lag.append({
                    "topic": tp.topic,
                    "partition": tp.partition,
                    "committed": comm,
                    "end_offset": end_off,
                    "lag": lag,
                })

            groups_info.append({
                "group_id": group_id,
                "total_lag": total_lag,
                "partitions": partition_lag,
            })

        return {"consumer_groups": groups_info, "timestamp": time.time()}
    finally:
        await admin.close()
        await consumer.stop()


@router.get("/opa/policies")
async def opa_policies():
    """List of OPA policies currently loaded — bridges the gap between Rego files
    and what's actually evaluating decisions."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{settings.opa_url}/v1/policies", timeout=5)
        if resp.status_code != 200:
            raise HTTPException(502, "OPA unreachable")
        data = resp.json().get("result", [])

    policies = [{"id": p.get("id"), "ast_size": _measure_ast(p.get("ast", {})), "raw_present": bool(p.get("raw"))} for p in data]
    return {"policies": policies, "count": len(policies)}


def _measure_ast(ast: dict) -> int:
    if not isinstance(ast, dict):
        return 0
    return len(ast.get("rules", []))


@router.get("/opa/decisions")
async def opa_recent_decisions(limit: int = 50):
    """Recent OPA decision audit log — every strategy/compliance evaluation persists
    its input + output here. Sampled for the live decision feed."""
    rows = await execute_query("""
        SELECT audit_id, customer_id, strategy_version, policy_name,
               input_context, decision, evaluated_at
        FROM strategy_audit_log
        ORDER BY evaluated_at DESC NULLS LAST
        LIMIT :limit
    """, {"limit": limit})
    return {"decisions": rows}


@router.get("/trace/{event_id}")
async def trace_event(event_id: str):
    """End-to-end trace for a single event: every hop from channel → projector,
    including downstream events emitted with the same correlation_id."""
    primary = await execute_query("""
        SELECT event_id, customer_id, event_type, event_category, channel, direction,
               source_service, payload, correlation_id, occurred_at, received_at
        FROM customer_events
        WHERE event_id = :eid
        LIMIT 1
    """, {"eid": event_id})

    if not primary:
        raise HTTPException(404, "Event not found")

    primary_event = primary[0]
    correlation_id = primary_event.get("correlation_id") or event_id

    related = await execute_query("""
        SELECT event_id, customer_id, event_type, event_category, channel, direction,
               source_service, payload, correlation_id, occurred_at, received_at
        FROM customer_events
        WHERE correlation_id = :cid OR event_id = :cid OR workflow_id = (
            SELECT workflow_id FROM customer_events WHERE event_id = :eid LIMIT 1
        )
        ORDER BY occurred_at ASC
        LIMIT 200
    """, {"cid": correlation_id, "eid": event_id})

    return {
        "event": primary_event,
        "correlation_id": correlation_id,
        "trace": related,
        "hop_count": len(related),
    }


@router.get("/health/summary")
async def platform_health():
    """One-shot summary used by the page header."""
    rows = await execute_query("SELECT COUNT(*) AS n FROM customer_events WHERE received_at > NOW() - INTERVAL '5 minutes'")
    events_5m = int(rows[0]["n"]) if rows else 0

    svc_rows = await execute_query("""
        SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE last_seen_at > NOW() - INTERVAL '30 seconds') AS healthy
        FROM service_heartbeats
    """)
    svc = svc_rows[0] if svc_rows else {}

    return {
        "events_last_5m": events_5m,
        "events_per_sec_estimate": round(events_5m / 300, 2),
        "services_healthy": int(svc.get("healthy") or 0),
        "services_total": int(svc.get("n") or 0),
        "kafka_topics": len(Topics.ALL),
    }
