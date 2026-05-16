-- Champion/challenger framework: versions + per-customer assignment

CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_version    VARCHAR(32) PRIMARY KEY,
    role                VARCHAR(16) NOT NULL CHECK (role IN ('champion', 'challenger', 'retired')),
    description         TEXT,
    allocation_pct      NUMERIC(5,2) NOT NULL DEFAULT 0,  -- percentage of new customers
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at        TIMESTAMPTZ,
    retired_at          TIMESTAMPTZ,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS customer_strategy_assignments (
    customer_id         VARCHAR(64) PRIMARY KEY,
    strategy_version    VARCHAR(32) NOT NULL REFERENCES strategy_versions(strategy_version),
    assigned_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assignment_method   VARCHAR(24) NOT NULL DEFAULT 'random_allocation'
);

CREATE INDEX IF NOT EXISTS ix_assignments_version
    ON customer_strategy_assignments(strategy_version);
