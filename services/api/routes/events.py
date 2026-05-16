"""Event endpoints — query the event store, event timeline, and category filtering."""
from __future__ import annotations

from fastapi import APIRouter, Query

from services.shared.db import execute_query

router = APIRouter()


@router.get("")
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    category: str = Query("", description="Filter by event_category"),
    channel: str = Query("", description="Filter by channel"),
    customer_id: str = Query("", description="Filter by customer_id"),
):
    conditions = []
    params = {"limit": limit}

    if category:
        conditions.append("event_category = :category")
        params["category"] = category
    if channel:
        conditions.append("channel = :channel")
        params["channel"] = channel
    if customer_id:
        conditions.append("customer_id = :customer_id")
        params["customer_id"] = customer_id

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = await execute_query(f"""
        SELECT event_id, customer_id, account_id, workflow_id,
               channel, direction, event_type, event_category,
               intent, payload, source_service, occurred_at
        FROM customer_events
        {where}
        ORDER BY occurred_at DESC LIMIT :limit
    """, params)
    return {"events": rows}


@router.get("/stats")
async def event_stats(hours: int = Query(24, ge=1, le=168)):
    rows = await execute_query("""
        SELECT event_category,
               COUNT(*) as count,
               COUNT(DISTINCT customer_id) as unique_customers,
               MIN(occurred_at) as earliest,
               MAX(occurred_at) as latest
        FROM customer_events
        WHERE occurred_at > NOW() - MAKE_INTERVAL(hours => :hours)
        GROUP BY event_category
        ORDER BY count DESC
    """, {"hours": hours})
    return {"stats": rows, "hours": hours}


@router.get("/timeline")
async def event_timeline(
    customer_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    rows = await execute_query("""
        SELECT event_id, event_type, event_category, channel, direction,
               intent, payload, source_service, occurred_at
        FROM customer_events
        WHERE customer_id = :cid
        ORDER BY occurred_at ASC LIMIT :limit
    """, {"cid": customer_id, "limit": limit})
    return {"timeline": rows, "customer_id": customer_id}
