#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read Agent Cody Graphiti memory")
    parser.add_argument("--query", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--include-history", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    # --json is a top-level flag on graphiti-memory; argparse requires it
    # BEFORE the subcommand, otherwise the subparser rejects it as unknown.
    cmd = ["graphiti-memory"]
    if args.json:
        cmd.append("--json")
    cmd += [
        "read-facts",
        "--group-id",
        os.environ.get("GRAPHITI_GROUP_ID", "agent-cody"),
        "--query",
        args.query,
        "--limit",
        str(args.limit),
    ]
    if args.as_of:
        cmd.extend(["--as-of", args.as_of])
    if args.include_history:
        cmd.append("--include-history")
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
