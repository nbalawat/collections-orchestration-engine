-- Attach the audit_immutable trigger to your audit tables.
-- Edit this list for your schema.

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

-- ADD MORE AS YOUR SCHEMA GROWS
-- For example:
-- DROP TRIGGER IF EXISTS trg_payment_history_immutable ON payment_history;
-- CREATE TRIGGER trg_payment_history_immutable
--     BEFORE UPDATE OR DELETE ON payment_history
--     FOR EACH ROW EXECUTE FUNCTION audit_immutable();
