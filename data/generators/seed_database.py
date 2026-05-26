"""Load generated seed data into PostgreSQL."""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from pathlib import Path

import asyncpg

from services.shared.config import get_settings


SEED_DIR = Path("data/seed")


def _date(val: str | None) -> date | None:
    if not val:
        return None
    return date.fromisoformat(val)


def _ts(val: str | None) -> datetime | None:
    if not val:
        return None
    return datetime.fromisoformat(val)


def _decimal(val) -> float | None:
    if val is None:
        return None
    return float(val)


async def seed():
    conn = await asyncpg.connect(get_settings().postgres_dsn_sync)

    try:
        # Clear existing data (order matters for FK constraints)
        for table in [
            "quality_reviews", "ai_reasoning_traces", "strategy_audit_log",
            "dashboard_metrics", "customer_events", "promises_to_pay",
            "contact_history", "payment_history", "compliance_flags",
            "accounts", "customer_profiles",
        ]:
            await conn.execute(f"TRUNCATE {table} CASCADE")
        print("Cleared existing data")

        # Load customers
        with open(SEED_DIR / "customers.json") as f:
            customers = json.load(f)

        for c in customers:
            await conn.execute("""
                INSERT INTO customer_profiles (
                    customer_id, first_name, last_name, date_of_birth, ssn_last4,
                    email, phone_primary, phone_secondary,
                    address_line1, address_city, address_state, address_zip,
                    timezone, preferred_language, preferred_channel,
                    employer, annual_income, relationship_start, relationship_value,
                    risk_score, behavioral_score, segment
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
            """,
                c["customer_id"], c["first_name"], c["last_name"],
                _date(c["date_of_birth"]), c["ssn_last4"],
                c["email"], c["phone_primary"], c["phone_secondary"],
                c["address_line1"], c["address_city"], c["address_state"], c["address_zip"],
                c["timezone"], c["preferred_language"], c["preferred_channel"],
                c["employer"], _decimal(c["annual_income"]),
                _date(c["relationship_start"]), c["relationship_value"],
                c["risk_score"], c["behavioral_score"], c["segment"],
            )
        print(f"  Loaded {len(customers)} customers")

        # Load accounts
        with open(SEED_DIR / "accounts.json") as f:
            accounts_data = json.load(f)

        for a in accounts_data:
            await conn.execute("""
                INSERT INTO accounts (
                    account_id, customer_id, product_type, original_amount, current_balance,
                    minimum_payment, interest_rate, origination_date, maturity_date,
                    days_past_due, delinquency_stage, last_payment_date, last_payment_amount,
                    total_past_due, status
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
            """,
                a["account_id"], a["customer_id"], a["product_type"],
                _decimal(a["original_amount"]), _decimal(a["current_balance"]),
                _decimal(a["minimum_payment"]), _decimal(a["interest_rate"]),
                _date(a["origination_date"]), _date(a["maturity_date"]),
                a["days_past_due"], a["delinquency_stage"],
                _date(a["last_payment_date"]), _decimal(a["last_payment_amount"]),
                _decimal(a["total_past_due"]), a["status"],
            )
        print(f"  Loaded {len(accounts_data)} accounts")

        # Load payments
        with open(SEED_DIR / "payments.json") as f:
            payments = json.load(f)

        for p in payments:
            await conn.execute("""
                INSERT INTO payment_history (
                    payment_id, account_id, customer_id, amount, payment_date,
                    due_date, payment_method, status
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
                p["payment_id"], p["account_id"], p["customer_id"],
                _decimal(p["amount"]), _ts(p["payment_date"]),
                _date(p["due_date"]), p["payment_method"], p["status"],
            )
        print(f"  Loaded {len(payments)} payments")

        # Load contacts
        with open(SEED_DIR / "contacts.json") as f:
            contacts = json.load(f)

        for c in contacts:
            await conn.execute("""
                INSERT INTO contact_history (
                    contact_id, customer_id, account_id, channel, direction,
                    contact_type, outcome, agent_id, duration_seconds, notes, occurred_at
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
                c["contact_id"], c["customer_id"], c["account_id"],
                c["channel"], c["direction"], c["contact_type"],
                c["outcome"], c["agent_id"], c["duration_seconds"],
                c["notes"], _ts(c["occurred_at"]),
            )
        print(f"  Loaded {len(contacts)} contacts")

        # Load compliance flags
        with open(SEED_DIR / "compliance_flags.json") as f:
            flags = json.load(f)

        for fl in flags:
            await conn.execute("""
                INSERT INTO compliance_flags (
                    flag_id, customer_id, flag_type, reason,
                    effective_date, expiry_date, status, source
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
                fl["flag_id"], fl["customer_id"], fl["flag_type"],
                fl["reason"], _ts(fl["effective_date"]), _ts(fl["expiry_date"]),
                fl["status"], fl["source"],
            )
        print(f"  Loaded {len(flags)} compliance flags")

        # Verify
        count = await conn.fetchval("SELECT COUNT(*) FROM customer_profiles")
        print(f"\nDatabase seeded: {count} customers")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
