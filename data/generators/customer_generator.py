"""Generate 200 synthetic customers with realistic collections profiles."""
from __future__ import annotations

import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

fake = Faker()
Faker.seed(42)
random.seed(42)

SEGMENTS = [
    {"name": "pre_delinquent", "count": 30, "dpd_range": (1, 29), "balance_range": (500, 50000)},
    {"name": "early", "count": 50, "dpd_range": (30, 59), "balance_range": (1000, 30000)},
    {"name": "mid", "count": 40, "dpd_range": (60, 89), "balance_range": (2000, 80000)},
    {"name": "late", "count": 30, "dpd_range": (90, 119), "balance_range": (5000, 150000)},
    {"name": "severe", "count": 20, "dpd_range": (120, 180), "balance_range": (3000, 100000)},
    {"name": "special", "count": 30, "dpd_range": (15, 120), "balance_range": (2000, 80000)},
]

PRODUCTS = ["credit_card", "personal_loan", "auto_loan", "mortgage", "heloc", "bnpl"]
PRODUCT_WEIGHTS = [0.35, 0.20, 0.15, 0.15, 0.10, 0.05]

RELATIONSHIP_VALUES = ["standard", "standard", "standard", "high", "high", "platinum"]

STATES = [
    "CA", "TX", "NY", "FL", "IL", "PA", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
]

SPECIAL_FLAGS = [
    "BANKRUPTCY", "BANKRUPTCY", "BANKRUPTCY",
    "CEASE_AND_DESIST", "CEASE_AND_DESIST",
    "ATTORNEY_REPRESENTED", "ATTORNEY_REPRESENTED",
    "SCRA_MILITARY", "SCRA_MILITARY", "SCRA_MILITARY",
    "FRAUD", "FRAUD",
    "DECEASED",
    "DISPUTE", "DISPUTE", "DISPUTE",
    "DISASTER", "DISASTER",
    "IDENTITY_THEFT",
    None, None, None, None, None, None, None, None, None, None, None,
]

TIMEZONES = {
    "CA": "America/Los_Angeles", "TX": "America/Chicago", "NY": "America/New_York",
    "FL": "America/New_York", "IL": "America/Chicago", "PA": "America/New_York",
    "OH": "America/New_York", "GA": "America/New_York", "NC": "America/New_York",
    "MI": "America/New_York", "NJ": "America/New_York", "VA": "America/New_York",
    "WA": "America/Los_Angeles", "AZ": "America/Phoenix", "MA": "America/New_York",
    "TN": "America/Chicago", "IN": "America/New_York", "MO": "America/Chicago",
    "MD": "America/New_York", "WI": "America/Chicago",
}


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _gen_payment_history(account_id: str, customer_id: str, product: str, dpd: int, balance: float) -> list[dict]:
    payments = []
    months_back = max(24, dpd // 30 + 12)
    monthly_pmt = balance / max(months_back, 12)

    for i in range(months_back, 0, -1):
        due_date = date.today() - timedelta(days=i * 30)
        months_delinquent = dpd // 30

        if i > months_delinquent + random.randint(0, 3):
            status = "COMPLETED"
            amount = round(monthly_pmt * random.uniform(0.95, 1.05), 2)
            pay_date = due_date + timedelta(days=random.randint(0, 5))
        elif i > months_delinquent and random.random() < 0.3:
            status = "COMPLETED"
            amount = round(monthly_pmt * random.uniform(0.5, 0.8), 2)
            pay_date = due_date + timedelta(days=random.randint(10, 25))
        else:
            status = "MISSED"
            amount = 0
            pay_date = None

        if status == "COMPLETED":
            payments.append({
                "payment_id": _uid("PAY"),
                "account_id": account_id,
                "customer_id": customer_id,
                "amount": amount,
                "payment_date": pay_date.isoformat() if pay_date else None,
                "due_date": due_date.isoformat(),
                "payment_method": random.choice(["ach", "debit_card", "check", "online"]),
                "status": status,
            })
    return payments


def _gen_contact_history(customer_id: str, account_id: str, dpd: int) -> list[dict]:
    contacts = []
    num_contacts = min(dpd // 10 + random.randint(1, 3), 20)

    for i in range(num_contacts):
        days_ago = random.randint(1, max(dpd, 7))
        channel = random.choice(["sms", "email", "voice", "dialer"])
        direction = random.choice(["outbound", "outbound", "outbound", "inbound"])
        outcomes = ["connected", "no_answer", "voicemail", "busy", "delivered", "bounced", "replied"]

        contacts.append({
            "contact_id": _uid("CON"),
            "customer_id": customer_id,
            "account_id": account_id,
            "channel": channel,
            "direction": direction,
            "contact_type": f"{channel}_{direction}",
            "outcome": random.choice(outcomes),
            "agent_id": f"AGT-{random.randint(100, 999)}" if channel == "voice" else None,
            "duration_seconds": random.randint(30, 600) if channel == "voice" else None,
            "notes": None,
            "occurred_at": (datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(8, 20))).isoformat(),
        })

    return sorted(contacts, key=lambda c: c["occurred_at"])


def generate_customers() -> dict:
    customers = []
    accounts = []
    all_payments = []
    all_contacts = []
    compliance_flags = []

    customer_idx = 0

    for seg in SEGMENTS:
        for _ in range(seg["count"]):
            customer_idx += 1
            cid = f"CUST-{customer_idx:04d}"
            state = random.choice(STATES)
            tenure_years = random.randint(1, 25)
            rel_value = random.choice(RELATIONSHIP_VALUES)
            if tenure_years > 15:
                rel_value = random.choice(["high", "platinum", "high"])

            income = round(random.uniform(25000, 200000), 2)
            risk_score = random.randint(350, 800)
            behavioral_score = random.randint(300, 850)

            if seg["name"] in ("late", "severe"):
                risk_score = min(risk_score, random.randint(350, 600))
            elif seg["name"] == "pre_delinquent":
                risk_score = max(risk_score, random.randint(550, 800))

            customer = {
                "customer_id": cid,
                "first_name": fake.first_name(),
                "last_name": fake.last_name(),
                "date_of_birth": fake.date_of_birth(minimum_age=22, maximum_age=75).isoformat(),
                "ssn_last4": f"{random.randint(1000, 9999)}",
                "email": fake.email(),
                "phone_primary": fake.numerify("###-###-####"),
                "phone_secondary": fake.numerify("###-###-####") if random.random() < 0.4 else None,
                "address_line1": fake.street_address(),
                "address_city": fake.city(),
                "address_state": state,
                "address_zip": fake.zipcode(),
                "timezone": TIMEZONES.get(state, "America/New_York"),
                "preferred_language": "en",
                "preferred_channel": random.choice(["sms", "email", "voice", None, None]),
                "employer": fake.company() if random.random() < 0.7 else None,
                "annual_income": income,
                "relationship_start": (date.today() - timedelta(days=tenure_years * 365)).isoformat(),
                "relationship_value": rel_value,
                "risk_score": risk_score,
                "behavioral_score": behavioral_score,
                "segment": seg["name"],
            }
            customers.append(customer)

            num_accounts = 1 if random.random() < 0.6 else random.randint(2, 3)
            products_chosen = random.choices(PRODUCTS, weights=PRODUCT_WEIGHTS, k=num_accounts)

            for prod in products_chosen:
                aid = _uid("ACCT")
                dpd = random.randint(*seg["dpd_range"])
                balance = round(random.uniform(*seg["balance_range"]), 2)

                if prod == "mortgage":
                    balance = round(random.uniform(50000, 500000), 2)
                elif prod == "auto_loan":
                    balance = round(random.uniform(5000, 60000), 2)
                elif prod == "bnpl":
                    balance = round(random.uniform(100, 3000), 2)

                orig_amount = round(balance * random.uniform(1.1, 2.0), 2)
                last_pmt_date = (date.today() - timedelta(days=dpd + random.randint(0, 15))).isoformat() if dpd < 120 else None
                last_pmt_amt = round(balance / 12 * random.uniform(0.8, 1.2), 2) if last_pmt_date else None

                stage_map = {
                    "pre_delinquent": "PRE_DELINQUENT",
                    "early": "EARLY",
                    "mid": "MID",
                    "late": "LATE",
                    "severe": "SEVERE",
                    "special": random.choice(["EARLY", "MID", "LATE"]),
                }

                account = {
                    "account_id": aid,
                    "customer_id": cid,
                    "product_type": prod,
                    "original_amount": orig_amount,
                    "current_balance": balance,
                    "minimum_payment": round(balance * random.uniform(0.02, 0.05), 2),
                    "interest_rate": round(random.uniform(0.039, 0.299), 3),
                    "origination_date": (date.today() - timedelta(days=tenure_years * 365 + random.randint(0, 1000))).isoformat(),
                    "maturity_date": (date.today() + timedelta(days=random.randint(365, 3650))).isoformat(),
                    "days_past_due": dpd,
                    "delinquency_stage": stage_map[seg["name"]],
                    "last_payment_date": last_pmt_date,
                    "last_payment_amount": last_pmt_amt,
                    "total_past_due": round(balance * min(dpd / 360, 0.5), 2),
                    "status": "ACTIVE",
                }
                accounts.append(account)

                all_payments.extend(_gen_payment_history(aid, cid, prod, dpd, balance))
                all_contacts.extend(_gen_contact_history(cid, aid, dpd))

            # Special population flags
            if seg["name"] == "special":
                flag_type = random.choice(SPECIAL_FLAGS)
                if flag_type:
                    compliance_flags.append({
                        "flag_id": _uid("FLG"),
                        "customer_id": cid,
                        "flag_type": flag_type,
                        "reason": f"Simulated {flag_type.lower().replace('_', ' ')} for demo",
                        "effective_date": (datetime.utcnow() - timedelta(days=random.randint(1, 90))).isoformat(),
                        "expiry_date": None,
                        "status": "ACTIVE",
                        "source": "demo_generator",
                    })

    return {
        "customers": customers,
        "accounts": accounts,
        "payments": all_payments,
        "contacts": all_contacts,
        "compliance_flags": compliance_flags,
    }


def save_seed_data(output_dir: str = "data/seed"):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    data = generate_customers()

    for key, records in data.items():
        path = out / f"{key}.json"
        with open(path, "w") as f:
            json.dump(records, f, indent=2, default=str)
        print(f"  {key}: {len(records)} records -> {path}")

    print(f"\nTotal: {sum(len(v) for v in data.values())} records generated")
    return data


if __name__ == "__main__":
    print("Generating synthetic collections data...")
    save_seed_data()
