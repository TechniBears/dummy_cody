---
name: calendar-read
description: Read Outlook calendar events via Microsoft Graph. Use when the user asks what's on their calendar, upcoming meetings, events today or this week, or details of a specific event.
metadata: {"openclaw":{"emoji":"📅","os":["linux"],"requires":{"bins":["calendar-read"]},"model":"amazon-bedrock/us.anthropic.claude-sonnet-4-6"}}
---

# calendar-read

Read calendar events from the user's Outlook calendar.

## When to use

- User asks "what's on my calendar today/this week?"
- User asks about upcoming meetings or events
- User asks for details of a specific event

## Commands

```bash
calendar-read --today               # events today
calendar-read --week                # events this week
calendar-read --upcoming --limit 5  # next 5 events
calendar-read --event <id>          # full details of one event
calendar-read --today --json        # raw JSON output
```

## Rules

- Read-only. Cannot modify or delete events.
- Default limit is 10 events. Do not exceed 20 without a specific reason.
- Always show start/end times and location if available.
