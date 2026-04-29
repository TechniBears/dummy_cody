#!/usr/bin/env python3
"""One-shot Telegram message announcing Cody is back online.

Invoked from openclaw-admin-helper after a successful pull-latest. Idempotent:
won't re-announce within 5 minutes of the previous announce. Pass --force to
bypass cooldown.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

USER_CHAT_ID = 000000000  # Configure with the principal's Telegram chat ID
TOKEN_SECRET_ID = "agent-cody/telegram-bot-token"
LAST_ANNOUNCE_FILE = Path("/var/lib/openclaw/last-announce.txt")
COOLDOWN_SECONDS = 300

MESSAGE = """\
🤖 Cody is back online.

*Model lineup (live now):*
• `opus` → Claude Opus 4.6 (Bedrock) — *primary, daily driver*
• `opus-next` → Opus 4.7 (Bedrock) — *premium experimental*
• `sonnet` → Sonnet 4.6 (Bedrock) — *quick reasoning*
• `sonnet-1m` → Sonnet 4.5 1M-ctx (Bedrock) — *long-context research*
• `haiku` → Haiku 4.5 (Bedrock) — *fast small ops*
• `gemma` → gemma3:4b (local Ollama) — *offline / sovereign*

*Switch on the fly:*
`/model opus` · `/model sonnet` · `/model gemma` · etc.

*Per-skill routing:*
Memory ops + email queue → Haiku. Reads + summaries → Sonnet. Drafting → Opus.
Morning-brief → Sonnet 4.5 1M (full inbox window). All declared in SKILL.md.

*Drift protection:*
Per-agent state is now purged on every restart, so a transient fallback can't
permanently hijack the config (OpenClaw bug #47705 is contained).

*Self-improvement:*
`cody-admin --pull-latest` pulls the latest from S3 + restarts. Triggered by
GitHub Actions on every green push to main. CI now validates renderer output
structurally instead of pinning to a stale string constant.

Spec + plan in `docs/superpowers/{specs,plans}/2026-04-25-cody-restoration-*`.
"""


def fetch_token(secret_id: str = TOKEN_SECRET_ID, region: str = "us-east-1") -> str:
    """Fetch the Telegram bot token from Secrets Manager via boto3.

    Mirrors scripts/fetch-telegram-token.sh — secret stores JSON with a `token` key.
    """
    import boto3

    client = boto3.client("secretsmanager", region_name=region)
    raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    return json.loads(raw)["token"]


def should_announce() -> bool:
    if not LAST_ANNOUNCE_FILE.is_file():
        return True
    try:
        last = float(LAST_ANNOUNCE_FILE.read_text().strip())
    except ValueError:
        return True
    return (time.time() - last) > COOLDOWN_SECONDS


def mark_announced() -> None:
    LAST_ANNOUNCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LAST_ANNOUNCE_FILE.write_text(str(time.time()))


def send(token: str, text: str, chat_id: int = USER_CHAT_ID) -> dict:
    data = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    force = "--force" in sys.argv
    if not force and not should_announce():
        print("skipped (cooldown)")
        return 0
    token = fetch_token()
    result = send(token, MESSAGE)
    if not result.get("ok"):
        print(json.dumps(result), file=sys.stderr)
        return 1
    mark_announced()
    print(json.dumps({"ok": True, "message_id": result["result"]["message_id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
