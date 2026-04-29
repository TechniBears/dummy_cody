#!/usr/bin/env python3
"""Render a tenant-specific OpenClaw config.

Reuses MODEL_REGISTRY and helpers from render_root_openclaw_config so the
model lineup stays in lockstep across root and tenant configs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from openclaw_exec_policy import build_exec_config
from render_root_openclaw_config import (
    FALLBACK_ALIASES,
    PRIMARY_ALIAS,
    _bedrock_models_block,
    _build_agents_list,
    _collect_skill_required_bins,
    _model_ref,
    _ollama_models_block,
    _per_model_defaults,
)


def parse_approvers(raw: str) -> list[int]:
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a tenant-specific OpenClaw config")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--principal-name", required=True)
    parser.add_argument("--principal-email", required=True)
    parser.add_argument("--principal-handle", default="")
    parser.add_argument("--gateway-port", required=True, type=int)
    parser.add_argument("--approvers", default="")
    parser.add_argument("--stt-language", default="en")
    parser.add_argument("--style-card-path", default="/creds/style-card.json")
    parser.add_argument("--neo4j-password-file", default="/creds/neo4j-password")
    parser.add_argument("--graphiti-url", default="http://localhost:7474")
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    approvers = parse_approvers(args.approvers)
    config = {
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
                "allowFrom": approvers if approvers else [],
                "execApprovals": {
                    "enabled": False,
                    "approvers": approvers,
                    "target": "channel",
                },
            },
        },
        "gateway": {"bindHost": "127.0.0.1", "port": args.gateway_port},
        "audio": {
            "transcription": {
                "command": [f"/opt/openclaw-tenants/{args.tenant}/bin/stt-wrapper.sh", "{input}"],
                "timeoutSeconds": 120,
            }
        },
        "tools": {
            "exec": build_exec_config(
                path_prepend=["/usr/local/bin", f"/opt/openclaw-tenants/{args.tenant}/bin"],
                ask="off",
                extra_skill_bins=_collect_skill_required_bins(),
            ),
        },
        "memory": {
            "backend": "builtin",
        },
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
