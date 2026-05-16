-- v0.4: Reg F §1006.34 validation notice tracking.
-- Required content within "initial communication" period.
CREATE TABLE IF NOT EXISTS validation_notices (
    notice_id           UUID PRIMARY KEY,
    customer_id         VARCHAR(32) NOT NULL,
    account_id          VARCHAR(32),
    workflow_id         VARCHAR(128),
    first_contact_at    TIMESTAMPTZ NOT NULL,
    notice_due_at       TIMESTAMPTZ NOT NULL,
    notice_sent_at      TIMESTAMPTZ,
    channel             VARCHAR(16),
    delivery_event_id   UUID,
    status              VARCHAR(24) NOT NULL DEFAULT 'pending',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_validation_customer ON validation_notices(customer_id, status);
CREATE INDEX IF NOT EXISTS ix_validation_due ON validation_notices(notice_due_at) WHERE status = 'pending';

-- Trigger immutability on validation_notices too (status transitions allowed)
CREATE OR REPLACE FUNCTION validation_notice_protect() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.notice_id IS DISTINCT FROM OLD.notice_id
       OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
       OR NEW.first_contact_at IS DISTINCT FROM OLD.first_contact_at
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'validation_notices immutable fields cannot be changed';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_validation_protect ON validation_notices;
CREATE TRIGGER trg_validation_protect
    BEFORE UPDATE ON validation_notices
    FOR EACH ROW EXECUTE FUNCTION validation_notice_protect();

DROP TRIGGER IF EXISTS trg_validation_no_delete ON validation_notices;
CREATE TRIGGER trg_validation_no_delete
    BEFORE DELETE ON validation_notices
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();
