"""Accounts reserved exclusively for scripted demo scenarios.

The traffic generator must NOT touch these customers — they should show only
the activity produced by a scenario run, so a presenter gets a clean, scripted
journey every time. Everything else in the portfolio is fair game for the
traffic generator, which keeps the platform looking alive in the background.

Keep this list in sync with the scenario defaults in
services/api/routes/scenarios.py and the customer ids used inside
services/channel_simulators/scenarios.py.
"""
from __future__ import annotations

# Named-customer scenarios (one hero customer each).
RESERVED_SCENARIO_CUSTOMERS: frozenset[str] = frozenset(
    {
        "CUST-0032",  # cross_channel  — Jane Doe
        "CUST-0095",  # bankruptcy     — Robert Chen
        "CUST-0055",  # ptp            — Maria Garcia
        "CUST-0120",  # complex_case   — David Park
        "CUST-0040",  # strategy_swap
        "CUST-0041",  # strategy_swap
        "CUST-0042",  # strategy_swap
    }
)


def is_reserved(customer_id: str) -> bool:
    return customer_id in RESERVED_SCENARIO_CUSTOMERS
