#!/usr/bin/env bash
# Tear down everything provision.sh created. Confirms before destroying.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${DIR}/_common.sh"
load_state

if [[ -z "${INSTANCE_ID:-}" && -z "${SG_ID:-}" ]]; then
  warn "No state file — nothing to tear down."
  exit 0
fi

cat <<EOF

About to destroy:
  Instance:    ${INSTANCE_ID:-(none)}
  SG:          ${SG_ID:-(none)}
  Key pair:    ${KEY_NAME}
  DNS record:  ${SITE_HOSTNAME} (A record will be deleted)

This is irreversible. Type 'destroy' to confirm:
EOF

read -r CONFIRM
if [[ "${CONFIRM}" != "destroy" ]]; then
  warn "Cancelled."
  exit 1
fi

# ── Terminate instance ──────────────────────────────────────────────
if [[ -n "${INSTANCE_ID:-}" ]]; then
  log "Terminating ${INSTANCE_ID}…"
  aws ec2 terminate-instances --instance-ids "${INSTANCE_ID}" >/dev/null || true
  log "Waiting for termination…"
  aws ec2 wait instance-terminated --instance-ids "${INSTANCE_ID}" || true
  ok "Instance terminated"
fi

# ── Delete DNS record ───────────────────────────────────────────────
if [[ -n "${PUBLIC_IP:-}" ]]; then
  log "Deleting A record ${SITE_HOSTNAME}…"
  CHANGE_BATCH=$(cat <<EOF
{
  "Changes": [{
    "Action": "DELETE",
    "ResourceRecordSet": {
      "Name": "${SITE_HOSTNAME}",
      "Type": "A",
      "TTL": 60,
      "ResourceRecords": [{"Value": "${PUBLIC_IP}"}]
    }
  }]
}
EOF
)
  aws route53 change-resource-record-sets \
    --hosted-zone-id "${HOSTED_ZONE_ID}" \
    --change-batch "${CHANGE_BATCH}" >/dev/null 2>&1 || warn "A record deletion failed (may not exist)"
  ok "DNS record removed"
fi

# ── Delete security group ──────────────────────────────────────────
if [[ -n "${SG_ID:-}" ]]; then
  log "Deleting security group ${SG_ID}…"
  for i in 1 2 3 4 5; do
    if aws ec2 delete-security-group --group-id "${SG_ID}" 2>/dev/null; then
      ok "SG deleted"
      break
    fi
    warn "  SG still in use (instance ENI lingering), retrying in 10s… (${i}/5)"
    sleep 10
  done
fi

# ── Delete key pair ────────────────────────────────────────────────
log "Deleting key pair ${KEY_NAME}…"
aws ec2 delete-key-pair --key-name "${KEY_NAME}" 2>/dev/null || true
rm -f "${KEY_FILE}"
ok "Key pair removed"

# ── Clean up state ─────────────────────────────────────────────────
rm -f "${STATE_FILE}"
ok "State file removed"

echo ""
ok "Teardown complete. Domain registration is NOT affected."
