"""Two-proportion z-test — the statistical test you need for champion vs challenger.

Returns lift, 95% CI on the difference, p-value, z-score, verdict, and required
sample size to detect a 5% lift at 80% power. Pure-Python, no scipy required.
"""
from __future__ import annotations

import math


def two_proportion_z(
    *,
    champion_n: int,
    champion_conversions: int,
    challenger_n: int,
    challenger_conversions: int,
    metric_name: str = "conversion",
) -> dict:
    if champion_n == 0 or challenger_n == 0:
        return {
            "metric": metric_name,
            "champion": {"n": champion_n, "conversions": champion_conversions, "rate": None},
            "challenger": {"n": challenger_n, "conversions": challenger_conversions, "rate": None},
            "lift_pct": None, "p_value": None, "significant_95": False,
            "verdict": "insufficient_data",
        }

    p1 = champion_conversions / champion_n
    p2 = challenger_conversions / challenger_n
    pooled = (champion_conversions + challenger_conversions) / (champion_n + challenger_n)
    se = math.sqrt(pooled * (1 - pooled) * (1 / champion_n + 1 / challenger_n))
    z = (p2 - p1) / se if se > 0 else 0.0
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    lift = (p2 - p1) / p1 * 100 if p1 > 0 else None
    diff = p2 - p1
    ci_half = 1.96 * math.sqrt(p1 * (1 - p1) / champion_n + p2 * (1 - p2) / challenger_n)

    required_n = None
    if p1 > 0:
        p2_target = p1 * 1.05
        avg = (p1 + p2_target) / 2
        se_test = math.sqrt(2 * avg * (1 - avg))
        se_alt = math.sqrt(p1 * (1 - p1) + p2_target * (1 - p2_target))
        if p2_target > p1:
            required_n = math.ceil(((1.96 * se_test + 0.84 * se_alt) ** 2) / ((p2_target - p1) ** 2))

    if p_value < 0.05 and lift is not None and lift > 0:
        verdict = "challenger_wins"
    elif p_value < 0.05 and lift is not None and lift < 0:
        verdict = "champion_wins"
    else:
        verdict = "no_difference"

    return {
        "metric": metric_name,
        "champion": {"n": champion_n, "conversions": champion_conversions, "rate": round(p1, 4)},
        "challenger": {"n": challenger_n, "conversions": challenger_conversions, "rate": round(p2, 4)},
        "absolute_difference": round(diff, 4),
        "difference_95_ci": [round(diff - ci_half, 4), round(diff + ci_half, 4)],
        "lift_pct": round(lift, 2) if lift is not None else None,
        "z_score": round(z, 3),
        "p_value": round(p_value, 4),
        "significant_95": bool(p_value < 0.05),
        "verdict": verdict,
        "required_n_per_arm_for_5pct_lift_80pct_power": required_n,
    }


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
