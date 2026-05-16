-- Initial DB foundation — apply once when the engagement starts.
-- Idempotent: safe to re-run.

-- ═══ Domain tables (replace with your domain) ═════════════════════
-- Customize for collections / claims / lending / fraud / etc.

CREATE TABLE IF NOT EXISTS customer_profiles (
    customer_id          VARCHAR(64) PRIMARY KEY,
    first_name           VARCHAR(128),
    last_name            VARCHAR(128),
    email                VARCHAR(256),
    phone                VARCHAR(32),
    timezone             VARCHAR(64) DEFAULT 'America/New_York',
    preferred_channel    VARCHAR(32),
    relationship_start   DATE,
    risk_score           INT,
    behavioral_score     INT,
    segment              VARCHAR(64),
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id           VARCHAR(64) PRIMARY KEY,
    customer_id          VARCHAR(64) NOT NULL REFERENCES customer_profiles(customer_id),
    product_type         VARCHAR(64),
    current_balance      NUMERIC(14,2),
    total_past_due       NUMERIC(14,2),
    days_past_due        INT,
    delinquency_stage    VARCHAR(32),
    status               VARCHAR(32) DEFAULT 'ACTIVE',
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compliance_flags (
    flag_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id          VARCHAR(64) NOT NULL,
    flag_type            VARCHAR(64) NOT NULL,
    status               VARCHAR(16) DEFAULT 'ACTIVE',
    reason               TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

-- ═══ Event store ═════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS customer_events (
    event_id             UUID PRIMARY KEY,
    customer_id          VARCHAR(64) NOT NULL,
    account_id           VARCHAR(64),
    workflow_id          VARCHAR(128),
    correlation_id       UUID,
    event_type           VARCHAR(64),
    event_category       VARCHAR(32),
    channel              VARCHAR(32),
    direction            VARCHAR(16),
    intent               VARCHAR(64),
    payload              JSONB DEFAULT '{}',
    source_service       VARCHAR(64),
    occurred_at          TIMESTAMPTZ NOT NULL,
    received_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_events_customer ON customer_events(customer_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_events_correlation ON customer_events(correlation_id);
CREATE INDEX IF NOT EXISTS ix_events_category_time ON customer_events(event_category, occurred_at DESC);

-- ═══ AI agent receipts (structured-ai-decisions) ═════════════════

CREATE TABLE IF NOT EXISTS agent_actions (
    action_id            UUID PRIMARY KEY,
    trace_id             UUID,
    agent_type           VARCHAR(32) NOT NULL,
    customer_id          VARCHAR(64) NOT NULL,
    account_id           VARCHAR(64),
    workflow_id          VARCHAR(128),
    action_type          VARCHAR(64) NOT NULL,
    parameters           JSONB DEFAULT '{}',
    rationale            TEXT,
    confidence           NUMERIC(4,3),
    status               VARCHAR(24) NOT NULL DEFAULT 'recorded',
    dispatched_at        TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agent_actions_customer ON agent_actions(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_actions_trace ON agent_actions(trace_id);

CREATE TABLE IF NOT EXISTS ai_reasoning_traces (
    event_id             UUID PRIMARY KEY,
    agent_type           VARCHAR(32),
    customer_id          VARCHAR(64),
    workflow_id          VARCHAR(128),
    reasoning_steps      JSONB,
    action_taken         VARCHAR(64),
    confidence           NUMERIC(4,3),
    escalated            BOOLEAN,
    tokens_used          INT,
    latency_ms           INT,
    model                VARCHAR(64),
    occurred_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══ Strategy audit + A/B (champion-challenger) ══════════════════

CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_version     VARCHAR(32) PRIMARY KEY,
    role                 VARCHAR(16) NOT NULL CHECK (role IN ('champion', 'challenger', 'retired')),
    description          TEXT,
    allocation_pct       NUMERIC(5,2) NOT NULL DEFAULT 0,
    activated_at         TIMESTAMPTZ,
    retired_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS customer_strategy_assignments (
    customer_id          VARCHAR(64) PRIMARY KEY,
    strategy_version     VARCHAR(32) NOT NULL REFERENCES strategy_versions(strategy_version),
    assigned_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assignment_method    VARCHAR(24) NOT NULL DEFAULT 'random_allocation'
);

CREATE TABLE IF NOT EXISTS strategy_audit_log (
    audit_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id          VARCHAR(64) NOT NULL,
    workflow_id          VARCHAR(128),
    strategy_version     VARCHAR(32) NOT NULL,
    policy_name          VARCHAR(64),
    input_context        JSONB,
    decision             JSONB,
    evaluated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_strategy_audit_customer ON strategy_audit_log(customer_id, evaluated_at DESC);
CREATE INDEX IF NOT EXISTS ix_strategy_audit_version ON strategy_audit_log(strategy_version, evaluated_at DESC);

-- Seed the champion with 100% allocation
INSERT INTO strategy_versions (strategy_version, role, description, allocation_pct, activated_at)
VALUES ('v1.0.0', 'champion', 'Initial baseline strategy', 100.00, NOW())
ON CONFLICT (strategy_version) DO NOTHING;

-- ═══ Regulatory artifacts ════════════════════════════════════════
-- Example: Reg F §1006.34 validation notice tracking
-- Replace with your domain's regulatory tables

CREATE TABLE IF NOT EXISTS validation_notices (
    notice_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id          VARCHAR(64) NOT NULL,
    workflow_id          VARCHAR(128),
    first_contact_at     TIMESTAMPTZ NOT NULL,
    deadline_at          TIMESTAMPTZ NOT NULL,
    delivered_at         TIMESTAMPTZ,
    delivery_event_id    UUID,
    status               VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ═══ WORM audit triggers (worm-audit-trail) ══════════════════════

CREATE OR REPLACE FUNCTION audit_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit table %.% is append-only; UPDATE/DELETE rejected (op=%, id=%)',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP,
        COALESCE(
            (to_jsonb(OLD)->>'audit_id'),
            (to_jsonb(OLD)->>'event_id'),
            (to_jsonb(OLD)->>'action_id'),
            (to_jsonb(OLD)->>'trace_id'),
            (to_jsonb(OLD)->>'notice_id'),
            'unknown'
        );
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_strategy_audit_immutable ON strategy_audit_log;
CREATE TRIGGER trg_strategy_audit_immutable
    BEFORE UPDATE OR DELETE ON strategy_audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

DROP TRIGGER IF EXISTS trg_customer_events_immutable ON customer_events;
CREATE TRIGGER trg_customer_events_immutable
    BEFORE UPDATE OR DELETE ON customer_events
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

DROP TRIGGER IF EXISTS trg_ai_reasoning_immutable ON ai_reasoning_traces;
CREATE TRIGGER trg_ai_reasoning_immutable
    BEFORE UPDATE OR DELETE ON ai_reasoning_traces
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

DROP TRIGGER IF EXISTS trg_validation_notices_immutable ON validation_notices;
CREATE TRIGGER trg_validation_notices_immutable
    BEFORE UPDATE OR DELETE ON validation_notices
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

-- agent_actions: status transitions allowed; decision fields locked
CREATE OR REPLACE FUNCTION agent_actions_protect_decision() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.action_type   IS DISTINCT FROM OLD.action_type
       OR NEW.rationale  IS DISTINCT FROM OLD.rationale
       OR NEW.confidence IS DISTINCT FROM OLD.confidence
       OR NEW.agent_type IS DISTINCT FROM OLD.agent_type
       OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
       OR NEW.parameters::text IS DISTINCT FROM OLD.parameters::text
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'agent_actions decision fields are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_actions_decision_locked ON agent_actions;
CREATE TRIGGER trg_agent_actions_decision_locked
    BEFORE UPDATE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION agent_actions_protect_decision();

DROP TRIGGER IF EXISTS trg_agent_actions_no_delete ON agent_actions;
CREATE TRIGGER trg_agent_actions_no_delete
    BEFORE DELETE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();
