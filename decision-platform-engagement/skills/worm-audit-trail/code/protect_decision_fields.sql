-- Narrow carve-out trigger for tables that legitimately allow status transitions
-- (e.g. agent_actions.status going recorded → dispatched → completed) but must
-- lock the decision fields (action_type, rationale, confidence, etc.).

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
        RAISE EXCEPTION 'agent_actions decision fields are immutable; only status/dispatched_at/completed_at may be updated';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_actions_decision_locked ON agent_actions;
CREATE TRIGGER trg_agent_actions_decision_locked
    BEFORE UPDATE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION agent_actions_protect_decision();

-- DELETE is still blocked outright for this table:
DROP TRIGGER IF EXISTS trg_agent_actions_no_delete ON agent_actions;
CREATE TRIGGER trg_agent_actions_no_delete
    BEFORE DELETE ON agent_actions
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();
