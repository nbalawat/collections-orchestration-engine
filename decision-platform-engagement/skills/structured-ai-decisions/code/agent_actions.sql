-- AI agent decision audit table — the receipt for every agent invocation.
-- Apply the WORM trigger from worm-audit-trail/code/ for tamper-evidence.

CREATE TABLE IF NOT EXISTS agent_actions (
    action_id           UUID PRIMARY KEY,
    trace_id            UUID,
    agent_type          VARCHAR(32) NOT NULL,
    customer_id         VARCHAR(64) NOT NULL,
    account_id          VARCHAR(64),
    workflow_id         VARCHAR(128),
    action_type         VARCHAR(64) NOT NULL,
    parameters          JSONB DEFAULT '{}',
    rationale           TEXT,
    confidence          NUMERIC(4,3),
    status              VARCHAR(24) NOT NULL DEFAULT 'recorded',  -- recorded → dispatched → completed
    dispatched_at       TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_agent_actions_customer ON agent_actions(customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_actions_trace    ON agent_actions(trace_id);
CREATE INDEX IF NOT EXISTS ix_agent_actions_type     ON agent_actions(action_type, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_agent_actions_agent    ON agent_actions(agent_type, created_at DESC);
