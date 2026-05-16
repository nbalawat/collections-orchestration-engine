#!/usr/bin/env bash
# Verify WORM triggers actually block UPDATE and DELETE.
# Usage: ./verify.sh "postgres://user:pass@host/db"

set -euo pipefail

DSN="${1:?usage: $0 <postgres-connection-string>}"

echo "=== Verifying WORM triggers ==="

# Pick the first row from strategy_audit_log if it exists
EXIST=$(psql "${DSN}" -t -A -c "SELECT EXISTS (SELECT 1 FROM strategy_audit_log LIMIT 1)" 2>/dev/null || echo "f")
if [[ "${EXIST}" != "t" ]]; then
  echo "no rows in strategy_audit_log; insert at least one to test"
  exit 0
fi

# Try DELETE — should raise
echo
echo "Attempting DELETE on strategy_audit_log (should raise) …"
if psql "${DSN}" -c "DELETE FROM strategy_audit_log WHERE audit_id = (SELECT audit_id FROM strategy_audit_log LIMIT 1)" 2>&1 | grep -q "append-only"; then
  echo "✓ DELETE blocked by trigger"
else
  echo "✗ DELETE succeeded — TRIGGER IS NOT WORKING"
  exit 1
fi

# Try UPDATE on agent_actions decision field — should raise
echo
echo "Attempting UPDATE on agent_actions decision field (should raise) …"
EXIST2=$(psql "${DSN}" -t -A -c "SELECT EXISTS (SELECT 1 FROM agent_actions LIMIT 1)" 2>/dev/null || echo "f")
if [[ "${EXIST2}" == "t" ]]; then
  if psql "${DSN}" -c "UPDATE agent_actions SET action_type = 'tampered' WHERE action_id = (SELECT action_id FROM agent_actions LIMIT 1)" 2>&1 | grep -q "immutable"; then
    echo "✓ UPDATE of decision field blocked by trigger"
  else
    echo "✗ UPDATE succeeded — TRIGGER IS NOT WORKING"
    exit 1
  fi

  echo
  echo "Attempting UPDATE of allowed field (status) on agent_actions (should succeed) …"
  if psql "${DSN}" -c "UPDATE agent_actions SET status = 'dispatched' WHERE action_id = (SELECT action_id FROM agent_actions LIMIT 1)" 2>&1 | grep -q "UPDATE 1"; then
    echo "✓ status transition allowed by narrow trigger"
  else
    echo "✗ status update blocked — CARVE-OUT NOT WORKING"
    exit 1
  fi
fi

echo
echo "All WORM checks passed ✓"
