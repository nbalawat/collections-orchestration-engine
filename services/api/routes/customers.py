"""Customer endpoints — profiles, accounts, 360 view, event timeline."""
from __future__ import annotations

from fastapi import APIRouter, Query

from services.shared.db import execute_query
from services.shared.redis_client import cache_get, cache_set

router = APIRouter()


@router.get("")
async def list_customers(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="Search by name or customer_id"),
    segment: str = Query("", description="Filter by delinquency_stage"),
):
    offset = (page - 1) * size
    conditions = []
    params = {"limit": size, "offset": offset}

    if search:
        conditions.append("(cp.customer_id ILIKE :search OR cp.first_name ILIKE :search OR cp.last_name ILIKE :search)")
        params["search"] = f"%{search}%"
    if segment:
        conditions.append("a.delinquency_stage = :segment")
        params["segment"] = segment

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    rows = await execute_query(f"""
        SELECT cp.customer_id, cp.first_name, cp.last_name, cp.email,
               cp.phone_primary, cp.risk_score, cp.behavioral_score,
               cp.preferred_channel, cp.timezone,
               a.account_id, a.product_type, a.current_balance,
               a.days_past_due, a.delinquency_stage, a.total_past_due,
               a.last_payment_date, a.last_payment_amount
        FROM customer_profiles cp
        LEFT JOIN accounts a ON cp.customer_id = a.customer_id AND a.status = 'ACTIVE'
        {where}
        ORDER BY a.days_past_due DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """, params)

    count_rows = await execute_query(f"""
        SELECT COUNT(DISTINCT cp.customer_id) as total
        FROM customer_profiles cp
        LEFT JOIN accounts a ON cp.customer_id = a.customer_id AND a.status = 'ACTIVE'
        {where}
    """, params)

    return {
        "customers": rows,
        "total": count_rows[0]["total"] if count_rows else 0,
        "page": page,
        "size": size,
    }


@router.get("/{customer_id}")
async def get_customer_360(customer_id: str):
    cached = await cache_get(f"c360:{customer_id}")
    if cached:
        return cached

    profile = await execute_query(
        "SELECT * FROM customer_profiles WHERE customer_id = :cid",
        {"cid": customer_id},
    )
    accounts = await execute_query(
        "SELECT * FROM accounts WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    flags = await execute_query(
        "SELECT * FROM compliance_flags WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    ptps = await execute_query(
        "SELECT * FROM promises_to_pay WHERE customer_id = :cid AND status = 'ACTIVE'",
        {"cid": customer_id},
    )
    recent_events = await execute_query("""
        SELECT event_id, event_type, event_category, channel, direction, intent,
               payload, source_service, occurred_at
        FROM customer_events WHERE customer_id = :cid
        ORDER BY occurred_at DESC LIMIT 25
    """, {"cid": customer_id})

    result = {
        "profile": profile[0] if profile else {},
        "accounts": accounts,
        "compliance_flags": flags,
        "active_ptps": ptps,
        "recent_events": recent_events,
    }

    await cache_set(f"c360:{customer_id}", result, ttl=60)
    return result


@router.get("/{customer_id}/events")
async def get_customer_events(
    customer_id: str,
    limit: int = Query(50, ge=1, le=200),
    category: str = Query("", description="Filter by event_category"),
):
    params = {"cid": customer_id, "limit": limit}
    cat_filter = ""
    if category:
        cat_filter = "AND event_category = :category"
        params["category"] = category

    rows = await execute_query(f"""
        SELECT event_id, event_type, event_category, channel, direction, intent,
               payload, source_service, occurred_at
        FROM customer_events
        WHERE customer_id = :cid {cat_filter}
        ORDER BY occurred_at DESC LIMIT :limit
    """, params)
    return {"events": rows, "customer_id": customer_id}


@router.get("/{customer_id}/payments")
async def get_payment_history(customer_id: str):
    rows = await execute_query("""
        SELECT * FROM payment_history WHERE customer_id = :cid
        ORDER BY payment_date DESC
    """, {"cid": customer_id})
    return {"payments": rows, "customer_id": customer_id}


@router.get("/{customer_id}/contacts")
async def get_contact_history(customer_id: str):
    rows = await execute_query("""
        SELECT * FROM contact_history WHERE customer_id = :cid
        ORDER BY contact_date DESC
    """, {"cid": customer_id})
    return {"contacts": rows, "customer_id": customer_id}
