"""FastAPI routes — version comparison and A/B significance.

Mount with:
    app.include_router(router, prefix="/api/strategies", tags=["strategies"])
"""
from __future__ import annotations

from fastapi import APIRouter, Query

# Adapt these imports to your project
from .allocator import resolve_strategy_version
from .ab_significance import two_proportion_z

# Replace with your project's DB helper
async def execute_query(sql: str, params: dict | None = None) -> list[dict]:
    raise NotImplementedError("plug in your project's DB helper")


router = APIRouter()


@router.get("/version-comparison")
async def version_comparison():
    """Live champion vs challenger from real assignment + audit data."""
    versions = await execute_query("""
        SELECT sv.strategy_version, sv.role, sv.description, sv.allocation_pct,
               sv.activated_at, sv.retired_at,
               (SELECT COUNT(*) FROM customer_strategy_assignments csa
                WHERE csa.strategy_version = sv.strategy_version) AS assigned_customers
        FROM strategy_versions sv
        ORDER BY
            CASE sv.role WHEN 'champion' THEN 1 WHEN 'challenger' THEN 2 ELSE 3 END
    """)

    per_version_stats = await execute_query("""
        WITH per_v AS (
            SELECT csa.strategy_version, csa.customer_id
            FROM customer_strategy_assignments csa
        )
        SELECT
            per_v.strategy_version,
            COUNT(DISTINCT per_v.customer_id) AS customers,
            COUNT(DISTINCT sal.audit_id) FILTER (WHERE sal.evaluated_at > NOW() - INTERVAL '24 hours') AS evaluations_24h
        FROM per_v
        LEFT JOIN strategy_audit_log sal ON sal.customer_id = per_v.customer_id
        GROUP BY per_v.strategy_version
    """)

    stats_by_v = {r["strategy_version"]: r for r in per_version_stats}
    for v in versions:
        s = stats_by_v.get(v["strategy_version"], {})
        v["customers_24h"]    = int(s.get("customers") or 0)
        v["evaluations_24h"]  = int(s.get("evaluations_24h") or 0)

    return {"versions": versions}


@router.get("/ab-significance")
async def ab_significance(metric: str = Query("conversion")):
    """Two-proportion z-test for champion vs challenger on the given metric.

    Customize the SQL below to define what "conversion" means in your domain:
      collections → CURED transitions
      claims      → approved within SLA
      lending     → loan accepted
      fraud       → confirmed legitimate
    """
    versions = await execute_query("""
        SELECT csa.strategy_version, sv.role, COUNT(DISTINCT csa.customer_id) AS n
        FROM customer_strategy_assignments csa
        LEFT JOIN strategy_versions sv ON sv.strategy_version = csa.strategy_version
        GROUP BY csa.strategy_version, sv.role
    """)
    if len(versions) < 2:
        return {"error": "Need at least two strategy versions", "versions": versions}

    champ = next((v for v in versions if v["role"] == "champion"), versions[0])
    chal  = next((v for v in versions if v["role"] == "challenger"), versions[1])

    # CUSTOMIZE THIS — what counts as a conversion in your domain
    conversion_sql = """
        SELECT COUNT(DISTINCT csa.customer_id) AS converted
        FROM customer_strategy_assignments csa
        JOIN customer_events ce ON ce.customer_id = csa.customer_id
        WHERE csa.strategy_version = :v
          AND ce.event_type LIKE 'stage_change:%->CURED'   -- adapt to your domain
          AND ce.occurred_at > NOW() - INTERVAL '24 hours'
    """

    champ_conv = (await execute_query(conversion_sql, {"v": champ["strategy_version"]}))[0]["converted"] or 0
    chal_conv  = (await execute_query(conversion_sql, {"v": chal["strategy_version"]}))[0]["converted"] or 0

    return two_proportion_z(
        champion_n=int(champ["n"] or 0), champion_conversions=int(champ_conv),
        challenger_n=int(chal["n"] or 0), challenger_conversions=int(chal_conv),
        metric_name=metric,
    )
