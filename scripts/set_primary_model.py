#!/usr/bin/env python3
"""Switch the primary model in the managed OpenClaw config.

Single source of truth used by both `cody-admin --set-model` (CLI) and
the `model-switch` skill (Telegram /model command).

The MODEL_REGISTRY is imported from render_root_openclaw_config so the
aliases match what the renderer declares.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from render_root_openclaw_config import FALLBACK_ALIASES, MODEL_REGISTRY

CONFIG_PATH = Path("/opt/openclaw/openclaw.json")
LOG_PATH = Path("/var/log/openclaw/model-switches.log")
ADMIN_HELPER = "/usr/local/sbin/openclaw-admin-helper"


def resolve_alias(alias_or_id: str) -> str:
    """Return the full provider/model-id for an alias or pass through a known full id."""
    if alias_or_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[alias_or_id][0]
    for ref, _, _ in MODEL_REGISTRY.values():
        if ref == alias_or_id:
            return alias_or_id
    raise ValueError(
        f"unknown model {alias_or_id!r}; choose from "
        f"{sorted(MODEL_REGISTRY)} or a full provider/model-id"
    )


def _atomic_write(path: Path, data: str) -> None:
    """Write `data` to `path` atomically, preserving original owner/group/mode.

    The previous version left the new file root:root 0600 because tempfile.mkstemp
    creates with 0600 and os.replace preserves that. With the openclaw service
    running as the openclaw user, that triggered PermissionError on every restart
    and put the gateway in a 5,000+ restart crash loop on 2026-04-25/26.
    """
    # Snapshot original metadata BEFORE replace, so we can restore it after.
    try:
        st = path.stat()
        original_uid = st.st_uid
        original_gid = st.st_gid
        original_mode = st.st_mode & 0o777
    except FileNotFoundError:
        original_uid = original_gid = None
        original_mode = 0o644  # sensible default if file is being created

    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        # Set perms BEFORE replace so the destination always lands with the
        # right mode — no window where the file is unreadable.
        os.chmod(tmp, original_mode)
        if original_uid is not None and original_gid is not None:
            try:
                os.chown(tmp, original_uid, original_gid)
            except PermissionError:
                # Non-root caller can't chown to a different uid; that's OK
                # if we're already running as the file owner.
                pass
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def _log_switch(record: dict) -> None:
    if not LOG_PATH.parent.is_dir():
        return
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _trigger_restart() -> None:
    """Invoke the admin helper directly with subprocess (no shell, no injection)."""
    subprocess.run(
        ["sudo", "-n", ADMIN_HELPER, "restart"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def set_primary_model(
    alias_or_id: str,
    *,
    config_path: Path = CONFIG_PATH,
    dry_run: bool = False,
    restart: bool = True,
) -> dict:
    """Update agents.defaults.model.primary; return the new primary + fallback chain."""
    primary = resolve_alias(alias_or_id)
    fallbacks = [
        MODEL_REGISTRY[a][0] for a in FALLBACK_ALIASES if MODEL_REGISTRY[a][0] != primary
    ]

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    cfg.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
    cfg["agents"]["defaults"]["model"]["primary"] = primary
    cfg["agents"]["defaults"]["model"]["fallbacks"] = fallbacks

    result = {
        "primary": primary,
        "fallbacks": fallbacks,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
    }

    if dry_run:
        return result

    _atomic_write(config_path, json.dumps(cfg, indent=2) + "\n")
    _log_switch(result)

    if restart:
        _trigger_restart()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch the primary model")
    parser.add_argument("alias_or_id", help="Model alias (opus, sonnet, etc.) or full provider/id")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = set_primary_model(
            args.alias_or_id,
            config_path=Path(args.config),
            dry_run=args.dry_run,
            restart=not args.no_restart,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"primary -> {result['primary']}")
        print(f"fallbacks -> {result['fallbacks']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
