from __future__ import annotations

import logging

import decimal
import datetime
import uuid

import orjson
import redis.asyncio as redis


def _json_default(obj):
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    raise TypeError(f"Type is not JSON serializable: {type(obj)}")

from services.shared.config import get_settings

logger = logging.getLogger(__name__)

_redis_pool = None


async def get_redis() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        settings = get_settings()
        _redis_pool = redis.from_url(settings.redis_url, decode_responses=False)
    return _redis_pool


async def cache_set(key: str, value: dict, ttl: int = 300):
    r = await get_redis()
    await r.set(key, orjson.dumps(value, default=_json_default), ex=ttl)


async def cache_get(key: str) -> dict | None:
    r = await get_redis()
    data = await r.get(key)
    if data:
        return orjson.loads(data)
    return None


async def publish_ws_event(channel: str, event: dict):
    r = await get_redis()
    await r.publish(channel, orjson.dumps(event))
