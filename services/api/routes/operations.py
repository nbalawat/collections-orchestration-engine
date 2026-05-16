"""Operations Floor endpoints — live counts of journeys, agent activity, escalations.

Powers the new Operations Floor page (the home of the app). All queries hit real
tables that the orchestration backbone populates in real time.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from services.shared.db import execute_query

router = APIRouter()


@router.get("/live-journeys")
async def live_journeys(limit: int = Query(50, ge=1, le=500)):
    """Customers with recent activity — the active portfolio right now."""
    rows = await execute_query("""
        WITH recent AS (
            SELECT customer_id, MAX(occurred_at) AS last_activity
            FROM customer_events
            WHERE occurred_at > NOW() - INTERVAL '15 minutes'
            GROUP BY customer_id
            ORDER BY MAX(occurred_at) DESC
            LIMIT :limit
        )
        SELECT
            r.customer_id,
            r.last_activity,
            cp.first_name,
            cp.last_name,
            cp.risk_score,
            a.account_id,
            a.delinquency_stage,
            a.days_past_due,
            a.current_balance,
            a.total_past_due,
            (
                SELECT event_type FROM customer_events
                WHERE customer_id = r.customer_id
                ORDER BY occurred_at DESC LIMIT 1
            ) AS last_event_type,
            (
                SELECT to_stage FROM customer_events
                WHERE customer_id = r.customer_id
                  AND event_category = 'lifecycle'
                ORDER BY occurred_at DESC LIMIT 1
            ) AS journey_stage_hint
        FROM recent r
        LEFT JOIN customer_profiles cp ON cp.customer_id = r.customer_id
        LEFT JOIN LATERAL (
            SELECT * FROM accounts WHERE customer_id = r.customer_id AND status = 'ACTIVE'
            ORDER BY days_past_due DESC LIMIT 1
        ) a ON true
        ORDER BY r.last_activity DESC
    """, {"limit": limit})
    return {"journeys": rows, "count": len(rows)}


@router.get("/channel-activity")
async def channel_activity_last_5m():
    """Per-channel event rates in the last 5 minutes — for the live activity heatmap."""
    rows = await execute_query("""
        SELECT channel, direction,
               COUNT(*) AS count_5m,
               COUNT(DISTINCT customer_id) AS unique_customers,
               COUNT(*) FILTER (WHERE occurred_at > NOW() - INTERVAL '1 minute') AS count_1m
        FROM customer_events
        WHERE occurred_at > NOW() - INTERVAL '5 minutes'
          AND channel IS NOT NULL
        GROUP BY channel, direction
        ORDER BY count_5m DESC
    """)
    return {"channels": rows}


@router.get("/agent-activity")
async def agent_activity(limit: int = Query(30, ge=1, le=200)):
    """Recent AI agent actions — the agent workbench on the Operations Floor."""
    rows = await execute_query("""
        SELECT
            aa.action_id, aa.agent_type, aa.customer_id, aa.action_type,
            aa.confidence, aa.rationale, aa.status, aa.created_at,
            cp.first_name, cp.last_name
        FROM agent_actions aa
        LEFT JOIN customer_profiles cp ON cp.customer_id = aa.customer_id
        ORDER BY aa.created_at DESC
        LIMIT :limit
    """, {"limit": limit})
    return {"actions": rows}


@router.get("/agent-activity/summary")
async def agent_activity_summary():
    """Per-agent counts + average confidence over the last 24 hours."""
    rows = await execute_query("""
        SELECT
            agent_type,
            COUNT(*) AS actions_24h,
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '5 minutes') AS actions_5m,
            COUNT(*) FILTER (WHERE status = 'escalated') AS escalations_24h,
            AVG(confidence)::numeric(4,3) AS avg_confidence
        FROM agent_actions
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY agent_type
        ORDER BY actions_24h DESC
    """)
    return {"agents": rows}


@router.get("/escalation-queue")
async def escalation_queue(limit: int = Query(30, ge=1, le=200)):
    """Pending human escalations, ordered by urgency + SLA."""
    rows = await execute_query("""
        SELECT
            he.escalation_id, he.customer_id, he.reason, he.urgency,
            he.specialist_type, he.status, he.sla_due_at,
            he.created_at, he.source_agent,
            cp.first_name, cp.last_name,
            EXTRACT(EPOCH FROM (he.sla_due_at - NOW()))::int AS seconds_until_sla
        FROM human_escalations he
        LEFT JOIN customer_profiles cp ON cp.customer_id = he.customer_id
        WHERE he.status = 'queued'
        ORDER BY
            CASE he.urgency
                WHEN 'immediate' THEN 1
                WHEN 'high' THEN 2
                WHEN 'normal' THEN 3
                ELSE 4
            END,
            he.sla_due_at ASC
        LIMIT :limit
    """, {"limit": limit})
    return {"escalations": rows}


@router.get("/compliance-blocks")
async def recent_compliance_blocks(limit: int = Query(30, ge=1, le=200)):
    """Most recent compliance-blocked actions — the live enforcement feed."""
    rows = await execute_query("""
        SELECT
            event_id, customer_id, payload, occurred_at,
            payload->>'action_blocked' AS action_blocked,
            payload->>'rule_name' AS rule_name,
            payload->>'check_type' AS check_type,
            payload->>'reason' AS reason
        FROM customer_events
        WHERE event_category = 'compliance'
          AND (payload->>'passed')::boolean = false
        ORDER BY occurred_at DESC
        LIMIT :limit
    """, {"limit": limit})
    return {"blocks": rows}


@router.get("/portfolio-kpis")
async def portfolio_kpis():
    """Real risk-management KPIs: cure rate, roll rate, strategy effectiveness.
    Reads only from real Postgres data — no synthesized numbers."""
    # Cure rate: % of customers with payments large enough to cure in last 30 days
    cure = await execute_query("""
        WITH past_due_30d AS (
            SELECT DISTINCT a.customer_id
            FROM accounts a
            WHERE a.days_past_due > 0 AND a.status = 'ACTIVE'
        ),
        cured_30d AS (
            SELECT DISTINCT customer_id
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%->CURED'
              AND occurred_at > NOW() - INTERVAL '30 days'
        )
        SELECT
            (SELECT COUNT(*) FROM past_due_30d) AS at_risk,
            (SELECT COUNT(*) FROM cured_30d) AS cured,
            CASE WHEN (SELECT COUNT(*) FROM past_due_30d) > 0
                 THEN ROUND((SELECT COUNT(*)::numeric FROM cured_30d) /
                            (SELECT COUNT(*)::numeric FROM past_due_30d) * 100, 2)
                 ELSE NULL END AS cure_rate_pct
    """)

    # Roll-rate matrix: stage transitions in last 30 days
    rolls = await execute_query("""
        SELECT
            SUBSTRING(event_type FROM 'stage_change:([A-Z_]+)->') AS from_stage,
            SUBSTRING(event_type FROM '->([A-Z_]+)$') AS to_stage,
            COUNT(*) AS transitions
        FROM customer_events
        WHERE event_type LIKE 'stage_change:%->%'
          AND occurred_at > NOW() - INTERVAL '30 days'
        GROUP BY from_stage, to_stage
        ORDER BY transitions DESC
        LIMIT 30
    """)

    # Strategy-version comparison: actions taken + escalation rate per version
    strategy_perf = await execute_query("""
        WITH per_customer AS (
            SELECT csa.customer_id, csa.strategy_version
            FROM customer_strategy_assignments csa
        ),
        per_version AS (
            SELECT pc.strategy_version,
                   COUNT(DISTINCT pc.customer_id) AS customers,
                   COUNT(aa.action_id) FILTER (WHERE aa.created_at > NOW() - INTERVAL '7 days') AS actions_7d,
                   COUNT(aa.action_id) FILTER (WHERE aa.status = 'escalated'
                                                AND aa.created_at > NOW() - INTERVAL '7 days') AS escalations_7d,
                   AVG(aa.confidence)::numeric(4,3) AS avg_confidence
            FROM per_customer pc
            LEFT JOIN agent_actions aa ON aa.customer_id = pc.customer_id
            GROUP BY pc.strategy_version
        ),
        cures_per_version AS (
            SELECT pc.strategy_version,
                   COUNT(DISTINCT ce.customer_id) AS cured_7d
            FROM per_customer pc
            JOIN customer_events ce ON ce.customer_id = pc.customer_id
            WHERE ce.event_type LIKE 'stage_change:%->CURED'
              AND ce.occurred_at > NOW() - INTERVAL '7 days'
            GROUP BY pc.strategy_version
        )
        SELECT pv.strategy_version, sv.role, sv.description,
               pv.customers, pv.actions_7d, pv.escalations_7d, pv.avg_confidence,
               COALESCE(cv.cured_7d, 0) AS cured_7d,
               CASE WHEN pv.customers > 0
                    THEN ROUND(COALESCE(cv.cured_7d, 0)::numeric / pv.customers::numeric * 100, 2)
                    ELSE NULL END AS cure_rate_7d_pct
        FROM per_version pv
        LEFT JOIN strategy_versions sv ON sv.strategy_version = pv.strategy_version
        LEFT JOIN cures_per_version cv ON cv.strategy_version = pv.strategy_version
        ORDER BY sv.role
    """)

    # Recovery: payments received in last 30 days vs total past due 30 days ago
    recovery = await execute_query("""
        SELECT
            COALESCE(SUM(ph.amount), 0)::numeric AS payments_30d,
            COUNT(DISTINCT ph.customer_id) AS paying_customers
        FROM payment_history ph
        WHERE ph.payment_date > NOW() - INTERVAL '30 days'
          AND UPPER(ph.status) = 'COMPLETED'
    """)

    # PTP performance: kept vs broken vs pending
    ptp = await execute_query("""
        SELECT status, COUNT(*) AS n
        FROM promises_to_pay
        WHERE created_at > NOW() - INTERVAL '30 days'
        GROUP BY status
    """)

    # Compliance enforcement rate
    enforcement = await execute_query("""
        WITH agg AS (
            SELECT
                COUNT(*) FILTER (WHERE (payload->>'passed')::boolean = true) AS allowed,
                COUNT(*) FILTER (WHERE (payload->>'passed')::boolean = false) AS blocked
            FROM customer_events
            WHERE event_category = 'compliance'
              AND occurred_at > NOW() - INTERVAL '24 hours'
        )
        SELECT allowed, blocked,
               CASE WHEN (allowed + blocked) > 0
                    THEN ROUND(blocked::numeric / (allowed + blocked)::numeric * 100, 2)
                    ELSE NULL END AS block_rate_pct
        FROM agg
    """)

    return {
        "cure": cure[0] if cure else {},
        "roll_matrix": rolls,
        "strategy_performance": strategy_perf,
        "recovery_30d": recovery[0] if recovery else {},
        "ptp_30d": ptp,
        "enforcement_24h": enforcement[0] if enforcement else {},
    }


@router.get("/portfolio-pulse")
async def portfolio_pulse():
    """One-call summary for the Operations Floor header."""
    pulse = await execute_query("""
        SELECT
            (SELECT COUNT(DISTINCT customer_id) FROM customer_events
             WHERE occurred_at > NOW() - INTERVAL '5 minutes') AS active_journeys,
            (SELECT COUNT(*) FROM customer_events
             WHERE occurred_at > NOW() - INTERVAL '1 minute') AS events_last_minute,
            (SELECT COUNT(*) FROM agent_actions
             WHERE created_at > NOW() - INTERVAL '5 minutes') AS agent_actions_5m,
            (SELECT COUNT(*) FROM human_escalations
             WHERE status = 'queued') AS pending_escalations,
            (SELECT COUNT(*) FROM customer_events
             WHERE event_category = 'compliance'
               AND (payload->>'passed')::boolean = false
               AND occurred_at > NOW() - INTERVAL '1 hour') AS compliance_blocks_1h,
            (SELECT COUNT(*) FROM customer_events
             WHERE event_type LIKE 'stage_change:%'
               AND occurred_at > NOW() - INTERVAL '1 hour') AS stage_transitions_1h
    """)
    return pulse[0] if pulse else {}
