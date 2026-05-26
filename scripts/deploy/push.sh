#!/usr/bin/env bash
# Push current repo + .env to the EC2 host, then bring the compose stack up.
# Run after scripts/deploy/provision.sh.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${DIR}/_common.sh"
load_state

[[ -n "${PUBLIC_IP:-}" ]] || { err "No instance found. Run 'make deploy-bootstrap' first."; exit 1; }
[[ -f "${KEY_FILE}" ]]    || { err "Missing ${KEY_FILE}"; exit 1; }
[[ -f "${REPO_ROOT}/.env" ]] || { err "Missing .env (required: ANTHROPIC_API_KEY, AWS creds, LAKEHOUSE_* buckets)"; exit 1; }

log "Target: ec2-user@${PUBLIC_IP}"

# Wait for SSH to be ready (instance may have just booted)
log "Waiting for SSH…"
for i in $(seq 1 30); do
  if ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
       -o LogLevel=ERROR -o ConnectTimeout=5 "ec2-user@${PUBLIC_IP}" 'echo ok' >/dev/null 2>&1; then
    ok "SSH ready"
    break
  fi
  sleep 5
  if [[ "$i" == "30" ]]; then
    err "SSH did not come up after 150s. Check security group + EC2 console."
    exit 1
  fi
done

# Wait for user-data (Docker install) to finish
log "Waiting for user-data (Docker install) to finish…"
ssh_into '
  for i in $(seq 1 60); do
    if [ -f /var/lib/cloud/instance/boot-finished ] && command -v docker >/dev/null; then
      echo "ready"; exit 0
    fi
    sleep 5
  done
  echo "user-data did not finish in 300s"; exit 1
'

# Sync repo (exclude noise + secrets that we set separately)
log "Syncing repo to /opt/collections…"
rsync -az --delete \
  --exclude=.git/ \
  --exclude=.venv/ \
  --exclude=node_modules/ \
  --exclude=web/node_modules/ \
  --exclude=web/dist/ \
  --exclude=__pycache__/ \
  --exclude='*.pyc' \
  --exclude=.pytest_cache/ \
  --exclude=.ruff_cache/ \
  --exclude=.deploy-state \
  --exclude=ec2-key.pem \
  --exclude=.env \
  -e "ssh -i ${KEY_FILE} -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR" \
  "${REPO_ROOT}/" "ec2-user@${PUBLIC_IP}:/opt/collections/"

# Generate a basic-auth hash for the demo password if BASIC_AUTH_HASH not already in .env
PASSWORD="${DEPLOY_BASIC_AUTH_PASSWORD:-collections-demo-2026}"
log "Generating bcrypt hash for basic-auth password…"
BASIC_AUTH_HASH="$(docker run --rm caddy:2.8-alpine caddy hash-password --plaintext "${PASSWORD}" 2>/dev/null || true)"
if [[ -z "${BASIC_AUTH_HASH}" ]]; then
  warn "Could not generate bcrypt locally (Docker not running?). Skipping basic auth — site will be OPEN."
fi

# Upload .env with prod overrides appended
log "Uploading .env (with prod SITE_ADDRESS + basic auth)…"
{
  cat "${REPO_ROOT}/.env"
  echo ""
  echo "# ── Appended by scripts/deploy/push.sh ──"
  echo "SITE_ADDRESS=${SITE_HOSTNAME}"
  echo "ACME_EMAIL=${ACME_EMAIL}"
  [[ -n "${BASIC_AUTH_HASH}" ]] && echo "BASIC_AUTH_HASH=${BASIC_AUTH_HASH}"
} | ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
       -o LogLevel=ERROR "ec2-user@${PUBLIC_IP}" 'cat > /opt/collections/.env && chmod 600 /opt/collections/.env'

# Pull updated images + recreate
log "Bringing stack up on EC2 (this builds images on first run — ~5 min)…"
ssh_into 'cd /opt/collections && docker compose build && docker compose up -d postgres redis kafka temporal opa'
ssh_into 'cd /opt/collections && docker compose up -d --wait postgres redis kafka 2>&1 | grep -v "^$" || true'
ssh_into 'cd /opt/collections && docker compose run --rm seed'
ssh_into 'cd /opt/collections && docker compose up -d api worker signal-bridge event-projector traffic-generator lake-sink silver-compactor gold-builder temporal-ui web'

ok "Deploy complete."
echo ""
echo "  Site:        https://${SITE_HOSTNAME}"
[[ -n "${BASIC_AUTH_HASH}" ]] && echo "  Login:       demo / ${PASSWORD}"
echo "  Logs:        make deploy-logs"
echo "  SSH:         make deploy-ssh"
echo ""
warn "Caddy issues TLS on first request — wait ~30s after DNS resolves before testing."
