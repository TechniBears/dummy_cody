---
name: calendar-write
description: Create or update Outlook calendar events via Microsoft Graph. Use when the user asks to schedule a meeting, add an event to their calendar, or update an existing event.
metadata: {"openclaw":{"emoji":"📆","os":["linux"],"requires":{"bins":["calendar-write"]},"model":"amazon-bedrock/us.anthropic.claude-sonnet-4-6"}}
---

# calendar-write

Create or update calendar events in the user's Outlook calendar.

## When to use

- User asks to schedule a meeting or add an event
- User asks to update or reschedule an existing event

## When NOT to use

- User asks to delete an event (not supported)
- User wants to read calendar (use calendar-read)

## Required inputs for new events

- `--title` — event title
- `--start` — ISO 8601 datetime e.g. `2026-04-24T10:00:00`
- `--end` — ISO 8601 datetime

## Optional inputs

- `--timezone` — default UTC, configure per principal
- `--location` — location string
- `--body` — description/agenda
- `--attendees` — comma-separated emails
- `--update <id>` — update existing event instead of creating

## Commands

```bash
# Create new event
calendar-write \
  --title "Meeting with Ulysses" \
  --start "2026-04-24T10:00:00" \
  --end "2026-04-24T11:00:00" \
  --timezone "Asia/Dubai" \
  --attendees "ulysses@reddoordigital.com" \
  --json

# Update existing event
calendar-write --update <event-id> --title "New Title" --json
```

## Rules

- Always confirm details with user before creating.
- Use the principal's configured timezone as default unless specified otherwise.
- Report event ID and web link on success.
