---
name: champion-challenger
description: A/B testing framework for strategies, not just experiments. Customers partitioned by strategy version with random allocation by weight. Live cohort comparison from real evaluation history. Two-proportion z-test for statistical significance. Trigger when the user mentions A/B testing, champion challenger, strategy rollout, gradual deployment, statistical significance, lift testing, or new strategy launch.
metadata:
  type: pattern
  tags: [strategy, A/B, statistics, risk]
---

# Champion / challenger — A/B testing as a platform capability

## What this solves

A platform that only knows about one strategy version is a platform that can't ship new strategies safely. Build the A/B framework into the platform from day one so introducing a new strategy is a routine operation, measured rigorously, rolled out by allocation %.

This is the CRO's home turf. They recognize it from every clinical trial or ML experiment they've ever run.

## The pattern

### 1. Strategy versions table

```sql
CREATE TABLE strategy_versions (
    strategy_version    VARCHAR(32) PRIMARY KEY,
    role                VARCHAR(16) CHECK (role IN ('champion', 'challenger', 'retired')),
    description         TEXT,
    allocation_pct      NUMERIC(5,2),  -- % of new customers
    activated_at        TIMESTAMPTZ,
    retired_at          TIMESTAMPTZ,
    notes               TEXT
);
```

Seed with `v1.0.0` as champion (90% allocation) and `v1.1.0` as challenger (10%).

### 2. Customer-level assignment

```sql
CREATE TABLE customer_strategy_assignments (
    customer_id         VARCHAR(32) PRIMARY KEY,
    strategy_version    VARCHAR(32) REFERENCES strategy_versions,
    assigned_at         TIMESTAMPTZ DEFAULT NOW(),
    assignment_method   VARCHAR(24) DEFAULT 'random_allocation'
);
```

On first evaluation for a customer:
- If `customer_strategy_assignments` already has them → use that version (stable)
- Otherwise → roll a weighted random over `strategy_versions.allocation_pct` → insert assignment

### 3. Tag every evaluation with version

Pass `strategy_version` as an input to the policy engine. Persist it in `strategy_audit_log`. Now you can group everything (decisions, agent actions, escalations, cures) by version.

### 4. Live A/B dashboard

For each strategy version, compute over the last 24h:

| Metric | How |
|---|---|
| Customers assigned | `COUNT(DISTINCT customer_id) FROM customer_strategy_assignments WHERE strategy_version = ?` |
| Evaluations | `COUNT(*) FROM strategy_audit_log WHERE strategy_version = ?` (24h window) |
| AI agent actions | `COUNT(*) FROM agent_actions WHERE customer_id IN (assigned to version)` (24h window) |
| Escalations | filter to `status='escalated'` |
| Cure rate | `COUNT(*) FILTER (WHERE event_type LIKE 'stage_change:%->CURED')` over the same cohort |
| Avg AI confidence | `AVG(confidence)` from agent_actions |

### 5. Two-proportion z-test for significance

Don't claim a winner without statistical evidence. The minimal API:

```python
def two_proportion_z(champion_n, champion_conversions, challenger_n, challenger_conversions):
    p1 = champion_conversions / champion_n
    p2 = challenger_conversions / challenger_n
    pooled = (champion_conversions + challenger_conversions) / (champion_n + challenger_n)
    se = sqrt(pooled * (1 - pooled) * (1/champion_n + 1/challenger_n))
    z = (p2 - p1) / se if se > 0 else 0
    p_value = 2 * (1 - norm_cdf(abs(z)))   # two-sided
    lift = (p2 - p1) / p1 * 100 if p1 > 0 else None

    # 95% CI on the difference
    ci_half = 1.96 * sqrt(p1*(1-p1)/champion_n + p2*(1-p2)/challenger_n)
    diff_ci = [diff - ci_half, diff + ci_half]

    # Required-n per arm to detect 5% lift at 80% power
    if p1 > 0:
        p2_target = p1 * 1.05
        avg = (p1 + p2_target) / 2
        se_test = sqrt(2 * avg * (1 - avg))
        se_alt = sqrt(p1*(1-p1) + p2_target*(1-p2_target))
        required_n = ceil(((1.96*se_test + 0.84*se_alt) ** 2) / ((p2_target - p1) ** 2))

    return {
        "lift_pct": lift, "p_value": p_value, "z_score": z,
        "absolute_difference": diff, "difference_95_ci": diff_ci,
        "significant_95": p_value < 0.05,
        "required_n_per_arm_for_5pct_lift_80pct_power": required_n,
        "verdict": _verdict(lift, p_value),
    }
```

### 6. Multiple metrics

A/B testing should report at least three metrics for each pair:
- **Cure rate** — primary outcome
- **Escalation rate** — operational cost signal
- **Engagement rate** — inbound interactions (proxy for treatment quality)

A challenger that beats champion on cure but doubles escalations might not actually be better.

## The side-by-side evaluator

In addition to the cohort-level A/B comparison, build a side-by-side evaluator: pick a customer (or synthetic case), run them through both strategy versions, show the diff in policy verdicts.

This is the CRO's "show me one case" question. Make it a one-click feature.

## Rolling out a new strategy

The pattern for safely introducing `v1.2.0`:

1. Insert into `strategy_versions` with `allocation_pct = 0.0` initially
2. Promote it to `allocation_pct = 1.0` (1% of new customers)
3. Watch the live A/B dashboard for a calibration period
4. Promote to 5%, 10%, 25% as evidence accumulates
5. When p_value < 0.05 and lift is positive across all three metrics → make it champion
6. Demote old champion to `role='retired'`

## Common failure modes to avoid

- **No customer-level pinning.** If a customer can flip versions per evaluation, you can't measure anything.
- **Comparing total cures without normalizing.** Always compare *rates* (cures / customers in cohort), not raw counts.
- **Reporting lift without significance.** A 50% lift on n=10 each is noise.
- **Forgetting the carrying capacity.** A challenger that needs 10× more agent attention to achieve its lift isn't actually better.
- **Manual allocation.** Use weighted random, not "every other customer" or stratified-by-ID — both leak.

## Worked example from the reference engagement

`strategy_versions` table seeded with v1.0.0 (champion, 90%) + v1.1.0 (challenger, 10%). Customer-level assignment persisted on first evaluation. Live A/B dashboard on `/strategy` and `/risk-ml` pages showing 174 customers @ v1.0.0 vs 26 @ v1.1.0 with per-version evaluation/action/escalation/cure counts.

Two-proportion z-test exposed via `/api/risk/ab-significance?metric=cure|escalation|engagement` returning lift, 95% CI on difference, p-value, required-n for 5% lift at 80% power, and a verdict (`challenger_wins` / `champion_wins` / `no_difference` / `insufficient_data`).
