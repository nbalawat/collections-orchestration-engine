#!/usr/bin/env bash
# Tail logs on the deployed instance. Optional first arg = service name.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${DIR}/_common.sh"
load_state
[[ -n "${PUBLIC_IP:-}" ]] || { err "No instance — run 'make deploy-bootstrap'"; exit 1; }

SVC="${1:-}"
if [[ -n "${SVC}" ]]; then
  ssh_into "cd /opt/collections && docker compose logs -f --tail=200 ${SVC}"
else
  ssh_into 'cd /opt/collections && docker compose logs -f --tail=100'
fi
