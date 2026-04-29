---
name: morning-brief
description: Compose and deliver the principal's morning email brief on demand. Normally fires automatically at 07:30 Asia/Dubai via a systemd timer; only invoke this skill when the principal asks for a brief right now or a re-run.
metadata: {"openclaw":{"emoji":"🌅","os":["linux"],"requires":{"bins":["morning-brief"]},"model":"amazon-bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0"}}
---

# morning-brief

Compose the morning brief and deliver it via Telegram. This runs automatically each day at 07:30 Asia/Dubai via the `morning-brief.timer` systemd unit. Use this skill only when the principal explicitly asks for an ad-hoc brief.

## Commands

```bash
morning-brief              # live compose + send to Telegram
morning-brief --dry-run    # compose + print; skip Telegram delivery
```

## Behavior

- The brief scans the last ~18 hours of inbox.
- For each message, it calls `memory-read` on the sender's email and name and boosts importance by memory facts: `priority=high`, `register=vip|exec` (+), `surface_policy=quiet` (–).
- It also factors Outlook's `importance` and `flag` fields, urgency keywords in subject/preview, and a cheap newsletter filter.
- It picks the top 5 by score and composes a Markdown summary.
- Delivery target: the chat id in `/creds/morning-brief-chat-id`. If that file is missing or empty, the brief logs to journal only (safe mode) — this is intentional until the principal confirms the delivery target.

## Rules

- Do not invoke this skill speculatively. The principal must ask.
- If the live send fails, report the actual error and offer `--dry-run`.
- Never modify the chat-id file. If the principal wants a different delivery target, ask them to update `/creds/morning-brief-chat-id` themselves.
