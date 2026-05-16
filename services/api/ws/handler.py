"""WebSocket handler — real-time event streaming via Redis pub/sub.

Supports two subscription modes:
  - /ws/events/all         → firehose of all events (for Ops Dashboard)
  - /ws/events/{customer}  → per-customer stream (for Agent Desktop)

The event projector publishes to Redis channels; this handler relays them
to connected WebSocket clients.
"""
from __future__ import annotations

import asyncio
import logging

import orjson
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.shared.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()


@router.websocket("/ws/events/all")
async def ws_all_events(ws: WebSocket):
    await ws.accept()
    r = aioredis.from_url(settings.redis_url, decode_responses=False)
    pubsub = r.pubsub()
    await pubsub.subscribe("events:all")
    logger.info("WebSocket connected: events:all")

    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                await ws.send_bytes(msg["data"])
            else:
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: events:all")
    except Exception:
        logger.exception("WebSocket error: events:all")
    finally:
        await pubsub.unsubscribe("events:all")
        await pubsub.aclose()
        await r.aclose()


@router.websocket("/ws/events/{customer_id}")
async def ws_customer_events(ws: WebSocket, customer_id: str):
    await ws.accept()
    r = aioredis.from_url(settings.redis_url, decode_responses=False)
    pubsub = r.pubsub()
    channel = f"events:{customer_id}"
    await pubsub.subscribe(channel)
    logger.info("WebSocket connected: %s", channel)

    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg["type"] == "message":
                await ws.send_bytes(msg["data"])
            else:
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", channel)
    except Exception:
        logger.exception("WebSocket error: %s", channel)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()
        await r.aclose()
