"""Portfolio endpoints — aggregate metrics, delinquency breakdown, dashboard data."""
from __future__ import annotations

from fastapi import APIRouter, Query

from services.shared.db import execute_query
from services.shared.redis_client import cache_get, cache_set

router = APIRouter()


def _floatify(row: dict) -> dict:
    return {k: float(v) if hasattr(v, "__float__") and not isinstance(v, (int, float)) else v for k, v in row.items()}


@router.get("/summary")
async def portfolio_summary():
    cached = await cache_get("portfolio:summary")
    if cached:
        return cached

    rows = await execute_query("""
        SELECT
            COUNT(DISTINCT customer_id) as total_customers,
            COUNT(*) as total_accounts,
            COALESCE(SUM(current_balance), 0) as total_outstanding,
            COALESCE(AVG(days_past_due), 0) as avg_dpd,
            COALESCE(SUM(total_past_due), 0) as total_past_due,
            COUNT(*) FILTER (WHERE days_past_due = 0) as current_count,
            COUNT(*) FILTER (WHERE days_past_due BETWEEN 1 AND 29) as bucket_1_29,
            COUNT(*) FILTER (WHERE days_past_due BETWEEN 30 AND 59) as bucket_30_59,
            COUNT(*) FILTER (WHERE days_past_due BETWEEN 60 AND 89) as bucket_60_89,
            COUNT(*) FILTER (WHERE days_past_due >= 90) as bucket_90_plus
        FROM accounts WHERE status = 'ACTIVE'
    """)
    result = _floatify(rows[0]) if rows else {}
    await cache_set("portfolio:summary", result, ttl=30)
    return result


@router.get("/delinquency")
async def delinquency_breakdown():
    rows = await execute_query("""
        SELECT delinquency_stage,
               COUNT(*) as count,
               SUM(current_balance)::numeric as total_balance,
               AVG(days_past_due)::numeric as avg_dpd,
               SUM(total_past_due)::numeric as total_past_due
        FROM accounts WHERE status = 'ACTIVE'
        GROUP BY delinquency_stage
        ORDER BY avg_dpd
    """)
    return {"breakdown": rows}


@router.get("/segments")
async def segment_distribution():
    rows = await execute_query("""
        SELECT
            a.delinquency_stage,
            cp.risk_score / 10 * 10 as risk_bucket,
            COUNT(*) as count,
            AVG(a.current_balance)::numeric as avg_balance,
            AVG(a.days_past_due)::numeric as avg_dpd
        FROM accounts a
        JOIN customer_profiles cp ON a.customer_id = cp.customer_id
        WHERE a.status = 'ACTIVE'
        GROUP BY a.delinquency_stage, risk_bucket
        ORDER BY a.delinquency_stage, risk_bucket
    """)
    return {"segments": rows}


@router.get("/channel-activity")
async def channel_activity(days: int = Query(30, ge=1, le=90)):
    rows = await execute_query("""
        SELECT channel, direction, event_category,
               COUNT(*) as event_count,
               COUNT(DISTINCT customer_id) as unique_customers
        FROM customer_events
        WHERE occurred_at > NOW() - MAKE_INTERVAL(days => :days)
        GROUP BY channel, direction, event_category
        ORDER BY event_count DESC
    """, {"days": days})
    return {"activity": rows, "days": days}


@router.get("/ptp-summary")
async def ptp_summary():
    rows = await execute_query("""
        SELECT status,
               COUNT(*) as count,
               SUM(promised_amount)::numeric as total_amount,
               AVG(promised_amount)::numeric as avg_amount
        FROM promises_to_pay
        GROUP BY status
    """)
    return {"ptps": rows}


@router.get("/compliance-flags")
async def compliance_flag_summary():
    rows = await execute_query("""
        SELECT flag_type, status,
               COUNT(*) as count
        FROM compliance_flags
        GROUP BY flag_type, status
        ORDER BY count DESC
    """)
    return {"flags": rows}


@router.get("/dashboard-metrics")
async def dashboard_metrics():
    summary = await portfolio_summary()
    delinquency = await delinquency_breakdown()
    ptps = await ptp_summary()
    flags = await compliance_flag_summary()

    return {
        "summary": summary,
        "delinquency": delinquency,
        "ptps": ptps,
        "compliance_flags": flags,
    }
