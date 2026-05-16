-- Collections Orchestration Engine — Database Schema

-- Customer profiles (golden record)
CREATE TABLE customer_profiles (
    customer_id         VARCHAR(32) PRIMARY KEY,
    first_name          VARCHAR(64) NOT NULL,
    last_name           VARCHAR(64) NOT NULL,
    date_of_birth       DATE,
    ssn_last4           CHAR(4),
    email               VARCHAR(128),
    phone_primary       VARCHAR(20),
    phone_secondary     VARCHAR(20),
    address_line1       VARCHAR(128),
    address_city        VARCHAR(64),
    address_state       CHAR(2),
    address_zip         VARCHAR(10),
    timezone            VARCHAR(32) DEFAULT 'America/New_York',
    preferred_language  VARCHAR(8) DEFAULT 'en',
    preferred_channel   VARCHAR(16),
    employer            VARCHAR(128),
    annual_income       NUMERIC(12,2),
    relationship_start  DATE,
    relationship_value  VARCHAR(16) DEFAULT 'standard',
    risk_score          INTEGER,
    behavioral_score    INTEGER,
    segment             VARCHAR(32),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Loan/credit accounts
CREATE TABLE accounts (
    account_id          VARCHAR(32) PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL REFERENCES customer_profiles(customer_id),
    product_type        VARCHAR(32) NOT NULL,
    original_amount     NUMERIC(12,2) NOT NULL,
    current_balance     NUMERIC(12,2) NOT NULL,
    minimum_payment     NUMERIC(12,2),
    interest_rate       NUMERIC(5,3),
    origination_date    DATE,
    maturity_date       DATE,
    days_past_due       INTEGER DEFAULT 0,
    delinquency_stage   VARCHAR(32) DEFAULT 'CURRENT',
    last_payment_date   DATE,
    last_payment_amount NUMERIC(12,2),
    total_past_due      NUMERIC(12,2) DEFAULT 0,
    charge_off_date     DATE,
    status              VARCHAR(16) DEFAULT 'ACTIVE',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_accounts_customer ON accounts(customer_id);
CREATE INDEX ix_accounts_dpd ON accounts(days_past_due);
CREATE INDEX ix_accounts_stage ON accounts(delinquency_stage);

-- Payment history
CREATE TABLE payment_history (
    payment_id          VARCHAR(32) PRIMARY KEY,
    account_id          VARCHAR(32) NOT NULL REFERENCES accounts(account_id),
    customer_id         VARCHAR(32) NOT NULL REFERENCES customer_profiles(customer_id),
    amount              NUMERIC(12,2) NOT NULL,
    payment_date        TIMESTAMPTZ NOT NULL,
    due_date            DATE,
    payment_method      VARCHAR(32),
    status              VARCHAR(16) DEFAULT 'COMPLETED',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_payments_account ON payment_history(account_id, payment_date DESC);

-- Contact / interaction history
CREATE TABLE contact_history (
    contact_id          VARCHAR(32) PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL REFERENCES customer_profiles(customer_id),
    account_id          VARCHAR(32) REFERENCES accounts(account_id),
    channel             VARCHAR(16) NOT NULL,
    direction           VARCHAR(16) NOT NULL,
    contact_type        VARCHAR(32),
    outcome             VARCHAR(32),
    agent_id            VARCHAR(32),
    duration_seconds    INTEGER,
    notes               TEXT,
    occurred_at         TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_contacts_customer ON contact_history(customer_id, occurred_at DESC);

-- Compliance flags (active suppressions)
CREATE TABLE compliance_flags (
    flag_id             VARCHAR(32) PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL REFERENCES customer_profiles(customer_id),
    flag_type           VARCHAR(32) NOT NULL,
    reason              TEXT,
    effective_date      TIMESTAMPTZ NOT NULL,
    expiry_date         TIMESTAMPTZ,
    status              VARCHAR(16) DEFAULT 'ACTIVE',
    source              VARCHAR(64),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_compliance_customer ON compliance_flags(customer_id, status);
CREATE INDEX ix_compliance_type ON compliance_flags(flag_type, status);

-- Promises to pay
CREATE TABLE promises_to_pay (
    ptp_id              VARCHAR(32) PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL REFERENCES customer_profiles(customer_id),
    account_id          VARCHAR(32) NOT NULL REFERENCES accounts(account_id),
    promised_amount     NUMERIC(12,2) NOT NULL,
    promised_date       DATE NOT NULL,
    channel             VARCHAR(16),
    captured_by         VARCHAR(32),
    status              VARCHAR(16) DEFAULT 'PENDING',
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_ptp_customer ON promises_to_pay(customer_id, status);
CREATE INDEX ix_ptp_date ON promises_to_pay(promised_date, status);

-- Event store (all events projected from Kafka)
CREATE TABLE customer_events (
    event_id            UUID PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL,
    account_id          VARCHAR(32),
    workflow_id         VARCHAR(128),
    channel             VARCHAR(16),
    direction           VARCHAR(16),
    event_type          VARCHAR(64) NOT NULL,
    event_category      VARCHAR(32) NOT NULL,
    intent              VARCHAR(64),
    payload             JSONB,
    correlation_id      UUID,
    source_service      VARCHAR(64),
    occurred_at         TIMESTAMPTZ NOT NULL,
    received_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_events_customer_time ON customer_events(customer_id, occurred_at DESC);
CREATE INDEX ix_events_type ON customer_events(event_type, occurred_at DESC);
CREATE INDEX ix_events_category ON customer_events(event_category, occurred_at DESC);
CREATE INDEX ix_events_workflow ON customer_events(workflow_id);
CREATE INDEX ix_events_channel ON customer_events(channel, occurred_at DESC);

-- AI reasoning traces
CREATE TABLE ai_reasoning_traces (
    trace_id            UUID PRIMARY KEY,
    agent_type          VARCHAR(32) NOT NULL,
    customer_id         VARCHAR(32),
    workflow_id         VARCHAR(128),
    input_summary       TEXT,
    reasoning_steps     JSONB NOT NULL,
    action_taken        TEXT,
    confidence          NUMERIC(4,3),
    escalated           BOOLEAN DEFAULT FALSE,
    tokens_used         INTEGER,
    latency_ms          INTEGER,
    model               VARCHAR(64),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_ai_traces_customer ON ai_reasoning_traces(customer_id, created_at DESC);
CREATE INDEX ix_ai_traces_agent ON ai_reasoning_traces(agent_type, created_at DESC);

-- Quality review scorecards
CREATE TABLE quality_reviews (
    review_id           UUID PRIMARY KEY,
    interaction_id      VARCHAR(64) NOT NULL,
    customer_id         VARCHAR(32) NOT NULL,
    agent_type          VARCHAR(32),
    channel             VARCHAR(16),
    compliance_score    NUMERIC(5,2),
    tone_score          NUMERIC(5,2),
    accuracy_score      NUMERIC(5,2),
    completeness_score  NUMERIC(5,2),
    overall_score       NUMERIC(5,2),
    findings            JSONB,
    coaching_notes      TEXT,
    reviewed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_quality_customer ON quality_reviews(customer_id, reviewed_at DESC);

-- Strategy audit log
CREATE TABLE strategy_audit_log (
    audit_id            UUID PRIMARY KEY,
    customer_id         VARCHAR(32),
    workflow_id         VARCHAR(128),
    strategy_version    VARCHAR(32),
    policy_name         VARCHAR(64),
    input_context       JSONB,
    decision            JSONB,
    evaluated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_strategy_audit_customer ON strategy_audit_log(customer_id, evaluated_at DESC);
CREATE INDEX ix_strategy_audit_version ON strategy_audit_log(strategy_version);

-- Dashboard aggregate (materialized by event projector)
CREATE TABLE dashboard_metrics (
    metric_id           SERIAL PRIMARY KEY,
    metric_name         VARCHAR(64) NOT NULL,
    dimensions          JSONB NOT NULL DEFAULT '{}',
    value               NUMERIC(14,2) NOT NULL,
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ix_metrics_name_period ON dashboard_metrics(metric_name, period_start DESC);
