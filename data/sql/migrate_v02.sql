-- Migration from v0.1-poc → v0.2 (de-mocked orchestration)
-- Idempotent: safe to run multiple times.

CREATE TABLE IF NOT EXISTS agent_actions (
    action_id           UUID PRIMARY KEY,
    trace_id            UUID,
    agent_type          VARCHAR(32) NOT NULL,
    customer_id         VARCHAR(32) NOT NULL,
    account_id          VARCHAR(32),
    workflow_id         VARCHAR(128),
    action_type         VARCHAR(64) NOT NULL,
    parameters          JSONB DEFAULT '{}',
    rationale           TEXT,
    confidence          NUMERIC(4,3),
    status              VARCHAR(24) NOT NULL DEFAULT 'recorded',
    dispatched_at       TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agent_actions_customer ON agent_actions(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_actions_trace ON agent_actions(trace_id);
CREATE INDEX IF NOT EXISTS ix_agent_actions_type ON agent_actions(action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_actions_agent ON agent_actions(agent_type, created_at DESC);

CREATE TABLE IF NOT EXISTS human_escalations (
    escalation_id       UUID PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL,
    account_id          VARCHAR(32),
    workflow_id         VARCHAR(128),
    trace_id            UUID,
    source_agent        VARCHAR(32),
    reason              TEXT NOT NULL,
    urgency             VARCHAR(16) NOT NULL DEFAULT 'normal',
    specialist_type     VARCHAR(32) NOT NULL DEFAULT 'collections_agent',
    status              VARCHAR(24) NOT NULL DEFAULT 'queued',
    assigned_to         VARCHAR(64),
    sla_due_at          TIMESTAMPTZ,
    context             JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at         TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_escalations_status ON human_escalations(status, urgency, created_at);
CREATE INDEX IF NOT EXISTS ix_escalations_customer ON human_escalations(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_escalations_specialist ON human_escalations(specialist_type, status);

CREATE TABLE IF NOT EXISTS payment_links (
    link_id             VARCHAR(64) PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL,
    account_id          VARCHAR(32),
    amount              NUMERIC(12,2) NOT NULL,
    channel             VARCHAR(16) NOT NULL,
    issued_by_agent     VARCHAR(32),
    trace_id            UUID,
    status              VARCHAR(24) NOT NULL DEFAULT 'issued',
    expires_at          TIMESTAMPTZ NOT NULL,
    issued_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    clicked_at          TIMESTAMPTZ,
    paid_at             TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_payment_links_customer ON payment_links(customer_id, issued_at DESC);
CREATE INDEX IF NOT EXISTS ix_payment_links_status ON payment_links(status, expires_at);

CREATE TABLE IF NOT EXISTS service_heartbeats (
    service_name        VARCHAR(64) PRIMARY KEY,
    instance_id         VARCHAR(64),
    status              VARCHAR(16) NOT NULL DEFAULT 'healthy',
    throughput_per_sec  NUMERIC(10,2),
    error_count_5m      INTEGER DEFAULT 0,
    p99_latency_ms      INTEGER,
    extra               JSONB DEFAULT '{}',
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
