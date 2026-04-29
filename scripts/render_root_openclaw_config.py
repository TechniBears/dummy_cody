#!/usr/bin/env python3
"""Render the root OpenClaw gateway config.

Single source of truth for the model lineup lives in MODEL_REGISTRY below.
Bedrock model IDs MUST be inference-profile form (us.* or global.*); raw
model IDs (anthropic.claude-...) are rejected by Bedrock for on-demand
throughput and were the cause of the 2026-04-25 silent agent-loop failure
(see docs/superpowers/specs/2026-04-25-cody-restoration-and-model-router-design.md).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from openclaw_exec_policy import build_exec_config

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "skills"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _load_skill_metadata(skill_md: Path) -> dict | None:
    """Parse SKILL.md frontmatter and return the openclaw metadata dict if present."""
    text = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    body = match.group(1)
    out: dict = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    raw_metadata = out.get("metadata")
    if not raw_metadata:
        return None
    try:
        meta = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return None
    return meta.get("openclaw")


def _build_agents_list() -> list[dict]:
    """Walk SKILLS_ROOT; emit agents.list[] entry for each skill with metadata.openclaw.model."""
    if not SKILLS_ROOT.is_dir():
        return []
    out = []
    for skill_md in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        meta = _load_skill_metadata(skill_md)
        if not meta or "model" not in meta:
            continue
        skill_id = skill_md.parent.name
        out.append({
            "id": skill_id,
            "model": {"primary": meta["model"]},
        })
    return out


def _collect_skill_required_bins() -> list[str]:
    """Walk SKILLS_ROOT; collect every metadata.openclaw.requires.bins entry.

    Used to drive safeBins so any new skill is auto-allowlisted as soon as it
    declares its bins in SKILL.md. Hand-written profiles in openclaw_exec_policy
    still take precedence; this just ensures the bin name lands in safeBins.
    """
    if not SKILLS_ROOT.is_dir():
        return []
    bins: set[str] = set()
    for skill_md in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
        meta = _load_skill_metadata(skill_md)
        if not meta:
            continue
        requires = meta.get("requires") or {}
        for b in requires.get("bins") or []:
            if isinstance(b, str) and b:
                bins.add(b)
    return sorted(bins)

# alias -> (provider/full-id, role description, default cacheRetention or None)
MODEL_REGISTRY: dict[str, tuple[str, str, str | None]] = {
    "opus":      ("amazon-bedrock/us.anthropic.claude-opus-4-6-v1",              "Primary daily driver",      "short"),
    "opus-next": ("amazon-bedrock/us.anthropic.claude-opus-4-7",                 "Premium experimental",      "short"),
    "sonnet":    ("amazon-bedrock/us.anthropic.claude-sonnet-4-6",               "Quick reasoning",           "short"),
    "sonnet-1m": ("amazon-bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0", "Long-context research",     "short"),
    "haiku":     ("amazon-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0",  "Compaction and small ops",  "short"),
    "gemma":     ("ollama/gemma3:4b",                                             "Local sovereign fallback",  None),
}

PRIMARY_ALIAS = "opus"
FALLBACK_ALIASES = ["sonnet", "haiku", "gemma"]

STT_WRAPPER_PATH = "/opt/openclaw/bin/stt-wrapper.sh"


def _model_ref(alias: str) -> str:
    return MODEL_REGISTRY[alias][0]


def _bedrock_models_block() -> list[dict]:
    return [
        {"id": ref.split("/", 1)[1], "name": role}
        for alias, (ref, role, _) in MODEL_REGISTRY.items()
        if ref.startswith("amazon-bedrock/")
    ]


def _ollama_models_block() -> list[dict]:
    return [
        {"id": ref.split("/", 1)[1], "name": role}
        for alias, (ref, role, _) in MODEL_REGISTRY.items()
        if ref.startswith("ollama/")
    ]


def _per_model_defaults() -> dict:
    out: dict = {}
    for alias, (ref, _, retention) in MODEL_REGISTRY.items():
        if retention is None:
            continue
        out[ref] = {"params": {"cacheRetention": retention}}
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render the root OpenClaw gateway config")
    parser.add_argument("--output", help="Write JSON to this file instead of stdout")
    return parser


def build_config() -> dict:
    return {
        "agents": {
            "defaults": {
                "sandbox": {"mode": "off"},
                "model": {
                    "primary": _model_ref(PRIMARY_ALIAS),
                    "fallbacks": [_model_ref(a) for a in FALLBACK_ALIASES],
                },
                "models": _per_model_defaults(),
            },
            "list": _build_agents_list(),
        },
        "models": {
            "providers": {
                "amazon-bedrock": {
                    # Schema (verified empirically from a 227-restart crash loop on 2026-04-26):
                    #   - baseUrl: required string. Region is derived from this URL.
                    #   - api: required for streaming (bedrock-converse-stream).
                    #   - auth: STRING enum, NOT a dict. "aws-sdk" uses the default
                    #     AWS credential chain — IMDSv2 from the EC2 instance role.
                    #   - "region" is NOT a valid key (use baseUrl).
                    "baseUrl": "https://bedrock-runtime.us-east-1.amazonaws.com",
                    "api": "bedrock-converse-stream",
                    "auth": "aws-sdk",
                    "models": _bedrock_models_block(),
                },
                "ollama": {
                    "baseUrl": "http://127.0.0.1:11434",
                    "models": _ollama_models_block(),
                },
            }
        },
        "plugins": {
            "entries": {
                "amazon-bedrock": {"enabled": True},
                "ollama": {"enabled": True},
            }
        },
        "channels": {
            "telegram": {
                "enabled": True,
                "dmPolicy": "open",
                "allowFrom": [],
                "execApprovals": {
                    "enabled": False,
                    "approvers": [],
                    "target": "channel",
                },
            },
        },
        "gateway": {
            "bindHost": "127.0.0.1",
            "port": 18789,
        },
        "audio": {
            "transcription": {
                "command": [STT_WRAPPER_PATH, "{input}"],
                "timeoutSeconds": 120,
            }
        },
        "tools": {
            "exec": build_exec_config(
                path_prepend=["/usr/local/bin", "/opt/openclaw/bin"],
                include_root_admin=True,
                ask="off",
                extra_skill_bins=_collect_skill_required_bins(),
            ),
        },
        "memory": {
            "backend": "builtin",
        },
    }


def main() -> int:
    args = build_parser().parse_args()
    rendered = json.dumps(build_config(), indent=2) + "\n"
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        return 0
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
