"""[NOT MOCKED] — Genuinely queries Postgres. The audit should leave it alone."""
from __future__ import annotations

import asyncpg

DB_DSN = "postgresql://user:pass@localhost:5432/db"


async def lookup_account(customer_id: str) -> dict | None:
    conn = await asyncpg.connect(DB_DSN)
    try:
        row = await conn.fetchrow("""
            SELECT account_id, customer_id, current_balance, days_past_due
            FROM accounts
            WHERE customer_id = $1 AND status = 'ACTIVE'
            ORDER BY days_past_due DESC
            LIMIT 1
        """, customer_id)
        if row is None:
            return None
        return {
            "account_id": row["account_id"],
            "customer_id": row["customer_id"],
            "balance": float(row["current_balance"] or 0),
            "dpd": int(row["days_past_due"] or 0),
        }
    finally:
        await conn.close()
