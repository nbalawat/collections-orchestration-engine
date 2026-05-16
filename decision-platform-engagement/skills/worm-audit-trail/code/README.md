# worm-audit-trail · reference code

Drop-in PostgreSQL files that implement WORM (write-once-read-many) audit at the trigger layer. Lift, adapt the table names to your schema, apply as a migration.

## Files

- `audit_immutable.sql` — the trigger function (database-wide)
- `apply_triggers.sql` — attaches the trigger to standard audit tables
- `protect_decision_fields.sql` — narrow carve-out trigger for tables that allow status transitions but lock decision fields (e.g. `agent_actions`)
- `verify.sh` — verifies the triggers actually block UPDATE and DELETE

## How to adapt

1. Identify your audit tables. Common ones:
   - `<your-domain>_audit_log` (every policy evaluation)
   - `customer_events` / `case_events` / `transaction_events` (event store)
   - `ai_reasoning_traces`
   - `validation_notices` / `disclosure_log` (regulatory artifacts)
   - `agent_actions` (use the narrow protect_decision_fields trigger)

2. Edit `apply_triggers.sql` — replace the table names with yours.

3. Apply as a migration:
   ```bash
   psql -U <user> -d <db> -f audit_immutable.sql
   psql -U <user> -d <db> -f apply_triggers.sql
   psql -U <user> -d <db> -f protect_decision_fields.sql
   ```

4. Verify:
   ```bash
   ./verify.sh <db-connection-string>
   ```

## What this gives you

When an auditor asks "could anyone have changed this row?", you can demonstrate:

```sql
DELETE FROM strategy_audit_log WHERE audit_id = '<any-id>';
-- ERROR: Audit table public.strategy_audit_log is append-only; UPDATE/DELETE rejected
```

This is SOX / SOC 2 Type II evidence at the storage-engine layer — not application-layer enforcement that can be bypassed.

## Other databases

| DB | Mechanism |
|---|---|
| PostgreSQL | this code |
| MySQL | similar trigger syntax; rewrite using `BEFORE UPDATE OR DELETE ON ... FOR EACH ROW BEGIN ... END` |
| SQL Server | `INSTEAD OF UPDATE, DELETE` triggers + `THROW 50000, '...', 1` |
| Oracle | `BEFORE UPDATE OR DELETE` triggers + `RAISE_APPLICATION_ERROR(-20001, '...')` plus Flashback Archive for stronger evidence |
| DynamoDB | no native triggers — use Streams + Lambda with conditional writes (`attribute_not_exists`) |

If your stack mandates a non-Postgres OLTP, prefer Postgres specifically for audit tables when feasible — the trigger pattern is the cleanest evidence story.
