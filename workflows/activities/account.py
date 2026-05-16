"""Activities for querying account and customer data from backend mocks."""
from __future__ import annotations

import logging
from datetime import date

import asyncpg
from temporalio import activity

from workflows.types import AccountInfo

logger = logging.getLogger(__name__)
DB_DSN = "postgresql://collections:collections@localhost:5432/collections"


@activity.defn
async def lookup_account(customer_id: str) -> AccountInfo:
    conn = await asyncpg.connect(DB_DSN)
    try:
        row = await conn.fetchrow("""
            SELECT a.*, cp.risk_score, cp.behavioral_score, cp.relationship_value,
                   cp.relationship_start, cp.preferred_channel, cp.timezone, cp.segment
            FROM accounts a
            JOIN customer_profiles cp ON cp.customer_id = a.customer_id
            WHERE a.customer_id = $1 AND a.status = 'ACTIVE'
            ORDER BY a.days_past_due DESC
            LIMIT 1
        """, customer_id)

        if not row:
            raise activity.ApplicationError(f"No active account for {customer_id}")

        flags_rows = await conn.fetch("""
            SELECT flag_type FROM compliance_flags
            WHERE customer_id = $1 AND status = 'ACTIVE'
        """, customer_id)

        tenure_years = 0
        if row["relationship_start"]:
            rel_start = row["relationship_start"]
            if isinstance(rel_start, str):
                rel_start = date.fromisoformat(rel_start)
            tenure_years = (date.today() - rel_start).days // 365

        return AccountInfo(
            account_id=row["account_id"],
            customer_id=customer_id,
            product_type=row["product_type"],
            current_balance=float(row["current_balance"]),
            days_past_due=row["days_past_due"],
            delinquency_stage=row["delinquency_stage"],
            total_past_due=float(row["total_past_due"]),
            minimum_payment=float(row["minimum_payment"]),
            last_payment_date=row["last_payment_date"].isoformat() if row["last_payment_date"] else None,
            last_payment_amount=float(row["last_payment_amount"]) if row["last_payment_amount"] else None,
            risk_score=row["risk_score"],
            behavioral_score=row["behavioral_score"],
            relationship_value=row["relationship_value"] or "standard",
            relationship_tenure_years=tenure_years,
            prior_delinquencies=0,
            prior_cures=0,
            compliance_flags=[r["flag_type"] for r in flags_rows],
            preferred_channel=row["preferred_channel"],
            timezone=row["timezone"] or "America/New_York",
        )
    finally:
        await conn.close()
