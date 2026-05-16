-- v0.3 migration: enforce WORM (write-once, read-many) on audit tables.
-- SOX, SOC2 Type 2, and SR 11-7 model risk management all expect that audit
-- records cannot be silently changed or removed after the fact.
--
-- We implement this with a row-level trigger that raises on UPDATE/DELETE
-- attempts. Application code that needs to "fix" a record must INSERT a new
-- row with a reversal pattern, leaving the original intact.
--
-- Idempotent: safe to re-run.

CREATE OR REPLACE FUNCTION audit_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit table %.% is append-only; UPDATE/DELETE rejected (op=%, action_id/event_id=%)',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP,
        COALESCE((to_jsonb(OLD)->>'audit_id'),
                 (to_jsonb(OLD)->>'event_id'),
                 (to_jsonb(OLD)->>'action_id'),
                 (to_jsonb(OLD)->>'trace_id'),
                 'unknown');
END;
$$ LANGUAGE plpgsql;

-- strategy_audit_log
DROP TRIGGER IF EXISTS trg_strategy_audit_immutable ON strategy_audit_log;
CREATE TRIGGER trg_strategy_audit_immutable
    BEFORE UPDATE OR DELETE ON strategy_audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

-- agent_actions (the receipts for AI decisions; must be immutable for MRM)
DROP TRIGGER IF EXISTS trg_agent_actions_immutable ON agent_actions;
CREATE TRIGGER trg_agent_actions_immutable
    BEFORE DELETE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

-- agent_actions allows status transitions (recorded → dispatched → completed)
-- via a narrower trigger that only blocks changes to the core decision fields.
CREATE OR REPLACE FUNCTION agent_actions_protect_decision() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.action_type IS DISTINCT FROM OLD.action_type
       OR NEW.rationale IS DISTINCT FROM OLD.rationale
       OR NEW.confidence IS DISTINCT FROM OLD.confidence
       OR NEW.agent_type IS DISTINCT FROM OLD.agent_type
       OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
       OR NEW.parameters::text IS DISTINCT FROM OLD.parameters::text
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'agent_actions decision fields are immutable; only status/dispatched_at/completed_at may be updated';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_actions_decision_locked ON agent_actions;
CREATE TRIGGER trg_agent_actions_decision_locked
    BEFORE UPDATE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION agent_actions_protect_decision();

-- customer_events: append-only event log
DROP TRIGGER IF EXISTS trg_customer_events_immutable ON customer_events;
CREATE TRIGGER trg_customer_events_immutable
    BEFORE UPDATE OR DELETE ON customer_events
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();

-- ai_reasoning_traces: append-only
DROP TRIGGER IF EXISTS trg_ai_traces_immutable ON ai_reasoning_traces;
CREATE TRIGGER trg_ai_traces_immutable
    BEFORE UPDATE OR DELETE ON ai_reasoning_traces
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();
