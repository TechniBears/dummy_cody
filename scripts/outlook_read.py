#!/usr/bin/env python3
"""Read Outlook messages via Microsoft Graph.

Supports:
  --list                List recent inbox messages
  --message <id>        Fetch full body of a specific message
  --limit <n>           Limit number of messages (default 10)
  --json                Output raw JSON
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def log(msg: str) -> None:
    print(f"[outlook-read] {msg}", file=sys.stderr, flush=True)


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


def graph_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Prefer": 'IdType="ImmutableId"',
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def list_inbox(token: str, limit: int) -> list[dict]:
    params = {
        "$top": str(limit),
        "$select": "id,subject,bodyPreview,from,receivedDateTime,isRead,importance,webLink",
        "$orderby": "receivedDateTime desc",
    }
    url = f"{GRAPH_BASE}/me/mailFolders/inbox/messages?" + urllib.parse.urlencode(params, safe=",")
    return graph_get(url, token).get("value") or []


def get_message(token: str, message_id: str) -> dict:
    url = f"{GRAPH_BASE}/me/messages/{message_id}"
    return graph_get(url, token)


def main() -> int:
    parser = argparse.ArgumentParser(description="Read Outlook messages")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List recent messages")
    group.add_argument("--message", help="Fetch a specific message by ID")
    parser.add_argument("--limit", type=int, default=10, help="Max messages to list")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        token = get_graph_token()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    try:
        if args.list:
            data = list_inbox(token, args.limit)
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                for msg in data:
                    sender = (msg.get("from") or {}).get("emailAddress") or {}
                    display = sender.get("name") or sender.get("address") or "(unknown)"
                    received = msg.get("receivedDateTime", "")[:16].replace("T", " ")
                    print(f"[{msg['id'][:8]}] {received} | {display[:25]:25} | {msg['subject']}")
        elif args.message:
            data = get_message(token, args.message)
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                sender = (data.get("from") or {}).get("emailAddress") or {}
                print(f"From:    {sender.get('name')} <{sender.get('address')}>")
                print(f"Subject: {data.get('subject')}")
                print(f"Date:    {data.get('receivedDateTime')}")
                print("-" * 40)
                body = data.get("body", {}).get("content", "")
                print(body)
    except Exception as exc:
        print(f"Graph error: {exc}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
