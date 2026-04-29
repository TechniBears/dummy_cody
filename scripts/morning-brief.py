#!/usr/bin/env python3
"""Morning brief for Agent Cody.

Scans the last ~18 hours of the principal's Outlook inbox, scores each message using
signals from Cody's Graphiti memory (so the brief gets smarter as the graph
fills), picks the top N, and delivers a short Markdown summary to Telegram.

Config (env or defaults):
  GRAPH_MSAL_SECRET         agent-cody/graph-msal-token-cache
  TELEGRAM_BOT_SECRET       agent-cody/telegram-bot-token
  MORNING_BRIEF_CHAT_ID_FILE /creds/morning-brief-chat-id    (one-line chat id)
  MORNING_BRIEF_LOOKBACK_HOURS 18
  MORNING_BRIEF_TOP_N       5

If MORNING_BRIEF_CHAT_ID_FILE is missing/empty, the brief is printed to
stdout+journal only. This is the safe-by-default mode until the principal confirms
the target chat id.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
import msal

REGION = os.environ.get("AWS_REGION", "us-east-1")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SECRET_ID = os.environ.get("GRAPH_MSAL_SECRET", "agent-cody/graph-msal-token-cache")
TELEGRAM_SECRET_ID = os.environ.get("TELEGRAM_BOT_SECRET", "agent-cody/telegram-bot-token")
CHAT_ID_FILE = os.environ.get("MORNING_BRIEF_CHAT_ID_FILE", "/creds/morning-brief-chat-id")
LOOKBACK_HOURS = int(os.environ.get("MORNING_BRIEF_LOOKBACK_HOURS", "18"))
TOP_N = int(os.environ.get("MORNING_BRIEF_TOP_N", "5"))
MEMORY_READ_BIN = os.environ.get("MORNING_BRIEF_MEMORY_READ", "/opt/openclaw/bin/memory-read")


def log(msg: str) -> None:
    print(f"[morning-brief] {msg}", file=sys.stderr, flush=True)


def load_graph_token() -> str:
    sm = boto3.client("secretsmanager", region_name=REGION)
    blob = json.loads(sm.get_secret_value(SecretId=GRAPH_SECRET_ID)["SecretString"])
    cache = msal.SerializableTokenCache()
    cache.deserialize(blob["cache"])
    app = msal.PublicClientApplication(
        blob["client_id"], authority=blob["authority"], token_cache=cache
    )
    accounts = app.get_accounts()
    if not accounts:
        raise RuntimeError("no MSAL accounts in cached token")
    result = app.acquire_token_silent(scopes=blob["scopes"], account=accounts[0])
    if not result or "access_token" not in result:
        raise RuntimeError(f"silent token acquire failed: {result}")
    return result["access_token"]


def load_telegram_token() -> str:
    sm = boto3.client("secretsmanager", region_name=REGION)
    blob = json.loads(sm.get_secret_value(SecretId=TELEGRAM_SECRET_ID)["SecretString"])
    return blob["token"]


def load_chat_id() -> str | None:
    p = Path(CHAT_ID_FILE)
    if p.is_file():
        val = p.read_text().strip()
        if val:
            return val
    return None


def graph_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def fetch_recent_inbox(token: str, hours: int) -> list[dict]:
    since = (
        (datetime.now(timezone.utc) - timedelta(hours=hours))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    # OData params contain spaces (e.g. "receivedDateTime ge 2026-...Z") that
    # urllib.request rejects with "URL can't contain control characters".
    # urlencode with safe=',' preserves the commas inside $select values.
    params = {
        "$top": "50",
        "$select": "id,subject,bodyPreview,from,receivedDateTime,isRead,importance,flag,webLink",
        "$filter": f"receivedDateTime ge {since}",
        "$orderby": "receivedDateTime desc",
    }
    url = f"{GRAPH_BASE}/me/mailFolders/inbox/messages?" + urllib.parse.urlencode(params, safe=",")
    return graph_get(url, token).get("value") or []


def memory_query(query: str) -> list[dict]:
    if not query:
        return []
    try:
        res = subprocess.run(
            [MEMORY_READ_BIN, "--query", query, "--limit", "5", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode != 0:
            log(f"memory-read rc={res.returncode} for {query!r}: {res.stderr.strip()}")
            return []
        data = json.loads(res.stdout or "{}")
        return data.get("facts") or []
    except FileNotFoundError:
        log(f"memory-read not found at {MEMORY_READ_BIN}; scoring without memory")
        return []
    except Exception as exc:
        log(f"memory-read failed for {query!r}: {exc}")
        return []


def score_message(msg: dict) -> tuple[int, list[str]]:
    sender = (msg.get("from") or {}).get("emailAddress") or {}
    email = (sender.get("address") or "").lower()
    name = sender.get("name") or ""
    subject = msg.get("subject") or ""
    preview = msg.get("bodyPreview") or ""
    is_read = bool(msg.get("isRead"))
    importance = (msg.get("importance") or "normal").lower()
    flagged = ((msg.get("flag") or {}).get("flagStatus") or "notFlagged").lower() == "flagged"

    score = 0
    signals: list[str] = []

    # Memory-driven signals. This is the lever that makes the brief smarter over time.
    facts = memory_query(email) if email else []
    if not facts and name:
        facts = memory_query(name)
    for fact in facts:
        pred = (fact.get("predicate") or "").lower()
        val = str(fact.get("value") or "").lower()
        if pred == "priority" and val == "high":
            score += 10
            signals.append("mem:priority=high")
        elif pred == "register" and val in ("vip", "exec"):
            score += 5
            signals.append(f"mem:{val}")
        elif pred == "surface_policy" and val == "quiet":
            score -= 8
            signals.append("mem:quiet")

    # Outlook-native signals.
    if importance == "high":
        score += 4
        signals.append("outlook:high")
    if flagged:
        score += 3
        signals.append("outlook:flagged")
    if not is_read:
        score += 1
        signals.append("unread")

    # Lightweight content heuristics.
    body_lc = (subject + " " + preview).lower()
    if any(kw in body_lc for kw in ("urgent", "asap", "deadline", "today by", "eod")):
        score += 3
        signals.append("urgency-kw")

    # Cheap noise filter. Not a substitute for a real newsletter rule.
    if email and any(
        tok in email
        for tok in ("noreply", "no-reply", "newsletter", "notification", "mailer-daemon")
    ):
        score -= 5
        signals.append("noise:bot-domain")

    return score, signals


def compose(top: list[tuple[dict, int, list[str]]]) -> str:
    if not top:
        return "Quiet morning — nothing pending."
    lines = ["🌅 *Morning brief*", ""]
    for i, (msg, score, signals) in enumerate(top, start=1):
        sender = (msg.get("from") or {}).get("emailAddress") or {}
        display = sender.get("name") or sender.get("address") or "(unknown)"
        subj = (msg.get("subject") or "(no subject)")[:80]
        preview = (msg.get("bodyPreview") or "").replace("\n", " ").strip()[:140]
        lines.append(f"{i}. *{display}* — {subj}")
        if preview:
            lines.append(f"   _{preview}_")
        lines.append(f"   `score={score} {' '.join(signals) if signals else 'no-signals'}`")
        lines.append("")
    return "\n".join(lines).rstrip()


def send_telegram(token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": str(chat_id), "text": text, "parse_mode": "Markdown"}).encode()
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"telegram http {exc.code}: {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Cody morning brief")
    parser.add_argument("--dry-run", action="store_true", help="Compose and print; skip send")
    parser.add_argument("--lookback-hours", type=int, default=LOOKBACK_HOURS)
    parser.add_argument("--top-n", type=int, default=TOP_N)
    args = parser.parse_args()

    log("starting")
    try:
        token = load_graph_token()
    except Exception as exc:
        log(f"graph token failed: {exc}")
        return 2

    log(f"fetching inbox (last {args.lookback_hours}h)")
    try:
        messages = fetch_recent_inbox(token, args.lookback_hours)
    except Exception as exc:
        log(f"inbox fetch failed: {exc}")
        return 3

    log(f"scoring {len(messages)} messages")
    scored: list[tuple[dict, int, list[str]]] = []
    for msg in messages:
        score, signals = score_message(msg)
        if score > 0:
            scored.append((msg, score, signals))
    scored.sort(key=lambda t: t[1], reverse=True)
    top = scored[: args.top_n]
    log(f"selected {len(top)} of {len(scored)} scoring>0")

    text = compose(top)

    if args.dry_run:
        print(text)
        return 0

    chat_id = load_chat_id()
    if not chat_id:
        # Safe default: log the brief, do not send. Operator creates the chat id
        # file once they're comfortable with the output.
        log(f"no chat id at {CHAT_ID_FILE}; printing only (safe mode)")
        print(text)
        return 0

    try:
        tg_token = load_telegram_token()
    except Exception as exc:
        log(f"telegram secret failed: {exc}")
        return 4

    try:
        resp = send_telegram(tg_token, chat_id, text)
        log(f"sent: message_id={(resp.get('result') or {}).get('message_id')}")
    except Exception as exc:
        log(f"telegram send failed: {exc}")
        return 5

    return 0


if __name__ == "__main__":
    sys.exit(main())
