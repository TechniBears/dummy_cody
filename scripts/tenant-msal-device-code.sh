#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TENANT="${1:-}"
[[ -n "$TENANT" ]] || { echo "usage: $0 <tenant-slug> [extra msal-device-code.py args unsupported]" >&2; exit 2; }

SERVICE_ENV="/opt/openclaw-tenants/$TENANT/service.env"
GRAPH_SECRET_ID="agent-cody/tenants/$TENANT/graph-msal-token-cache"

if [[ -f "$SERVICE_ENV" ]]; then
  # shellcheck disable=SC1090
  source "$SERVICE_ENV"
fi

export GRAPH_MSAL_SECRET="${GRAPH_MSAL_SECRET_ID:-$GRAPH_SECRET_ID}"
exec python3 "$SCRIPT_DIR/msal-device-code.py"
