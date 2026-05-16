-- WORM audit trigger function — write-once, read-many enforcement at the
-- database layer. Raises on UPDATE and DELETE.
--
-- Idempotent: safe to re-apply. Used by apply_triggers.sql to attach to
-- audit tables.

CREATE OR REPLACE FUNCTION audit_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit table %.% is append-only; UPDATE/DELETE rejected (op=%, id=%)',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP,
        COALESCE(
            (to_jsonb(OLD)->>'audit_id'),
            (to_jsonb(OLD)->>'event_id'),
            (to_jsonb(OLD)->>'action_id'),
            (to_jsonb(OLD)->>'trace_id'),
            (to_jsonb(OLD)->>'id'),
            'unknown'
        );
END;
$$ LANGUAGE plpgsql;
