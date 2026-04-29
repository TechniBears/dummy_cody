#!/usr/bin/env bash
# Phase 1 smoke test: prove (a) Telegram bot can send a proactive ping to the
# trusted user and (b) Bedrock invocation works post-IAM-hotfix from the
# openclaw IAM session.
#
# Run as root via SSM. Reads the bot token from /run/openclaw/env (already
# provisioned by openclaw-fetch-telegram-token.sh on service start).
set -uo pipefail   # NOT -e — we want both probes to run even if one fails

CHAT_ID=${CHAT_ID:-000000000}
TOKEN_FILE=${TOKEN_FILE:-/run/openclaw/env}

echo "=== telegram proactive ping ==="
if [ -r "$TOKEN_FILE" ]; then
  TOK=$(grep -oP '(?<=TELEGRAM_BOT_TOKEN=).+' "$TOKEN_FILE")
  if [ -n "$TOK" ]; then
    curl -s -X POST "https://api.telegram.org/bot${TOK}/sendMessage" \
      -d "chat_id=${CHAT_ID}" \
      --data-urlencode "text=Cody back online. IAM session refreshed post-restart. Send me a real message and you should get a real reply this time, in shaa allah." \
      | python3 -m json.tool 2>&1 | head -10
  else
    echo "ERROR: token empty in $TOKEN_FILE"
  fi
else
  echo "ERROR: $TOKEN_FILE not readable (service not running?)"
fi

echo
echo "=== bedrock smoke (us.anthropic.claude-haiku-4-5 via openclaw role) ==="
sudo -u openclaw -H bash -c "
  body=\$(printf '%s' '{\"anthropic_version\":\"bedrock-2023-05-31\",\"max_tokens\":25,\"messages\":[{\"role\":\"user\",\"content\":\"reply with: alive\"}]}' | base64 -w0)
  aws bedrock-runtime invoke-model \
    --region us-east-1 \
    --model-id us.anthropic.claude-haiku-4-5-20251001-v1:0 \
    --content-type application/json \
    --body \$body \
    /tmp/b.json 2>&1 | head -3
  echo --- response ---
  cat /tmp/b.json 2>/dev/null | head -c 600
  echo
"

echo
echo "=== bedrock smoke (sonnet — was working yesterday) ==="
sudo -u openclaw -H bash -c "
  body=\$(printf '%s' '{\"anthropic_version\":\"bedrock-2023-05-31\",\"max_tokens\":25,\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}]}' | base64 -w0)
  aws bedrock-runtime invoke-model \
    --region us-east-1 \
    --model-id us.anthropic.claude-sonnet-4-6 \
    --content-type application/json \
    --body \$body \
    /tmp/s.json 2>&1 | head -3
  echo --- response ---
  cat /tmp/s.json 2>/dev/null | head -c 600
  echo
"
