"""Strategy version allocator — pins each customer to one version stably.

On first call for a customer, allocates by weighted random over
strategy_versions.allocation_pct. Persists the assignment so subsequent
calls return the same version. Lift, attribution, and cohort comparison
all depend on this stability.
"""
from __future__ import annotations

import random
import asyncpg

DB_DSN = "postgresql://USER:PASS@HOST:5432/DB"  # adapt to your stack


async def resolve_strategy_version(customer_id: str) -> str:
    """Return the strategy_version for this customer, creating an assignment
    on first call. Falls back to 'v1.0.0' if no active versions exist."""
    conn = await asyncpg.connect(DB_DSN)
    try:
        existing = await conn.fetchrow(
            "SELECT strategy_version FROM customer_strategy_assignments WHERE customer_id = $1",
            customer_id,
        )
        if existing:
            return existing["strategy_version"]

        versions = await conn.fetch("""
            SELECT strategy_version, allocation_pct
            FROM strategy_versions
            WHERE role IN ('champion', 'challenger') AND retired_at IS NULL
            ORDER BY allocation_pct DESC
        """)
        if not versions:
            return "v1.0.0"

        total = sum(float(v["allocation_pct"] or 0) for v in versions) or 1.0
        roll = random.random() * total
        cum = 0.0
        chosen = versions[0]["strategy_version"]
        for v in versions:
            cum += float(v["allocation_pct"] or 0)
            if roll <= cum:
                chosen = v["strategy_version"]
                break

        try:
            await conn.execute("""
                INSERT INTO customer_strategy_assignments (customer_id, strategy_version)
                VALUES ($1, $2)
                ON CONFLICT (customer_id) DO NOTHING
            """, customer_id, chosen)
        except Exception:
            pass

        return chosen
    finally:
        await conn.close()
