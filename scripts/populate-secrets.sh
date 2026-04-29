#!/usr/bin/env bash
# Populate Agent Cody secrets. Run once per environment.
# - Uses stdin-based secret passing to avoid argv leaks to ps(1).
# - umask 077 so any temp files are owner-only.
# - Unsets secrets from env after use.
set -euo pipefail
umask 077

REGION="${AWS_REGION:-us-east-1}"
NAME_PREFIX="agent-cody"

prompt_secret() {
  local prompt="$1"
  local var
  printf "%s: " "$prompt" >&2
  read -rs var
  echo >&2
  printf '%s' "$var"
}

put_secret() {
  local secret_id="$1"
  local json_payload="$2"
  printf '%s' "$json_payload" \
    | aws secretsmanager put-secret-value \
        --secret-id "$secret_id" \
        --secret-string file:///dev/stdin \
        --region "$REGION" >/dev/null
  echo "  ✓ $secret_id populated"
}

echo "=== Agent Cody secret population ==="
echo "Secrets are read via -s (no echo) and piped via stdin (no ps(1) leak)."
echo

ANTHROPIC_KEY=$(prompt_secret "Anthropic API key")
put_secret "${NAME_PREFIX}/anthropic-api-key" \
  "$(printf '{"api_key":"%s","populated_at":"%s"}' "$ANTHROPIC_KEY" "$(date -Iseconds)")"
unset ANTHROPIC_KEY

printf "ElevenLabs API key (optional, press Enter to skip): " >&2
read -rs ELEVENLABS_KEY; echo >&2
if [ -n "$ELEVENLABS_KEY" ]; then
  put_secret "${NAME_PREFIX}/elevenlabs-api-key" \
    "$(printf '{"api_key":"%s","populated_at":"%s"}' "$ELEVENLABS_KEY" "$(date -Iseconds)")"
fi
unset ELEVENLABS_KEY

# Initialize the frozen flag to not-frozen
put_secret "${NAME_PREFIX}/graph-sender-frozen" \
  "$(printf '{"frozen":false,"populated_at":"%s"}' "$(date -Iseconds)")"

echo
echo "Done. Remaining secrets populated automatically:"
echo "  - agent-cody/neo4j-password       (by mem VM bootstrap)"
echo "  - agent-cody/graph-msal-token-cache (by Phase 1 device-code flow)"
echo "  - agent-cody/baileys-auth-dir     (by Phase 1 WhatsApp pairing)"
echo "  - agent-cody/style-card           (by Phase 3 style-card-refresh Lambda)"
