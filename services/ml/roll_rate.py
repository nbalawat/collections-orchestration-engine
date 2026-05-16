"""Roll-rate forecasting via Markov chain over stage transitions.

Builds the transition matrix M from customer_events stage_change rows:
  M[i, j] = P(stage_t+1 = j | stage_t = i)

Current portfolio state vector s is the distribution of customers across stages
right now (from accounts.delinquency_stage).

Projection:
  s(30 days)  = s · M^d30
  s(60 days)  = s · M^d60
  s(90 days)  = s · M^d90

Where d30, d60, d90 are the average number of transitions per period (computed
from the historical transition density). For a POC we use a fixed step
interpretation: one transition per "period" and treat the projections as relative.

Absorbing states (CURED, CHARGED_OFF) accumulate.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import asyncpg
import numpy as np

logger = logging.getLogger(__name__)
DB_DSN = "postgresql://collections:collections@localhost:5432/collections"

CANONICAL_STAGES = [
    "CURRENT", "PRE_DELINQUENT", "DUNNING", "PTP_ACTIVE", "PTP_BROKEN",
    "HARDSHIP_REVIEW", "SETTLEMENT_NEGOTIATION", "ARRANGEMENT_ACTIVE",
    "EARLY", "MID", "LATE", "SEVERE", "SUSPENDED", "CURED", "CHARGED_OFF",
]
STAGE_INDEX = {s: i for i, s in enumerate(CANONICAL_STAGES)}


async def build_transition_matrix() -> tuple[np.ndarray, list[str], dict]:
    """Reads stage_change events and builds an empirical transition matrix.

    Returns (matrix, stage_labels, metadata).
    """
    conn = await asyncpg.connect(DB_DSN)
    try:
        rows = await conn.fetch("""
            SELECT
                CASE
                    WHEN payload->>'from_stage' IS NULL OR payload->>'from_stage' = ''
                    THEN 'IDLE'
                    ELSE payload->>'from_stage'
                END AS from_stage,
                payload->>'to_stage' AS to_stage,
                COUNT(*) AS n
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%'
              AND payload->>'to_stage' IS NOT NULL
              AND payload->>'to_stage' != ''
            GROUP BY from_stage, to_stage
        """)
    finally:
        await conn.close()

    n = len(CANONICAL_STAGES)
    counts = np.zeros((n, n), dtype=float)
    skipped = 0
    for r in rows:
        a = r["from_stage"]
        b = r["to_stage"]
        ai = STAGE_INDEX.get(a)
        bi = STAGE_INDEX.get(b)
        if ai is None or bi is None:
            skipped += int(r["n"])
            continue
        counts[ai, bi] += float(r["n"])

    # Add row-wise smoothing so empty rows still produce a valid distribution
    # (absorbing states stay at themselves with prob 1).
    M = np.zeros_like(counts)
    for i in range(n):
        row = counts[i]
        s = row.sum()
        if s > 0:
            M[i] = row / s
        else:
            # No outgoing transitions observed → treat as absorbing in itself
            M[i, i] = 1.0

    # CURED and CHARGED_OFF are absorbing states regardless of data
    for absorbing in ("CURED", "CHARGED_OFF"):
        idx = STAGE_INDEX[absorbing]
        M[idx, :] = 0.0
        M[idx, idx] = 1.0

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "total_transitions_observed": float(counts.sum()),
        "transitions_skipped_unknown_stage": skipped,
        "non_zero_rows": int(((counts.sum(axis=1)) > 0).sum()),
    }
    return M, CANONICAL_STAGES, meta


async def current_state() -> dict[str, int]:
    """Distribution of active customers across journey stages right now.

    We prefer the latest lifecycle event ('stage_change:_->X' → X) since that's
    what the transition matrix is built from. For customers with no lifecycle
    history yet, we fall back to accounts.delinquency_stage with a mapping
    from the account-side labels (EARLY/MID/LATE/SEVERE/CURRENT) to the
    journey-side labels (DUNNING/etc).
    """
    conn = await asyncpg.connect(DB_DSN)
    try:
        # Latest journey stage per customer (from lifecycle events)
        latest = await conn.fetch("""
            SELECT DISTINCT ON (customer_id)
                customer_id, payload->>'to_stage' AS stage
            FROM customer_events
            WHERE event_type LIKE 'stage_change:%'
              AND payload->>'to_stage' IS NOT NULL
            ORDER BY customer_id, occurred_at DESC
        """)
        latest_map = {r["customer_id"]: r["stage"] for r in latest if r["stage"]}

        # Customers with active accounts but no lifecycle history yet
        no_history = await conn.fetch("""
            SELECT a.customer_id, a.delinquency_stage
            FROM accounts a
            WHERE a.status = 'ACTIVE'
              AND a.customer_id NOT IN (SELECT customer_id FROM customer_events WHERE event_type LIKE 'stage_change:%')
        """)
    finally:
        await conn.close()

    # Map account-side stage labels onto our canonical journey-stage space
    account_to_journey = {
        "CURRENT": "CURRENT", "PRE_DELINQUENT": "PRE_DELINQUENT",
        "EARLY": "EARLY", "MID": "MID", "LATE": "LATE", "SEVERE": "SEVERE",
        "PRE_CHARGE_OFF": "SEVERE", "CHARGE_OFF": "CHARGED_OFF",
    }
    out: dict[str, int] = {s: 0 for s in CANONICAL_STAGES}
    for cid, stage in latest_map.items():
        if stage in out:
            out[stage] += 1
    for r in no_history:
        mapped = account_to_journey.get(r["delinquency_stage"], r["delinquency_stage"])
        if mapped in out:
            out[mapped] += 1
    return out


def project(M: np.ndarray, state_vec: np.ndarray, steps: int) -> np.ndarray:
    """Project state vector forward `steps` transitions."""
    Mk = np.linalg.matrix_power(M, steps)
    return state_vec @ Mk


async def roll_rate_forecast() -> dict:
    """Build the matrix, capture current state, project to 30/60/90 days.

    For the POC the step counts (5/10/15) approximate "transitions per period".
    Production would calibrate this against observed transitions-per-customer-per-day.
    """
    M, labels, meta = await build_transition_matrix()
    state = await current_state()
    s = np.array([state.get(label, 0) for label in labels], dtype=float)
    total = s.sum()

    if total == 0:
        return {
            "matrix": [], "labels": labels, "current_state": state,
            "projections": {}, "meta": meta, "warning": "No active customers",
        }

    s_norm = s / total

    # Approximate step counts per period. Each Markov "step" represents one
    # observed transition; we calibrate by transitions/customer/day from history.
    transitions_per_customer = meta["total_transitions_observed"] / max(1, total)
    daily_rate = max(0.05, min(2.0, transitions_per_customer / max(1.0, 7.0)))  # rough
    step_30 = max(1, int(round(daily_rate * 30)))
    step_60 = max(1, int(round(daily_rate * 60)))
    step_90 = max(1, int(round(daily_rate * 90)))

    proj_30 = project(M, s_norm, step_30) * total
    proj_60 = project(M, s_norm, step_60) * total
    proj_90 = project(M, s_norm, step_90) * total

    def _to_dict(arr: np.ndarray) -> dict[str, float]:
        return {labels[i]: round(float(arr[i]), 2) for i in range(len(labels))}

    return {
        "matrix": [[round(float(v), 4) for v in row] for row in M],
        "labels": labels,
        "current_state": state,
        "current_total": int(total),
        "projections": {
            "30_day": _to_dict(proj_30),
            "60_day": _to_dict(proj_60),
            "90_day": _to_dict(proj_90),
        },
        "steps_per_period": {
            "30": step_30, "60": step_60, "90": step_90,
            "daily_transition_rate": round(daily_rate, 3),
        },
        "meta": meta,
    }
