---
name: worm-audit-trail
description: Tamper-evident audit at the database trigger layer (PostgreSQL recommended). UPDATE and DELETE on audit tables raise. Narrow status-only carve-outs allowed for workflow-status columns. Trigger when the user mentions audit trail, immutable, tamper-evident, SOX, SOC 2, WORM, write-once, or "could someone change the audit log".
metadata:
  type: pattern
  tags: [audit, compliance, governance, SOX, SOC2]
---

# WORM audit trail — tamper-evident at the database layer

## What this solves

Audit-table immutability enforced at the application layer is not tamper-evidence. Anyone with database access can `UPDATE` an audit row from outside the application. SOX, SOC 2 Type II, and SR 11-7 (model risk management) all expect tamper-evidence at the database layer — the storage engine itself refuses the mutation.

## The pattern

Define a PostgreSQL trigger function that raises on UPDATE / DELETE attempts. Attach it to every audit table. Verify it works by trying to delete a row.

### The trigger function

```sql
CREATE OR REPLACE FUNCTION audit_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit table %.% is append-only; UPDATE/DELETE rejected (op=%, id=%)',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP,
        COALESCE((to_jsonb(OLD)->>'audit_id'),
                 (to_jsonb(OLD)->>'event_id'),
                 (to_jsonb(OLD)->>'action_id'),
                 'unknown');
END;
$$ LANGUAGE plpgsql;
```

### Attach to audit tables

```sql
DROP TRIGGER IF EXISTS trg_strategy_audit_immutable ON strategy_audit_log;
CREATE TRIGGER trg_strategy_audit_immutable
    BEFORE UPDATE OR DELETE ON strategy_audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_immutable();
```

Repeat for every audit table: `customer_events`, `ai_reasoning_traces`, `validation_notices`, etc.

### Narrow status-only carve-outs

For tables where status legitimately transitions (e.g. `agent_actions.status` going from `recorded → dispatched → completed`), use a narrower trigger that locks only the decision fields:

```sql
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
        RAISE EXCEPTION 'agent_actions decision fields are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

DELETE is still blocked entirely — only the status / dispatched_at / completed_at columns can be updated.

## What to verify

Open a SQL prompt and try the operations. They should fail with the trigger's exception:

```sql
DELETE FROM strategy_audit_log WHERE audit_id = '<any-id>';
-- ERROR: Audit table public.strategy_audit_log is append-only; UPDATE/DELETE rejected

UPDATE agent_actions SET action_type = 'tampered' WHERE action_id = '<any-id>';
-- ERROR: agent_actions decision fields are immutable

UPDATE agent_actions SET status = 'dispatched' WHERE action_id = '<any-id>';
-- UPDATE 1 (allowed by the narrow carve-out)
```

This is the SOX/SOC 2 evidence — paste the trigger function definition + the raise outputs into the control test.

## Tables that should be WORM

| Table | Reason |
|---|---|
| `strategy_audit_log` | Every OPA evaluation |
| `customer_events` | The event store |
| `ai_reasoning_traces` | AI agent reasoning |
| `validation_notices` | Reg F §1006.34 evidence |
| `agent_actions` | AI agent decision receipts (narrow carve-out for status) |
| `compliance_flags_history` | Past flag activations |
| `payment_history` | Financial records |

## What NOT to make WORM

- Operational state tables (customer_profiles updates, journey state snapshots) — these legitimately change
- Cache tables, materialized views, derived aggregates — they can be rebuilt
- Configuration tables — they change with deployments

## Equivalent in other databases

| DB | Mechanism |
|---|---|
| PostgreSQL | Trigger function (this skill) |
| MySQL | Trigger function (same pattern) |
| SQL Server | INSTEAD OF triggers |
| Oracle | Database triggers + Flashback Archive |
| DynamoDB | No native triggers; use Lambda streams + conditional writes (`attribute_not_exists`) |
| MongoDB | Change streams + application-layer enforcement (weaker) |

PostgreSQL has the cleanest story. If the engagement allows it for audit tables, prefer it even when the primary OLTP store is something else.

## Migration / idempotency

The trigger creation must be idempotent — `DROP TRIGGER IF EXISTS` then `CREATE TRIGGER`. Put it in a migration file (`migrate_v0X_audit.sql`) so it can be re-applied without error.

## Common failure modes to avoid

- **Application-layer immutability only.** Anyone with DB access bypasses it. Use the trigger.
- **WORM on tables that legitimately change.** Don't try to make `customer_profiles` immutable — you'll break legitimate updates.
- **Forgetting the narrow carve-out for `agent_actions.status`.** Workflow lifecycle transitions are legitimate; only the decision fields should be locked.
- **Not testing.** Try the DELETE, paste the error into your audit evidence document.

## Worked example from the reference engagement

`data/sql/migrate_v03_audit.sql` in the reference engagement creates the `audit_immutable()` function and attaches it to four tables, plus a narrow `agent_actions_protect_decision()` trigger that allows status transitions but locks decision fields. Verified by attempting deletes / updates in `psql` — the trigger fires with the audit_id in the error message.

The Audit / SOX persona on the stakeholder demo flow asks for this specific verification. Run it live on the call.
