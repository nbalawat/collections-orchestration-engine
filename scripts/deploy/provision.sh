#!/usr/bin/env bash
# Provision a single EC2 host in us-east-1: key pair, security group, instance,
# 50GB gp3 disk, Docker installed via user-data, public IP, DNS A record.
# Idempotent — re-running skips anything already in place.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${DIR}/_common.sh"
load_state

log "Region: ${AWS_REGION}"
log "Account: $(aws sts get-caller-identity --query Account --output text)"

# ── Public IP (for SSH ingress) ──────────────────────────────────────
MY_IP="$(curl -s --max-time 5 https://checkip.amazonaws.com)"
[[ -n "${MY_IP}" ]] || { err "Could not determine your public IP"; exit 1; }
log "Your IP: ${MY_IP} (SSH access will be restricted to this)"

# ── Key pair ─────────────────────────────────────────────────────────
if aws ec2 describe-key-pairs --key-names "${KEY_NAME}" >/dev/null 2>&1; then
  ok "Key pair ${KEY_NAME} already exists"
  if [[ ! -f "${KEY_FILE}" ]]; then
    err "Key exists in AWS but ${KEY_FILE} is missing locally. Run 'make destroy' then 'make deploy' to regenerate."
    exit 1
  fi
else
  log "Creating key pair ${KEY_NAME}…"
  aws ec2 create-key-pair --key-name "${KEY_NAME}" --query 'KeyMaterial' --output text > "${KEY_FILE}"
  chmod 600 "${KEY_FILE}"
  ok "Wrote private key to ${KEY_FILE} (chmod 600). DO NOT COMMIT THIS."
fi

# ── Default VPC ──────────────────────────────────────────────────────
VPC_ID="$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
            --query 'Vpcs[0].VpcId' --output text)"
[[ "${VPC_ID}" != "None" ]] || { err "No default VPC in ${AWS_REGION}"; exit 1; }
log "Default VPC: ${VPC_ID}"

# ── Security group ───────────────────────────────────────────────────
SG_ID="$(aws ec2 describe-security-groups \
          --filters Name=group-name,Values="${SG_NAME}" Name=vpc-id,Values="${VPC_ID}" \
          --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)"

if [[ -z "${SG_ID}" || "${SG_ID}" == "None" ]]; then
  log "Creating security group ${SG_NAME}…"
  SG_ID="$(aws ec2 create-security-group \
            --group-name "${SG_NAME}" --vpc-id "${VPC_ID}" \
            --description "${PROJECT_TAG} demo host" \
            --query 'GroupId' --output text)"
  ok "Created SG ${SG_ID}"
else
  ok "Security group ${SG_NAME} already exists (${SG_ID})"
fi

# ── SG rules (idempotent — ignore duplicate errors) ──────────────────
authorize() {
  local proto="$1" port="$2" cidr="$3" desc="$4"
  aws ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" --protocol "${proto}" --port "${port}" --cidr "${cidr}" \
    >/dev/null 2>&1 && log "  + ${proto}/${port} from ${cidr} (${desc})" || true
}

log "Ensuring SG ingress rules…"
authorize tcp 22  "${MY_IP}/32"  "SSH from your IP"
authorize tcp 80  "0.0.0.0/0"    "HTTP (Caddy)"
authorize tcp 443 "0.0.0.0/0"    "HTTPS (Caddy + Let's Encrypt)"

# ── Find latest AL2023 AMI ───────────────────────────────────────────
AMI_ID="$(aws ec2 describe-images --owners amazon \
          --filters "Name=name,Values=al2023-ami-2023.*-x86_64" \
                    "Name=state,Values=available" \
          --query "sort_by(Images, &CreationDate)[-1].ImageId" --output text)"
log "Latest AL2023 AMI: ${AMI_ID}"

# ── Launch instance ──────────────────────────────────────────────────
USER_DATA="$(cat <<'EOSH'
#!/bin/bash
set -euxo pipefail
dnf update -y
dnf install -y docker git rsync curl
systemctl enable --now docker
usermod -aG docker ec2-user

# Install docker compose v2 as a CLI plugin
mkdir -p /usr/local/lib/docker/cli-plugins
curl -sSL https://github.com/docker/compose/releases/download/v2.32.1/docker-compose-linux-x86_64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Prep app directory
mkdir -p /opt/collections
chown ec2-user:ec2-user /opt/collections
EOSH
)"

INSTANCE_ID="${INSTANCE_ID:-}"
if [[ -n "${INSTANCE_ID}" ]] && \
   aws ec2 describe-instances --instance-ids "${INSTANCE_ID}" \
     --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null | grep -qE "^(running|pending)$"; then
  ok "Instance ${INSTANCE_ID} already exists"
else
  log "Launching ${INSTANCE_TYPE} instance with ${EBS_SIZE_GB}GB gp3 disk…"
  INSTANCE_ID="$(aws ec2 run-instances \
    --image-id "${AMI_ID}" \
    --instance-type "${INSTANCE_TYPE}" \
    --key-name "${KEY_NAME}" \
    --security-group-ids "${SG_ID}" \
    --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=${EBS_SIZE_GB},VolumeType=gp3,DeleteOnTermination=true}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${INSTANCE_NAME}},{Key=Project,Value=${PROJECT_TAG}}]" \
    --user-data "${USER_DATA}" \
    --query 'Instances[0].InstanceId' --output text)"
  ok "Launched ${INSTANCE_ID}"
fi

log "Waiting for instance to be running (this takes ~60s)…"
aws ec2 wait instance-running --instance-ids "${INSTANCE_ID}"

INSTANCE_INFO="$(aws ec2 describe-instances --instance-ids "${INSTANCE_ID}" \
  --query 'Reservations[0].Instances[0].[PublicIpAddress,PublicDnsName]' --output text)"
PUBLIC_IP="$(echo "${INSTANCE_INFO}" | awk '{print $1}')"
PUBLIC_DNS="$(echo "${INSTANCE_INFO}" | awk '{print $2}')"
ok "Instance running"
ok "Public IP:  ${PUBLIC_IP}"
ok "Public DNS: ${PUBLIC_DNS}"

# ── Route 53 A record ────────────────────────────────────────────────
log "Setting Route 53 A record: ${SITE_HOSTNAME} → ${PUBLIC_IP}"
CHANGE_BATCH=$(cat <<EOF
{
  "Changes": [{
    "Action": "UPSERT",
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
CHANGE_ID="$(aws route53 change-resource-record-sets \
  --hosted-zone-id "${HOSTED_ZONE_ID}" \
  --change-batch "${CHANGE_BATCH}" \
  --query 'ChangeInfo.Id' --output text)"
ok "DNS change submitted (${CHANGE_ID})"

# ── Persist state ────────────────────────────────────────────────────
save_state
ok "State saved to ${STATE_FILE}"

echo ""
ok "Provision complete."
echo ""
echo "  Site:       https://${SITE_HOSTNAME}  (after Caddy issues TLS, ~30s after first 'make deploy-push')"
echo "  SSH:        ssh -i ${KEY_FILE} ec2-user@${PUBLIC_IP}"
echo "  Next step:  make deploy-push    (uploads code + .env, brings stack up)"
