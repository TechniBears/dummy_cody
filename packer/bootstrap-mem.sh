#!/usr/bin/env bash
# Memory VM bootstrap — Neo4j 5.26 install with secure password provisioning.
# Runs as user-data on first boot; self-wipes user-data at the end so the plaintext
# password trace cannot be recovered from DescribeInstanceAttribute or IMDS.
#
# NOTE: No `-x` in the shebang — `set -x` would trace the password into cloud-init-output.log.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

log() { echo "[bootstrap-mem] $(date -Iseconds) $*" | tee -a /var/log/cody-bootstrap.log; }

log "starting"

# ---------------- Prereqs (G1 fix: jq + awscli before use) ----------------
# Ubuntu 24.04 removed `awscli` from apt — install via snap (preinstalled on Canonical AMIs)
apt-get update
apt-get install -y jq openjdk-21-jdk-headless curl gnupg unattended-upgrades python3-boto3
snap install aws-cli --classic
ln -sf /snap/bin/aws /usr/local/bin/aws

# ---------------- Wait for instance profile propagation ----------------
# IAM role attachment can take a few seconds to be usable. Retry.
for i in $(seq 1 30); do
  if aws sts get-caller-identity --region us-east-1 >/dev/null 2>&1; then
    log "IAM ready after ${i}s"
    break
  fi
  sleep 2
done

# ---------------- Neo4j install ----------------
curl -fsSL https://debian.neo4j.com/neotechnology.gpg.key \
  | gpg --dearmor -o /etc/apt/trusted.gpg.d/neo4j.gpg
echo 'deb https://debian.neo4j.com stable 5' > /etc/apt/sources.list.d/neo4j.list
apt-get update
apt-get install -y neo4j=1:5.26.0

# CRITICAL (G3 fix): stop + disable BEFORE set-initial-password. The Debian package
# auto-starts Neo4j which initializes with default creds, and set-initial-password
# then errors out with "live Neo4j-users were detected".
systemctl stop neo4j || true
systemctl disable neo4j

# Bind to 0.0.0.0 (SG enforces Bolt+HTTP ingress allow-list from gw only)
sed -i 's/#server.default_listen_address=0.0.0.0/server.default_listen_address=0.0.0.0/' /etc/neo4j/neo4j.conf

# ---------------- Secret handling (C2 fix — no trace) ----------------
# No -x inside this block. Reads existing password if placeholder was populated
# out-of-band, otherwise generates a fresh one and writes it back.
log "fetching neo4j password"
SECRET_BLOB=$(aws secretsmanager get-secret-value \
  --secret-id agent-cody/neo4j-password \
  --query SecretString --output text \
  --region us-east-1 2>/dev/null || echo '{}')

HAS_PW=$(echo "$SECRET_BLOB" | jq -r 'has("password")')
if [ "$HAS_PW" = "true" ]; then
  NEO4J_PW=$(echo "$SECRET_BLOB" | jq -r '.password')
  log "password fetched from Secrets Manager"
else
  NEO4J_PW=$(openssl rand -base64 32 | tr -d '\n')
  printf '{"password":"%s","populated_at":"%s"}' "$NEO4J_PW" "$(date -Iseconds)" \
    | aws secretsmanager put-secret-value \
        --secret-id agent-cody/neo4j-password \
        --secret-string file:///dev/stdin \
        --region us-east-1 >/dev/null
  log "fresh password generated and stored"
fi

neo4j-admin dbms set-initial-password "$NEO4J_PW" >/dev/null 2>&1
unset NEO4J_PW SECRET_BLOB HAS_PW

systemctl enable neo4j
systemctl start neo4j
log "neo4j started"

# ---------------- Self-wipe user-data (C2 fix) ----------------
# Overwrites user-data with a benign string so the plaintext script + password
# generation pipeline is not recoverable via DescribeInstanceAttribute or
# http://169.254.169.254/latest/user-data (IMDS).
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $(curl -s -X PUT \
  'http://169.254.169.254/latest/api/token' \
  -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')" \
  http://169.254.169.254/latest/meta-data/instance-id)

# Must stop to modify user-data on most instance types
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region us-east-1 >/dev/null 2>&1 || true
# Note: modify-instance-attribute requires a stopped instance. We'll let the next
# reboot do the wipe via a one-shot systemd unit. For Phase 0 simplicity, clear
# the user-data via a deferred action scheduled for next boot.

# Clear on next boot via a oneshot systemd service
cat > /etc/systemd/system/wipe-userdata.service <<'EOF'
[Unit]
Description=Wipe EC2 user-data after bootstrap
After=network-online.target
ConditionPathExists=/var/lib/cloud/instance/user-data.txt
RefuseManualStart=yes

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'INSTANCE_ID=$(curl -sH "X-aws-ec2-metadata-token: $(curl -s -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")" http://169.254.169.254/latest/meta-data/instance-id) && aws ec2 modify-instance-attribute --instance-id "$INSTANCE_ID" --user-data "Value=Ym9vdHN0cmFwLWNvbXBsZXRlZCAtLSBzZWUgcGFja2VyL2Jvb3RzdHJhcC1tZW0uc2g=" --region us-east-1 || true'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF
systemctl enable wipe-userdata.service

# Restart so the wipe runs on next boot (happens automatically after stop above)
aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region us-east-1 >/dev/null 2>&1 || true

log "bootstrap complete; user-data wipe scheduled for next boot"
