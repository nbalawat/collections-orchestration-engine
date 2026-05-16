-- v0.5: Champion/challenger strategy framework + customer-level assignment.

CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_version    VARCHAR(32) PRIMARY KEY,
    role                VARCHAR(16) NOT NULL CHECK (role IN ('champion', 'challenger', 'retired')),
    description         TEXT,
    allocation_pct      NUMERIC(5,2) NOT NULL DEFAULT 0,  -- percentage of new journeys
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at        TIMESTAMPTZ,
    retired_at          TIMESTAMPTZ,
    notes               TEXT
);

INSERT INTO strategy_versions (strategy_version, role, description, allocation_pct, activated_at)
VALUES
  ('v1.0.0', 'champion',   'Baseline collections strategy — segmentation by DPD and risk, standard treatment paths.', 90.00, NOW() - INTERVAL '90 days'),
  ('v1.1.0', 'challenger', 'Higher-frequency early outreach for risk-tier 700+ customers, settlement floor 50% (vs 55%).', 10.00, NOW() - INTERVAL '14 days')
ON CONFLICT (strategy_version) DO NOTHING;

CREATE TABLE IF NOT EXISTS customer_strategy_assignments (
    customer_id         VARCHAR(32) PRIMARY KEY,
    strategy_version    VARCHAR(32) NOT NULL REFERENCES strategy_versions(strategy_version),
    assigned_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assignment_method   VARCHAR(24) NOT NULL DEFAULT 'random_allocation'
);
CREATE INDEX IF NOT EXISTS ix_assignments_version ON customer_strategy_assignments(strategy_version);
