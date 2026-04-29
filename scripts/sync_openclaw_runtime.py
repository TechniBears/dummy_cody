#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_SCHEMA_KEYS = ("models", "plugins", "session", "wizard", "skills", "meta")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync a managed OpenClaw config into a runtime config")
    parser.add_argument("--managed-config", required=True, help="Path to the managed config JSON")
    parser.add_argument("--runtime-root", required=True, help="Path to the runtime root (contains openclaw.json)")
    parser.add_argument("--runtime-workspace", required=True, help="Path to the runtime workspace directory")
    return parser


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def looks_like_runtime_schema(data: Any) -> bool:
    return isinstance(data, dict) and any(key in data for key in RUNTIME_SCHEMA_KEYS)


def find_runtime_base(runtime_root: Path) -> dict[str, Any] | None:
    runtime_cfg_path = runtime_root / "openclaw.json"
    candidates = [runtime_cfg_path, *sorted(runtime_root.glob("openclaw.json.bak*"))]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            data = load_json(candidate)
        except Exception:
            continue
        if looks_like_runtime_schema(data):
            return data
    return None


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = {k: copy.deepcopy(v) for k, v in base.items()}
        for key, value in overlay.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
    return copy.deepcopy(overlay)


def normalize_gateway(gateway: dict[str, Any]) -> dict[str, Any]:
    gateway = copy.deepcopy(gateway)
    bind_host = gateway.pop("bindHost", None)
    if "bind" not in gateway:
        if bind_host and bind_host not in ("127.0.0.1", "localhost", "::1"):
            gateway["bind"] = "custom"
            gateway.setdefault("customBindHost", bind_host)
        else:
            gateway["bind"] = "loopback"
    elif gateway.get("bind") == "custom" and bind_host and "customBindHost" not in gateway:
        gateway["customBindHost"] = bind_host

    gateway.setdefault("mode", "local")
    auth = gateway.get("auth")
    if not isinstance(auth, dict):
        gateway["auth"] = {"mode": "token"}
    else:
        auth.setdefault("mode", "token")
    return gateway


def normalize_managed_config(managed_cfg: dict[str, Any], runtime_workspace: str) -> dict[str, Any]:
    normalized = copy.deepcopy(managed_cfg)
    normalized["gateway"] = normalize_gateway((normalized.get("gateway") or {}))
    agents = normalized.setdefault("agents", {})
    defaults = agents.setdefault("defaults", {})
    defaults.setdefault("workspace", runtime_workspace)
    normalized.setdefault("session", {}).setdefault("dmScope", "per-channel-peer")
    normalized.setdefault("skills", {}).setdefault("install", {}).setdefault("nodeManager", "npm")
    normalized.setdefault("meta", {})
    normalized.setdefault("wizard", {})
    normalized.setdefault("tools", {}).setdefault("profile", "coding")
    return normalized


def backup_non_runtime_config(runtime_cfg_path: Path) -> None:
    if not runtime_cfg_path.is_file():
        return
    try:
        current = load_json(runtime_cfg_path)
    except Exception:
        current = None
    if current is not None and not looks_like_runtime_schema(current):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
        shutil.copy2(runtime_cfg_path, runtime_cfg_path.parent / f"openclaw.json.clobbered.{stamp}")


def main() -> int:
    args = build_parser().parse_args()
    managed_cfg_path = Path(args.managed_config)
    runtime_root = Path(args.runtime_root)
    runtime_cfg_path = runtime_root / "openclaw.json"
    runtime_root.mkdir(parents=True, exist_ok=True)

    managed_cfg = load_json(managed_cfg_path)
    normalized = normalize_managed_config(managed_cfg, args.runtime_workspace)
    base_cfg = find_runtime_base(runtime_root)

    backup_non_runtime_config(runtime_cfg_path)
    merged = deep_merge(base_cfg or {}, normalized)

    # Managed config is authoritative for these sections. We intentionally do
    # not carry forward stale channel/plugin/model entries from runtime state
    # because that is how old WhatsApp keys and old model selections survive a
    # deploy even after the managed config removed them.
    for section in ("channels", "models", "plugins", "audio", "memory"):
        if section in normalized:
            merged[section] = copy.deepcopy(normalized[section])

    if "tools" in normalized:
        preserved_tools = {}
        if isinstance(base_cfg, dict):
            base_tools = base_cfg.get("tools") or {}
            if isinstance(base_tools, dict):
                preserved_tools = {k: copy.deepcopy(v) for k, v in base_tools.items() if k != "exec"}
        merged["tools"] = deep_merge(preserved_tools, normalized["tools"])

    runtime_cfg_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
