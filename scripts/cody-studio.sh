#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
GUIDE_HTML="$REPO_ROOT/operator-studio/index.html"
GUIDE_MD="$REPO_ROOT/docs/09-operator-studio.md"
GRAPHITI_GUIDE_MD="$REPO_ROOT/docs/10-graphiti-guide.md"
SOUL_FILE="$REPO_ROOT/workspace/SOUL.md"
AGENTS_FILE="$REPO_ROOT/workspace/AGENTS.md"
ROOT_CONFIG_RENDERER="$REPO_ROOT/scripts/render_root_openclaw_config.py"
TENANT_CONFIG_RENDERER="$REPO_ROOT/scripts/render_openclaw_config.py"
EXEC_POLICY_FILE="$REPO_ROOT/scripts/openclaw_exec_policy.py"
LEGACY_CONFIG_NOTE="$REPO_ROOT/scripts/cody-config.batch.LEGACY.md"
GRAPHITI_SCRIPT="$REPO_ROOT/scripts/graphiti_memory.py"
DEFAULT_MEMORY_DIR="${CLAUDE_FLOW_MEMORY_DIR:-$SCRIPT_DIR/.swarm}"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/cody-studio.sh open
  ./scripts/cody-studio.sh doc [operator|graphiti|legacy-config]
  ./scripts/cody-studio.sh edit soul
  ./scripts/cody-studio.sh edit agents
  ./scripts/cody-studio.sh edit config
  ./scripts/cody-studio.sh edit exec-policy
  ./scripts/cody-studio.sh status
  ./scripts/cody-studio.sh paths
  ./scripts/cody-studio.sh memory-doctor [memory-dir]
  ./scripts/cody-studio.sh graphiti <command> [args...]
USAGE
}

open_path() {
  local target="$1"
  if command -v open >/dev/null 2>&1; then
    open "$target"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$target"
  else
    printf '%s\n' "$target"
  fi
}

edit_file() {
  local target="$1"
  if [[ -n "${EDITOR:-}" ]]; then
    "$EDITOR" "$target"
  else
    printf 'Set $EDITOR to open files directly. Path: %s\n' "$target"
  fi
}

memory_doctor() {
  local memory_dir="${1:-$DEFAULT_MEMORY_DIR}"
  local db="$memory_dir/memory.db"
  local meta="$memory_dir/hnsw.metadata.json"

  printf 'Memory root: %s\n' "$memory_dir"

  if [[ ! -f "$db" ]]; then
    printf 'No memory.db found.\n'
    return 1
  fi

  if command -v sqlite3 >/dev/null 2>&1; then
    local rows unique namespaces
    rows=$(sqlite3 "$db" 'select count(*) from memory_entries;')
    unique=$(sqlite3 "$db" 'select count(distinct namespace || ":" || key) from memory_entries;')
    namespaces=$(sqlite3 "$db" 'select namespace || " (" || count(*) || ")" from memory_entries group by namespace order by namespace;')
    printf 'SQLite rows: %s\n' "$rows"
    printf 'Unique namespace:key rows: %s\n' "$unique"
    printf 'Namespaces:\n%s\n' "$namespaces"
  else
    printf 'sqlite3 not installed; skipping DB inspection.\n'
  fi

  if [[ -f "$meta" ]]; then
    python3 - "$meta" <<'PY'
import collections
import json
import sys

path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as handle:
    data = json.load(handle)

keys = []
for item in data:
    if isinstance(item, list) and len(item) == 2 and isinstance(item[1], dict):
        payload = item[1]
        key = payload.get('key', '<missing>')
        namespace = payload.get('namespace', 'default')
        keys.append(f"{namespace}:{key}")

counter = collections.Counter(keys)
duplicates = sorted((item for item in counter.items() if item[1] > 1), key=lambda item: (-item[1], item[0]))

print(f"HNSW metadata entries: {len(keys)}")
if duplicates:
    print('Duplicate keys in HNSW metadata:')
    for key, count in duplicates:
        print(f"  - {key} x{count}")
    print('Recommendation: use upserts for repeated keys and rebuild or clean the vector index when duplicates appear.')
else:
    print('HNSW metadata duplicates: none')
PY
  else
    printf 'No hnsw.metadata.json found.\n'
  fi
}

case "${1:-open}" in
  open)
    open_path "$GUIDE_HTML"
    ;;
  doc)
    case "${2:-operator}" in
      operator)
        open_path "$GUIDE_MD"
        ;;
      graphiti)
        open_path "$GRAPHITI_GUIDE_MD"
        ;;
      legacy-config)
        open_path "$LEGACY_CONFIG_NOTE"
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  edit)
    case "${2:-}" in
      soul)
        edit_file "$SOUL_FILE"
        ;;
      agents)
        edit_file "$AGENTS_FILE"
        ;;
      config)
        edit_file "$ROOT_CONFIG_RENDERER"
        ;;
      exec-policy)
        edit_file "$EXEC_POLICY_FILE"
        ;;
      *)
        usage
        exit 1
        ;;
    esac
    ;;
  status)
    cat <<STATUS_EOF
Agent Cody operator surfaces:
- Soul:   $SOUL_FILE
- Agents: $AGENTS_FILE
- Root config renderer:   $ROOT_CONFIG_RENDERER
- Tenant config renderer: $TENANT_CONFIG_RENDERER
- Exec policy:            $EXEC_POLICY_FILE
- Legacy batch note:      $LEGACY_CONFIG_NOTE
- Guide:  $GUIDE_HTML
- Graphiti guide: $GRAPHITI_GUIDE_MD
- Graphiti CLI:   $GRAPHITI_SCRIPT

Current memory posture:
- OpenClaw runtime memory: builtin
- Graph memory path: graphiti-memory sidecar on Neo4j
- claude-flow role: secondary project + operator memory

Useful commands:
- ./scripts/cody-studio.sh doc graphiti
- ./scripts/cody-studio.sh doc legacy-config
- ./scripts/cody-studio.sh edit config
- ./scripts/cody-studio.sh edit exec-policy
- ./scripts/cody-studio.sh graphiti smoke
- ./scripts/cody-studio.sh graphiti read-facts --query "example-contact"
STATUS_EOF
    ;;
  paths)
    printf '%s\n' "$SOUL_FILE" "$AGENTS_FILE" "$ROOT_CONFIG_RENDERER" "$TENANT_CONFIG_RENDERER" "$EXEC_POLICY_FILE" "$LEGACY_CONFIG_NOTE" "$GUIDE_HTML" "$GUIDE_MD" "$GRAPHITI_GUIDE_MD" "$GRAPHITI_SCRIPT"
    ;;
  memory-doctor)
    memory_doctor "${2:-$DEFAULT_MEMORY_DIR}"
    ;;
  graphiti)
    shift
    if [[ ! -f "$GRAPHITI_SCRIPT" ]]; then
      printf 'Graphiti CLI not found: %s\n' "$GRAPHITI_SCRIPT" >&2
      exit 1
    fi
    exec python3 "$GRAPHITI_SCRIPT" "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
