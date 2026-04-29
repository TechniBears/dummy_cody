#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write Agent Cody Graphiti memory")
    parser.add_argument("--entity", required=True)
    parser.add_argument("--entity-type", default="entity")
    parser.add_argument("--predicate", required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--target-entity")
    parser.add_argument("--target-type")
    parser.add_argument("--source", default="manual")
    parser.add_argument("--source-type", default="operator")
    parser.add_argument("--quote")
    parser.add_argument("--confidence", default="0.9")
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
        "write-fact",
        "--group-id",
        os.environ.get("GRAPHITI_GROUP_ID", "agent-cody"),
        "--entity",
        args.entity,
        "--entity-type",
        args.entity_type,
        "--predicate",
        args.predicate,
        "--value",
        args.value,
        "--source",
        args.source,
        "--source-type",
        args.source_type,
        "--confidence",
        str(args.confidence),
    ]
    if args.target_entity:
        cmd.extend(["--target-entity", args.target_entity])
    if args.target_type:
        cmd.extend(["--target-type", args.target_type])
    if args.quote:
        cmd.extend(["--quote", args.quote])
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
