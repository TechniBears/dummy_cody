#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate OpenClaw exec allowlist policy")
    parser.add_argument("config", help="Path to openclaw.json")
    return parser


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"ERROR: config not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: invalid JSON in {path}: {exc}")


def validate_exec_policy(config: dict) -> list[str]:
    exec_cfg = ((config.get("tools") or {}).get("exec") or {})
    security = exec_cfg.get("security", "allowlist")
    errors: list[str] = []

    if security not in ("deny", "allowlist", "full"):
        errors.append(f"tools.exec.security must be deny, allowlist, or full; got {security!r}")

    if security == "full":
        return errors

    safe_bins = exec_cfg.get("safeBins")
    profiles = exec_cfg.get("safeBinProfiles")

    if not isinstance(safe_bins, list) or not safe_bins:
        errors.append("tools.exec.safeBins must be a non-empty list")
        return errors
    if not isinstance(profiles, dict) or not profiles:
        errors.append("tools.exec.safeBinProfiles must be a non-empty object")
        return errors

    missing_profiles = [name for name in safe_bins if name not in profiles]
    if missing_profiles:
        errors.append(f"missing safeBinProfiles for: {', '.join(sorted(missing_profiles))}")

    orphan_profiles = [name for name in profiles if name not in safe_bins]
    if orphan_profiles:
        errors.append(f"profiles without safeBins entries: {', '.join(sorted(orphan_profiles))}")

    for name, profile in sorted(profiles.items()):
        if not isinstance(profile, dict):
            errors.append(f"{name}: profile must be an object")
            continue
        if not isinstance(profile.get("minPositional"), int):
            errors.append(f"{name}: minPositional must be an integer")
        if not isinstance(profile.get("maxPositional"), int):
            errors.append(f"{name}: maxPositional must be an integer")
        allowed_value_flags = profile.get("allowedValueFlags")
        if not isinstance(allowed_value_flags, list):
            errors.append(f"{name}: allowedValueFlags must be a list")
        elif any(not isinstance(flag, str) or not flag.startswith("--") for flag in allowed_value_flags):
            errors.append(f"{name}: allowedValueFlags must contain only long flags")

    return errors


def validate_managed_shape(config: dict) -> list[str]:
    errors: list[str] = []
    agents_defaults = ((config.get("agents") or {}).get("defaults") or {})
    model_cfg = agents_defaults.get("model") or {}
    gateway_cfg = config.get("gateway") or {}
    provider_cfg = (((config.get("models") or {}).get("providers") or {}).get("ollama") or {})
    plugin_cfg = ((((config.get("plugins") or {}).get("entries") or {}).get("ollama")) or {})
    audio_cfg = ((config.get("audio") or {}).get("transcription") or {})
    channels_cfg = config.get("channels") or {}
    legacy_keys = [
        key
        for key in (
            "agent",
            "stt",
            "tts",
            "voice_reply_mode",
            "voice_reply_override_per_thread",
            "tone",
            "security",
        )
        if key in config
    ]

    if not isinstance(model_cfg.get("primary"), str) or "/" not in model_cfg["primary"]:
        errors.append("agents.defaults.model.primary must be a provider/model string")
    fallbacks = model_cfg.get("fallbacks")
    if not isinstance(fallbacks, list) or not all(isinstance(item, str) and "/" in item for item in fallbacks):
        errors.append("agents.defaults.model.fallbacks must be a list of provider/model strings")

    if not isinstance(gateway_cfg.get("port"), int):
        errors.append("gateway.port must be an integer")
    if not any(key in gateway_cfg for key in ("bind", "bindHost", "customBindHost")):
        errors.append("gateway must define one of bind, bindHost, or customBindHost")

    provider_models = provider_cfg.get("models")
    if not isinstance(provider_models, list) or not provider_models:
        errors.append("models.providers.ollama.models must be a non-empty list")
    if plugin_cfg.get("enabled") is not True:
        errors.append("plugins.entries.ollama.enabled must be true")

    command = audio_cfg.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
        errors.append("audio.transcription.command must be a non-empty string list")

    whatsapp_cfg = channels_cfg.get("whatsapp")
    if isinstance(whatsapp_cfg, dict):
        extra_keys = sorted(set(whatsapp_cfg.keys()) - {"enabled"})
        if extra_keys:
            errors.append(f"channels.whatsapp may only declare enabled when disabled; found extra keys: {', '.join(extra_keys)}")

    if legacy_keys:
        errors.append(f"legacy unsupported top-level keys present: {', '.join(legacy_keys)}")

    return errors


def main() -> int:
    args = build_parser().parse_args()
    config_path = Path(args.config)
    config = load_config(config_path)
    errors = validate_exec_policy(config)
    errors.extend(validate_managed_shape(config))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"config valid: {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
