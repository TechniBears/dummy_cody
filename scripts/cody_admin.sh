#!/usr/bin/env bash
set -euo pipefail

HELPER="/usr/local/sbin/openclaw-admin-helper"

usage() {
  cat <<'EOF'
Usage:
  cody-admin --status [--json]
  cody-admin --restart [--json]
  cody-admin --refresh-snapshot [--json]
  cody-admin --pull-latest [--json]
  cody-admin --set-model <alias|provider/id> [--json]

Model aliases: opus | opus-next | sonnet | sonnet-1m | haiku | gemma
EOF
  exit 2
}

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing required command: $1" >&2; exit 1; }
}

need sudo
[[ -x "$HELPER" ]] || { echo "helper not installed: $HELPER" >&2; exit 1; }

action=""
model_arg=""
json_flag=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --status|--restart|--refresh-snapshot|--pull-latest)
      [[ -z "$action" ]] || usage
      action="${1#--}"
      shift
      ;;
    --set-model)
      [[ -z "$action" ]] || usage
      action="set-model"
      shift
      model_arg="${1:-}"
      [[ -n "$model_arg" ]] || { echo "--set-model requires a model alias or full id" >&2; usage; }
      shift
      ;;
    --json)
      json_flag="--json"
      shift
      ;;
    *)
      usage
      ;;
  esac
done

[[ -n "$action" ]] || usage

if [[ "$action" == "set-model" ]]; then
  exec sudo -n "$HELPER" "$action" "$model_arg" ${json_flag:+$json_flag}
else
  exec sudo -n "$HELPER" "$action" ${json_flag:+$json_flag}
fi
