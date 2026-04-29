#!/usr/bin/env python3
"""Read Outlook calendar events via Microsoft Graph.

Usage:
  calendar-read --today                    # events today
  calendar-read --week                     # events this week
  calendar-read --upcoming --limit 10      # next N events
  calendar-read --event <id>               # full details of one event
  calendar-read --json                     # output raw JSON
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone


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


def graph_get(token: str, url: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Graph error {exc.code}: {exc.read().decode('utf-8', 'replace')}") from exc


def fmt_dt(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%a %b %d, %Y %H:%M UTC")
    except Exception:
        return iso


def print_events(events: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(events, indent=2))
        return
    if not events:
        print("No events found.")
        return
    for e in events:
        start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
        end = e.get("end", {}).get("dateTime", e.get("end", {}).get("date", ""))
        print(f"📅 {e.get('subject', '(no title)')}")
        print(f"   Start : {fmt_dt(start)}")
        print(f"   End   : {fmt_dt(end)}")
        if e.get("location", {}).get("displayName"):
            print(f"   Where : {e['location']['displayName']}")
        if e.get("bodyPreview"):
            print(f"   Notes : {e['bodyPreview'][:120]}")
        print(f"   ID    : {e.get('id', '')[:40]}...")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read Outlook calendar via Microsoft Graph")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--today", action="store_true", help="Events today")
    group.add_argument("--week", action="store_true", help="Events this week")
    group.add_argument("--upcoming", action="store_true", help="Next N upcoming events")
    group.add_argument("--event", metavar="ID", help="Full details of a specific event")
    parser.add_argument("--limit", type=int, default=10, help="Max events to return (default 10)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        token = get_graph_token()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    base = "https://graph.microsoft.com/v1.0/me/calendarView"
    now = datetime.now(timezone.utc)

    try:
        if args.event:
            url = f"https://graph.microsoft.com/v1.0/me/events/{args.event}"
            data = graph_get(token, url)
            print_events([data], args.json)

        elif args.today:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            url = (f"{base}?startDateTime={start.isoformat()}&endDateTime={end.isoformat()}"
                   f"&$orderby=start/dateTime&$top={args.limit}"
                   f"&$select=id,subject,start,end,location,bodyPreview")
            data = graph_get(token, url)
            print_events(data.get("value", []), args.json)

        elif args.week:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7)
            url = (f"{base}?startDateTime={start.isoformat()}&endDateTime={end.isoformat()}"
                   f"&$orderby=start/dateTime&$top={args.limit}"
                   f"&$select=id,subject,start,end,location,bodyPreview")
            data = graph_get(token, url)
            print_events(data.get("value", []), args.json)

        elif args.upcoming:
            url = (f"https://graph.microsoft.com/v1.0/me/events"
                   f"?$orderby=start/dateTime&$top={args.limit}&$filter=start/dateTime ge '{now.isoformat()}'"
                   f"&$select=id,subject,start,end,location,bodyPreview")
            data = graph_get(token, url)
            print_events(data.get("value", []), args.json)

    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
