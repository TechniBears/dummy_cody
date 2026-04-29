#!/usr/bin/env bash
# Called by systemd ExecStartPre on the OpenClaw gateway.
# Fetches the Telegram bot token from AWS Secrets Manager via boto3 (not snap aws CLI,
# which broke under systemd's PrivateTmp/namespace confinement) and writes it to a
# tmpfs env file that the main service then loads via EnvironmentFile=.
set -euo pipefail

ENV_FILE=${ENV_FILE:-/run/openclaw/env}
SECRET_ID=${SECRET_ID:-agent-cody/telegram-bot-token}
REGION=${AWS_REGION:-us-east-1}

# Ensure runtime dir exists (RuntimeDirectory= in unit creates it, but be defensive).
install -d -m 0700 -o openclaw -g openclaw "$(dirname "$ENV_FILE")"

# Use system python3 + boto3 (apt-installed in install-base.sh as python3-boto3).
# python3-boto3 reads creds from instance metadata service v2 (IMDSv2) which works fine inside systemd.
TOKEN=$(/usr/bin/python3 -c "
import boto3, json, sys
try:
    v = boto3.client('secretsmanager', region_name='${REGION}').get_secret_value(SecretId='${SECRET_ID}')
    print(json.loads(v['SecretString'])['token'])
except Exception as e:
    sys.stderr.write(f'fetch failed: {type(e).__name__}: {e}\n')
    sys.exit(1)
")

if [ -z "$TOKEN" ]; then
  echo "ERROR: empty token returned from Secrets Manager" >&2
  exit 1
fi

# Write env file: 0600, owned by openclaw.
# Preserve any non-TELEGRAM_BOT_TOKEN lines other helpers have added — e.g.
# cody-bridge-helper writes DASHBOARD_URL for dev sessions. An older version
# of this script used '>' and wiped those lines on every service restart.
umask 077
tmp="$(mktemp)"
if [ -f "$ENV_FILE" ]; then
  grep -v '^TELEGRAM_BOT_TOKEN=' "$ENV_FILE" > "$tmp" || true
fi
printf 'TELEGRAM_BOT_TOKEN=%s\n' "$TOKEN" >> "$tmp"
install -m 0600 -o openclaw -g openclaw "$tmp" "$ENV_FILE"
rm -f "$tmp"

echo "fetched telegram token -> $ENV_FILE (length=${#TOKEN})"
