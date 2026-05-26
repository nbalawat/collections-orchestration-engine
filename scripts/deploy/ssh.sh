#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${DIR}/_common.sh"
load_state
[[ -n "${PUBLIC_IP:-}" ]] || { err "No instance — run 'make deploy-bootstrap'"; exit 1; }
exec ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
         -o LogLevel=ERROR "ec2-user@${PUBLIC_IP}"
