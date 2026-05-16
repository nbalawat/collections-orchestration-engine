# champion-challenger · reference code

Drop-in implementation of the A/B framework. Schema + customer-level random allocation + two-proportion z-test API.

## Files

- `schema.sql` — `strategy_versions` and `customer_strategy_assignments` tables
- `allocator.py` — resolves a customer's strategy version (creates assignment on first eval, weighted random by `allocation_pct`)
- `ab_significance.py` — two-proportion z-test with lift, 95% CI on difference, p-value, verdict, required-n for 5% lift at 80% power
- `api.py` — FastAPI routes for version-comparison and ab-significance

## How to adapt

1. Apply `schema.sql` as a migration.
2. Seed initial versions:
   ```sql
   INSERT INTO strategy_versions (strategy_version, role, description, allocation_pct, activated_at)
   VALUES ('v1.0.0', 'champion',   'Baseline strategy', 90.0, NOW()),
          ('v1.1.0', 'challenger', 'New approach',      10.0, NOW());
   ```
3. Wire `allocator.resolve_strategy_version()` into your strategy evaluation activity — call it before evaluating policy.
4. Pass `strategy_version` as an input to your policy engine; persist it in the audit log.
5. Mount the API routes from `api.py`.
6. Build a UI panel that calls `/api/strategies/version-comparison` and `/api/strategies/ab-significance?metric=…` — 5 minutes work with any framework.

## What this gives you

- Customers are partitioned by strategy version (stable assignment per customer)
- Every evaluation tagged with version → measurable cohorts
- Statistical significance reported with lift + CI + required-n
- Safe rollout via `allocation_pct` adjustment
