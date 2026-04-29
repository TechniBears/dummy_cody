#!/usr/bin/env bash
# local-deploy.sh — operator-side deploy driver for the 2026-04-22 schema + allowlist work.
#
# Runs everything end-to-end with safety stops:
#   [1/5] Validate rendered config
#   [2/5] Verify VM state (describe-instances)
#   [3/5] Graphiti smoke test via SSM (with auto-diagnostics on failure)
#   [4/5] cody-refresh --check (prompts before reconciling drift)
#   [5/5] Commit + push on main (prompt-confirmed)
#
# Idempotent — running twice after everything's pushed is a no-op beyond
# re-checking. Intended to be run from your laptop with AWS SSO already done
# for the technibears profile (or SSO login will be prompted).
#
# Usage:
#   bash scripts/local-deploy.sh
#
# Flags:
#   --dry-run         skip commit/push/refresh; validate + check-only.
#   --yes             auto-answer yes to all prompts (non-interactive).
#   --skip-smoke      skip the graphiti SSM smoke test (useful if SSM is
#                     being flaky and you just want the commit pushed).

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
export AWS_PROFILE=technibears
export AWS_REGION="${AWS_REGION:-us-east-1}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GATEWAY_ID="${GATEWAY_ID:-}"
MEM_ID="${MEM_ID:-}"
NAT_ID="${NAT_ID:-}"

COMMIT_SUBJECT="fix(gateway): schema-valid config + allowlist expansion + packaging"
COMMIT_BODY="render_root_openclaw_config.py: move agent/stt to schema-correct paths.
OpenClaw was silently dropping our top-level 'agent', 'stt', 'tts',
'voice_reply_mode', 'tone', 'security' blocks (evidence/25) and falling
back to openai/gpt-5.4 with no audio handler. Now emits:
  - agents.defaults.model.{primary,fallbacks} (amazon-bedrock prefix)
  - models.providers.amazon-bedrock declaration
  - audio.transcription.command = [stt-wrapper.sh, {input}]
  - memory.backend = builtin (dropped _graphiti_operator_memory; that
    sidecar is invoked directly by memory-read/write, not via OpenClaw)
Dropped tts/voice_reply_*/tone/security top-level blocks — no matching
schema paths; those responsibilities live in the bins/skills/style-card.

openclaw.service: drop WHISPER_LANGUAGE=ar so stt-wrapper lets whisper
auto-detect language per utterance. Bilingual voicenotes were being garbled
when forcing a single language.

openclaw_exec_policy.py: add two profile groups:
  AUDIO_MEDIA_PROFILES: ffmpeg, ffprobe, sox, afplay, say, whisper,
    whisper-cli, whisper-ctranslate2, opusenc, opusdec
  ARCHIVE_TRANSPORT_PROFILES: tar, gzip, gunzip, unzip, zip, rsync,
    ssh-keygen
Short-flag caveat documented — ffmpeg/sox/afplay/unzip/zip use
single-dash options this schema can't express; short flags may be
blocked at runtime. Verify post-deploy. rm/chmod/chown/ssh/nc/scp
still excluded (ask/on-miss path).

cody-refresh: include workspace/HANDOFF.md in full-mode tar (was
only in --publish), so 'cody-refresh --check' stops flagging it.

HANDOFF.md: document the cody-admin --pull-latest self-refresh loop
and the 2026-04-22 allowlist expansion."

DRY_RUN=false
AUTO_YES=false
SKIP_SMOKE=false
for arg in "$@"; do
  case "$arg" in
    --dry-run)    DRY_RUN=true ;;
    --yes|-y)     AUTO_YES=true ;;
    --skip-smoke) SKIP_SMOKE=true ;;
    -h|--help)
      awk 'NR==1{next} /^# ?/{sub(/^# ?/,""); print; next} {exit}' "$0"
      exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()    { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
ok()     { printf '\033[1;32m[ok]\033[0m   %s\n' "$*"; }
warn()   { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()    { printf '\033[1;31m[fail]\033[0m %s\n' "$*" >&2; exit 1; }
indent() { sed 's/^/    /'; }

confirm() {
  # confirm "prompt text" — returns 0 if user says yes, 1 otherwise.
  local prompt="$1"
  if "$AUTO_YES"; then
    printf '%s [auto-yes]\n' "$prompt"
    return 0
  fi
  local reply
  read -r -p "$prompt [y/N] " reply
  [[ "$reply" =~ ^[yY]([eE][sS])?$ ]]
}

need_bin() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

ssm_send() {
  # ssm_send <instance-id> <comment> <command-string> — runs synchronously.
  # Prints stdout + stderr of the remote command. Returns 1 if the command
  # failed or SSM status != Success.
  local instance="$1" comment="$2" cmd="$3"
  local cmd_id status stdout stderr
  cmd_id=$(aws ssm send-command \
    --instance-ids "$instance" \
    --document-name AWS-RunShellScript \
    --comment "$comment" \
    --parameters "commands=[\"$(printf '%s' "$cmd" | sed 's/"/\\"/g')\"]" \
    --query 'Command.CommandId' --output text 2>&1) \
    || { warn "ssm send-command failed: $cmd_id"; return 1; }
  # Poll for completion
  for _ in {1..60}; do
    sleep 2
    status=$(aws ssm get-command-invocation \
      --command-id "$cmd_id" --instance-id "$instance" \
      --query 'Status' --output text 2>/dev/null || echo InProgress)
    [[ "$status" == "Pending" || "$status" == "InProgress" ]] || break
  done
  stdout=$(aws ssm get-command-invocation \
    --command-id "$cmd_id" --instance-id "$instance" \
    --query 'StandardOutputContent' --output text 2>/dev/null || true)
  stderr=$(aws ssm get-command-invocation \
    --command-id "$cmd_id" --instance-id "$instance" \
    --query 'StandardErrorContent' --output text 2>/dev/null || true)
  [[ -n "$stdout" ]] && printf '%s\n' "$stdout"
  [[ -n "$stderr" ]] && printf '[stderr] %s\n' "$stderr" >&2
  [[ "$status" == "Success" ]]
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
need_bin aws
need_bin python3
need_bin git

[[ -d "$REPO_ROOT" ]] || die "repo not found: $REPO_ROOT"
[[ -x "$REPO_ROOT/scripts/render_root_openclaw_config.py" ]] \
  || chmod +x "$REPO_ROOT/scripts/render_root_openclaw_config.py"
[[ -x "$REPO_ROOT/scripts/validate_openclaw_config.py" ]] \
  || chmod +x "$REPO_ROOT/scripts/validate_openclaw_config.py"
[[ -x "$REPO_ROOT/scripts/cody-refresh" ]] \
  || chmod +x "$REPO_ROOT/scripts/cody-refresh"

# Prove AWS is authenticated upfront so we fail early, not mid-phase-3.
if ! aws sts get-caller-identity >/dev/null 2>&1; then
  warn "AWS not authenticated for profile '$AWS_PROFILE'."
  warn "Try: aws sso login --profile $AWS_PROFILE"
  die "bailing before touching cloud state."
fi
ok "AWS profile '$AWS_PROFILE' authenticated."

# ---------------------------------------------------------------------------
# Phase 1: Validate rendered config
# ---------------------------------------------------------------------------
log "[1/5] Rendering + validating openclaw.json..."

TMP_RENDERED="$(mktemp -t openclaw-rendered.XXXXXX.json)"
trap 'rm -f "$TMP_RENDERED"' EXIT

if ! python3 "$REPO_ROOT/scripts/render_root_openclaw_config.py" > "$TMP_RENDERED" 2>&1; then
  cat "$TMP_RENDERED"
  die "render failed — fix render_root_openclaw_config.py before continuing."
fi
ok "rendered to $TMP_RENDERED ($(wc -c < "$TMP_RENDERED") bytes)"

if ! python3 "$REPO_ROOT/scripts/validate_openclaw_config.py" "$TMP_RENDERED"; then
  die "validator rejected the rendered config — fix the config first."
fi
ok "exec policy valid."

# ---------------------------------------------------------------------------
# Phase 2: VM state
# ---------------------------------------------------------------------------
log "[2/5] Describing gateway, mem, and NAT instances..."

aws ec2 describe-instances \
  --instance-ids "$GATEWAY_ID" "$MEM_ID" "$NAT_ID" \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Name:Tags[?Key==`Name`]|[0].Value,IP:PrivateIpAddress}' \
  --output table

# Extract state per instance for the warn/prompt logic
GW_STATE=$(aws ec2 describe-instances --instance-ids "$GATEWAY_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo unknown)
MEM_STATE=$(aws ec2 describe-instances --instance-ids "$MEM_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo unknown)
NAT_STATE=$(aws ec2 describe-instances --instance-ids "$NAT_ID" \
  --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null || echo unknown)

STOPPED_IDS=()
[[ "$GW_STATE"  == "stopped" ]] && STOPPED_IDS+=("$GATEWAY_ID")
[[ "$MEM_STATE" == "stopped" ]] && STOPPED_IDS+=("$MEM_ID")
[[ "$NAT_STATE" == "stopped" ]] && STOPPED_IDS+=("$NAT_ID")

if [[ ${#STOPPED_IDS[@]} -gt 0 ]]; then
  warn "these instances are stopped: ${STOPPED_IDS[*]}"
  if confirm "Start them?"; then
    # Start NAT + mem first (gateway depends on NAT for egress and mem for graphiti).
    NON_GW=()
    for id in "${STOPPED_IDS[@]}"; do
      [[ "$id" == "$GATEWAY_ID" ]] || NON_GW+=("$id")
    done
    if [[ ${#NON_GW[@]} -gt 0 ]]; then
      log "starting NAT/mem first: ${NON_GW[*]}"
      aws ec2 start-instances --instance-ids "${NON_GW[@]}" >/dev/null
      aws ec2 wait instance-running --instance-ids "${NON_GW[@]}"
      ok "NAT/mem running."
    fi
    if [[ " ${STOPPED_IDS[*]} " == *" $GATEWAY_ID "* ]]; then
      log "waiting 30s for NAT/Neo4j to settle, then starting gateway"
      sleep 30
      aws ec2 start-instances --instance-ids "$GATEWAY_ID" >/dev/null
      aws ec2 wait instance-running --instance-ids "$GATEWAY_ID"
      ok "gateway running."
      log "waiting 60s for openclaw.service + SSM agent to come up"
      sleep 60
    fi
  else
    warn "skipping start — downstream phases may fail."
  fi
else
  ok "all three instances are running."
fi

# Confirm SSM sees the gateway before we try to send commands to it.
SSM_PING=$(aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=$GATEWAY_ID" \
  --query 'InstanceInformationList[0].PingStatus' --output text 2>/dev/null || echo none)
if [[ "$SSM_PING" != "Online" ]]; then
  warn "gateway SSM ping status: $SSM_PING (expected Online)"
  warn "SSM-dependent phases (smoke test, cody-refresh) may fail."
fi

# ---------------------------------------------------------------------------
# Phase 3: Graphiti smoke test
# ---------------------------------------------------------------------------
if "$SKIP_SMOKE"; then
  warn "[3/5] skipped (--skip-smoke)"
else
  log "[3/5] Graphiti smoke test via SSM on gateway..."

  SMOKE_CMD='sudo -u openclaw /usr/local/bin/graphiti-memory smoke --json 2>&1'
  if ssm_send "$GATEWAY_ID" "local-deploy: graphiti smoke" "$SMOKE_CMD"; then
    ok "graphiti smoke passed."
  else
    warn "graphiti smoke failed — running diagnostics..."

    log "diagnostic: which graphiti-memory"
    ssm_send "$GATEWAY_ID" "local-deploy: which graphiti-memory" \
      'which graphiti-memory; ls -la /usr/local/bin/graphiti-memory 2>&1' || true

    log "diagnostic: /creds/neo4j-password"
    ssm_send "$GATEWAY_ID" "local-deploy: creds check" \
      'ls -la /creds/neo4j-password 2>&1; stat /creds/neo4j-password 2>&1 | head -10' || true

    log "diagnostic: boto3 importable"
    ssm_send "$GATEWAY_ID" "local-deploy: boto3 check" \
      'python3 -c "import boto3; print(boto3.__version__)" 2>&1' || true

    log "diagnostic: Neo4j HTTP (\$MEM_IP:7474)"
    ssm_send "$GATEWAY_ID" "local-deploy: neo4j http" \
      'timeout 5 bash -c "</dev/tcp/$MEM_IP/7474" 2>&1 && echo "HTTP reachable" || echo "HTTP unreachable (exit $?)"' || true

    log "diagnostic: Neo4j Bolt (\$MEM_IP:7687)"
    ssm_send "$GATEWAY_ID" "local-deploy: neo4j bolt" \
      'timeout 5 bash -c "</dev/tcp/$MEM_IP/7687" 2>&1 && echo "Bolt reachable" || echo "Bolt unreachable (exit $?)"' || true

    log "diagnostic: secret read (agent-cody/neo4j-password)"
    ssm_send "$GATEWAY_ID" "local-deploy: secret read" \
      'sudo -u openclaw aws secretsmanager get-secret-value --secret-id agent-cody/neo4j-password --query "Name" --output text 2>&1' || true

    warn "diagnostics above. Common fixes:"
    warn "  - password missing: store it at /creds/neo4j-password (0600, openclaw:openclaw)"
    warn "  - secret access denied: grant gw role secretsmanager:GetSecretValue on agent-cody/neo4j-password"
    warn "  - HTTP/Bolt unreachable: mem VM security group or routing regression"
    warn "  - binary missing: run 'cody-refresh' (full mode) to reinstall graphiti-memory"
  fi
fi

# ---------------------------------------------------------------------------
# Phase 4: cody-refresh --check
# ---------------------------------------------------------------------------
if "$DRY_RUN"; then
  warn "[4/5] dry-run — skipping cody-refresh --check"
else
  log "[4/5] cody-refresh --check (drift detection, no mutations)..."
  set +e
  "$REPO_ROOT/scripts/cody-refresh" --check
  CHECK_RC=$?
  set -e
  case "$CHECK_RC" in
    0) ok "gateway matches repo — no drift." ;;
    1)
      warn "drift detected."
      if confirm "Run full 'cody-refresh' to reconcile (publishes + restarts gateway)?"; then
        "$REPO_ROOT/scripts/cody-refresh"
        log "re-checking after refresh..."
        "$REPO_ROOT/scripts/cody-refresh" --check || die "still drifted after refresh — investigate manually."
        ok "gateway matches repo after refresh."
      else
        warn "skipping refresh — gateway still drifted, no commit will be pushed."
        exit 1
      fi
      ;;
    2) die "cody-refresh --check errored (rc=2). Fix before committing." ;;
    *) die "unexpected cody-refresh --check rc=$CHECK_RC" ;;
  esac
fi

# ---------------------------------------------------------------------------
# Phase 5: Commit + push
# ---------------------------------------------------------------------------
if "$DRY_RUN"; then
  warn "[5/5] dry-run — skipping commit + push"
  log "dry-run complete."
  exit 0
fi

log "[5/5] Commit + push on main..."

cd "$REPO_ROOT"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "$CURRENT_BRANCH" != "main" ]]; then
  die "expected to be on 'main' in $REPO_ROOT, got '$CURRENT_BRANCH'"
fi

# Files we touched this work
STAGING_FILES=(
  "scripts/cody-refresh"
  "scripts/openclaw_exec_policy.py"
  "scripts/render_root_openclaw_config.py"
  "scripts/render_openclaw_config.py"
  "scripts/sync_openclaw_runtime.py"
  "scripts/validate_openclaw_config.py"
  "scripts/openclaw-init.sh"
  "scripts/provision-tenant.sh"
  "scripts/openclaw.service"
  ".github/workflows/validate-agent-infra.yml"
  "workspace/HANDOFF.md"
  "scripts/local-deploy.sh"
)

# Filter to only files that actually exist
EXISTING=()
for f in "${STAGING_FILES[@]}"; do
  [[ -f "$REPO_ROOT/$f" ]] && EXISTING+=("$f")
done

if [[ ${#EXISTING[@]} -eq 0 ]]; then
  die "none of the expected files exist to stage — did something move?"
fi

git -C "$REPO_ROOT" add "${EXISTING[@]}"

if git -C "$REPO_ROOT" diff --cached --quiet; then
  ok "nothing to commit — main is already up to date."
else
  log "staged diff summary:"
  git -C "$REPO_ROOT" diff --cached --stat | indent

  if confirm "Commit and push to origin main?"; then
    git -C "$REPO_ROOT" commit -m "$COMMIT_SUBJECT" -m "$COMMIT_BODY"
    ok "committed."
    git -C "$REPO_ROOT" push origin main
    ok "pushed to origin main."
  else
    warn "skipped commit. Staged changes remain in the index."
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# Codex/work sync — not auto-run. Print commands only.
# ---------------------------------------------------------------------------
log "codex/work sync (review + run manually)"
cat <<EOF

The codex/work worktree (if any) may also have been edited in parallel.
Decide whether to preserve codex-unique commits or fast-forward it to main.
Run these by hand:

  cd "<codex-worktree-path>"
  git status
  git log --oneline main..codex/work     # commits codex/work has that main doesn't
  git log --oneline codex/work..main     # commits main has that codex/work doesn't

  # If codex/work has no unique commits to preserve:
  git add scripts/cody-refresh scripts/openclaw_exec_policy.py \\
          scripts/render_root_openclaw_config.py scripts/render_openclaw_config.py \\
          scripts/sync_openclaw_runtime.py scripts/validate_openclaw_config.py \\
          scripts/openclaw-init.sh scripts/provision-tenant.sh scripts/openclaw.service \\
          .github/workflows/validate-agent-infra.yml \\
          workspace/HANDOFF.md
  git commit -m "sync with main: schema-valid config + allowlist expansion"
  git reset --hard main

  # If codex/work has unique work worth keeping:
  git add -u
  git commit -m "sync changes from main work"
  git merge main   # or: git rebase main
EOF

log "done."

# ===========================================================================
# Manual copy-paste reference (everything this script does, as plain shell)
# ===========================================================================
: <<'MANUAL_REFERENCE'
# All commands below assume AWS_PROFILE=technibears is exported.

export AWS_PROFILE=technibears
REPO="<your-repo-path>"
GW=$GATEWAY_ID
MEM=$MEM_ID
NAT=$NAT_ID

# [1/5] Validate rendered config
python3 "$REPO/scripts/render_root_openclaw_config.py" > /tmp/openclaw-new.json
python3 "$REPO/scripts/validate_openclaw_config.py" /tmp/openclaw-new.json
# Expect: "exec policy valid: /tmp/openclaw-new.json"

# [2/5] VM state
aws ec2 describe-instances --instance-ids "$GW" "$MEM" "$NAT" \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name,Name:Tags[?Key==`Name`]|[0].Value,IP:PrivateIpAddress}' \
  --output table

# If anything is stopped, start NAT + mem first, then gw:
aws ec2 start-instances --instance-ids "$MEM" "$NAT"
aws ec2 wait instance-running --instance-ids "$MEM" "$NAT"
sleep 30
aws ec2 start-instances --instance-ids "$GW"
aws ec2 wait instance-running --instance-ids "$GW"
sleep 60  # openclaw service warmup

# [3/5] Graphiti smoke
CMD_ID=$(aws ssm send-command --instance-ids "$GW" \
  --document-name AWS-RunShellScript \
  --comment "graphiti smoke" \
  --parameters 'commands=["sudo -u openclaw /usr/local/bin/graphiti-memory smoke --json 2>&1"]' \
  --query 'Command.CommandId' --output text)
sleep 8
aws ssm get-command-invocation --command-id "$CMD_ID" --instance-id "$GW" \
  --query 'StandardOutputContent' --output text

# If smoke fails, run these one at a time:
aws ssm send-command --instance-ids "$GW" --document-name AWS-RunShellScript \
  --comment "diag: graphiti bin" \
  --parameters 'commands=["which graphiti-memory; ls -la /usr/local/bin/graphiti-memory"]'
aws ssm send-command --instance-ids "$GW" --document-name AWS-RunShellScript \
  --comment "diag: creds" \
  --parameters 'commands=["ls -la /creds/neo4j-password"]'
aws ssm send-command --instance-ids "$GW" --document-name AWS-RunShellScript \
  --comment "diag: boto3" \
  --parameters 'commands=["python3 -c \"import boto3; print(boto3.__version__)\""]'
aws ssm send-command --instance-ids "$GW" --document-name AWS-RunShellScript \
  --comment "diag: neo4j http" \
  --parameters 'commands=["timeout 5 bash -c \"</dev/tcp/$MEM_IP/7474\" && echo http-up || echo http-down"]'
aws ssm send-command --instance-ids "$GW" --document-name AWS-RunShellScript \
  --comment "diag: neo4j bolt" \
  --parameters 'commands=["timeout 5 bash -c \"</dev/tcp/$MEM_IP/7687\" && echo bolt-up || echo bolt-down"]'
aws ssm send-command --instance-ids "$GW" --document-name AWS-RunShellScript \
  --comment "diag: secret" \
  --parameters 'commands=["sudo -u openclaw aws secretsmanager get-secret-value --secret-id agent-cody/neo4j-password --query Name --output text"]'
# For each, grab CMD_ID and fetch output with get-command-invocation.

# [4/5] cody-refresh
"$REPO/scripts/cody-refresh" --check
# 0 = clean, 1 = drift (then run "$REPO/scripts/cody-refresh" to reconcile,
# then re-check), 2 = error.

# [5/5] Commit + push
cd "$REPO"
git status
git add scripts/cody-refresh scripts/openclaw_exec_policy.py \
        scripts/render_root_openclaw_config.py scripts/render_openclaw_config.py \
        scripts/sync_openclaw_runtime.py scripts/validate_openclaw_config.py \
        scripts/openclaw-init.sh scripts/provision-tenant.sh scripts/openclaw.service \
        .github/workflows/validate-agent-infra.yml \
        workspace/HANDOFF.md scripts/local-deploy.sh
git diff --cached --stat
git commit -F- <<'MSG'
fix(gateway): schema-valid config + allowlist expansion + packaging

render_root_openclaw_config.py: move agent/stt to schema-correct paths.
openclaw.service: drop WHISPER_LANGUAGE=ar.
openclaw_exec_policy.py: add AUDIO_MEDIA_PROFILES + ARCHIVE_TRANSPORT_PROFILES.
cody-refresh: include workspace/HANDOFF.md in full-mode tar.
HANDOFF.md: document cody-admin --pull-latest self-refresh loop.
MSG
git push origin main

# Codex/work (if applicable)
cd "<codex-worktree-path>"
git status
git log --oneline main..codex/work
git log --oneline codex/work..main
# If codex/work is just staging:
git add -u && git commit -m "sync with main" && git reset --hard main
# If codex/work has unique commits:
git add -u && git commit -m "sync" && git merge main
MANUAL_REFERENCE
