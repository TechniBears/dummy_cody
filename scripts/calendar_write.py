#!/usr/bin/env python3
"""Create or update Outlook calendar events via Microsoft Graph.

Usage:
  calendar-write --title "Meeting" --start "2026-04-24T10:00:00" --end "2026-04-24T11:00:00"
  calendar-write --title "Call" --start "..." --end "..." --attendees "a@b.com,c@d.com"
  calendar-write --title "..." --location "Zoom" --body "Agenda here"
  calendar-write --update <event-id> --title "New title"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def get_graph_token() -> str:
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graph-token-fresh.py")
    if not os.path.exists(helper):
        helper = "/opt/openclaw/bin/graph-token-fresh.py"
    proc = subprocess.run(
        [sys.executable, helper],
        capture_output=True, text=True,
        env={**os.environ, "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1")},
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(proc.stderr.strip() or "could not obtain Graph token")
    return proc.stdout.strip()


def graph_request(token: str, url: str, payload: dict, method: str = "POST") -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Graph error {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc


def parse_attendees(raw: str) -> list[dict]:
    result = []
    for addr in raw.split(","):
        addr = addr.strip()
        if addr:
            result.append({"emailAddress": {"address": addr}, "type": "required"})
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create/update Outlook calendar events via Microsoft Graph")
    parser.add_argument("--title", required=True, help="Event title/subject")
    parser.add_argument("--start", help="Start datetime ISO 8601 e.g. 2026-04-24T10:00:00")
    parser.add_argument("--end", help="End datetime ISO 8601")
    parser.add_argument("--timezone", default="UTC", help="Timezone name (default UTC)")
    parser.add_argument("--location", default="", help="Location")
    parser.add_argument("--body", default="", help="Event body/description")
    parser.add_argument("--attendees", default="", help="Comma-separated attendee emails")
    parser.add_argument("--update", metavar="EVENT_ID", help="Update existing event by ID")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        token = get_graph_token()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload: dict = {"subject": args.title}
    if args.start:
        payload["start"] = {"dateTime": args.start, "timeZone": args.timezone}
    if args.end:
        payload["end"] = {"dateTime": args.end, "timeZone": args.timezone}
    if args.location:
        payload["location"] = {"displayName": args.location}
    if args.body:
        payload["body"] = {"contentType": "Text", "content": args.body}
    if args.attendees:
        payload["attendees"] = parse_attendees(args.attendees)

    try:
        if args.update:
            url = f"https://graph.microsoft.com/v1.0/me/events/{args.update}"
            result = graph_request(token, url, payload, method="PATCH")
            event_id = args.update
            action = "updated"
        else:
            if not args.start or not args.end:
                print("ERROR: --start and --end are required when creating a new event.", file=sys.stderr)
                return 1
            url = "https://graph.microsoft.com/v1.0/me/events"
            result = graph_request(token, url, payload, method="POST")
            event_id = result.get("id", "")
            action = "created"
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    output = {
        "ok": True,
        "action": action,
        "event_id": event_id,
        "title": args.title,
        "start": args.start,
        "end": args.end,
        "web_link": result.get("webLink", ""),
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"✓ Event {action}: {args.title}")
        if args.start:
            print(f"  Start : {args.start} ({args.timezone})")
        if args.end:
            print(f"  End   : {args.end} ({args.timezone})")
        if output["web_link"]:
            print(f"  Link  : {output['web_link']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
