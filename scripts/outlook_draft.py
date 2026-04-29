#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def parse_csv(raw: str) -> list[dict[str, dict[str, str]]]:
    items = []
    for value in raw.split(","):
        address = value.strip()
        if address:
            items.append({"emailAddress": {"address": address}})
    return items


def get_graph_token() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    helper = os.path.join(script_dir, "graph-token-fresh.py")
    if not os.path.exists(helper):
        helper = "/opt/openclaw/bin/graph-token-fresh.py"
    proc = subprocess.run(
        [sys.executable, helper],
        capture_output=True,
        text=True,
        env={**os.environ, "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1")},
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(proc.stderr.strip() or "could not obtain Graph token")
    return proc.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an Outlook draft via Microsoft Graph")
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--cc", default="")
    parser.add_argument("--content-type", default="Text", choices=["Text", "HTML"])
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    token = get_graph_token()
    payload = {
        "subject": args.subject,
        "body": {"contentType": args.content_type, "content": args.body},
        "toRecipients": parse_csv(args.to),
        "ccRecipients": parse_csv(args.cc),
    }

    req = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": 'IdType="ImmutableId"',
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", "replace")
        print(error_body, file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parsed = json.loads(body)
    draft_id = parsed.get("id")
    if not draft_id:
        print(body, file=sys.stderr)
        return 1

    result = {
        "ok": True,
        "draft_id": draft_id,
        "web_link": parsed.get("webLink", ""),
        "subject": parsed.get("subject", args.subject),
        "to": args.to,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Draft created in Outlook.")
        print(f"draft_id={result['draft_id']}")
        print(f"web_link={result['web_link']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
