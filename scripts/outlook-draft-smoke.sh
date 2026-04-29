#!/usr/bin/env bash
# End-to-end smoke test for the outlook-draft skill path:
# (1) refresh Graph token via graph-token-fresh.py
# (2) POST a draft to Graph /me/messages
# (3) print draft_id + webLink
# Safe: only creates a draft, never sends. Delete it from Outlook after.
set -euo pipefail

TO_ADDR="${1:-test@example.com}"

GRAPH_TOKEN=$(AWS_REGION=us-east-1 /usr/bin/python3 /opt/openclaw/bin/graph-token-fresh.py)
if [ -z "$GRAPH_TOKEN" ]; then
  echo "ERROR: no token from graph-token-fresh.py" >&2
  exit 2
fi

SUBJECT="Cody smoke draft $(date -u +%Y-%m-%dT%H:%M:%SZ)"
BODY="This is an automated draft created by outlook-draft-smoke.sh to verify the Graph API path end-to-end. You can safely delete it."

PAYLOAD=$(jq -n \
  --arg subject "$SUBJECT" \
  --arg body "$BODY" \
  --arg to "$TO_ADDR" \
  '{
    subject: $subject,
    body: { contentType: "Text", content: $body },
    toRecipients: [ { emailAddress: { address: $to } } ]
  }')

RESP=$(curl -sS -X POST https://graph.microsoft.com/v1.0/me/messages \
  -H "Authorization: Bearer $GRAPH_TOKEN" \
  -H "Content-Type: application/json" \
  --data "$PAYLOAD")

DRAFT_ID=$(echo "$RESP" | jq -r '.id // empty')
WEB_LINK=$(echo "$RESP" | jq -r '.webLink // empty')

if [ -z "$DRAFT_ID" ]; then
  echo "ERROR: no draft id in response" >&2
  echo "--- raw response ---" >&2
  echo "$RESP" >&2
  exit 3
fi

echo "draft_id=$DRAFT_ID"
echo "web_link=$WEB_LINK"
echo "subject=$SUBJECT"
