from __future__ import annotations

import datetime
import decimal
import logging
import uuid
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from services.shared.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def get_db_pool():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_dsn,
            pool_size=10,
            max_overflow=5,
            echo=False,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def get_db_session():
    get_db_pool()
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _make_serializable(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (datetime.datetime, datetime.date)):
            out[k] = v.isoformat()
        elif isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, memoryview):
            out[k] = bytes(v).decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


async def execute_query(query: str, params: dict | None = None) -> list[dict]:
    from sqlalchemy import text
    async with get_db_session() as session:
        result = await session.execute(text(query), params or {})
        return [_make_serializable(dict(row._mapping)) for row in result.fetchall()]


async def execute_insert(query: str, params: dict | None = None):
    from sqlalchemy import text
    async with get_db_session() as session:
        await session.execute(text(query), params or {})
