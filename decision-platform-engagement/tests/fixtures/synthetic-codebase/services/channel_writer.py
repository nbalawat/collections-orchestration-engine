"""[PLANTED MOCK #5 — Medium]

Recovery estimates fabricated with magic multipliers presented as if they
came from cohort analytics. No actual data behind them.
"""
from __future__ import annotations


def estimate_recovery_paths(customer_id: str, balance: float, dpd: int) -> dict:
    # ANTIPATTERN: hardcoded multipliers dressed as data-driven estimates
    paths = {
        "standard_dunning": {
            "description": "Continue standard collections cadence",
            "estimated_recovery": balance * 0.4 if dpd > 60 else balance * 0.7,
            "timeline_days": 90,
        },
        "hardship_program": {
            "description": "Reduced payment plan",
            "estimated_recovery": balance * 0.6,  # MAGIC NUMBER
            "timeline_days": 180,
        },
        "settlement_offer": {
            "description": "Lump-sum settlement",
            "estimated_recovery": balance * 0.45,  # MAGIC NUMBER
            "timeline_days": 30,
        },
        "payment_arrangement": {
            "description": "6-12 month plan",
            "estimated_recovery": balance * 0.85,  # MAGIC NUMBER
            "timeline_days": 365,
        },
    }
    return {"customer_id": customer_id, "treatment_paths": paths}
