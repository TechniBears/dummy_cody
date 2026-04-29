---
name: outlook-read
description: Read Outlook messages and list the inbox via Microsoft Graph.
metadata: {"openclaw":{"emoji":"📬","os":["linux"],"requires":{"bins":["outlook-read"]},"model":"amazon-bedrock/us.anthropic.claude-sonnet-4-6"}}
---

# outlook-read

Read messages from the user's Outlook inbox. Use this to check for replies, look up thread history, or find specific information in recent emails.

## Commands

```bash
outlook-read --list                # show the 10 most recent messages
outlook-read --list --limit 20     # show the 20 most recent
outlook-read --message <id>        # fetch the full body and details of a message
outlook-read --list --json         # output raw JSON for processing
```

## Behavior

- `--list` provides a summary table with truncated IDs, timestamps, senders, and subjects.
- `--message <id>` provides the sender, subject, date, and the full content (usually HTML or Text).
- Always use `--json` if you need to parse the data programmatically (e.g., to find a specific sender's email address).

## Rules

- This is a read-only skill. It cannot delete, move, or modify mail.
- Do not read more than 20 messages at a time without a specific reason.
- If you find a message you want to reply to, use the `id` from `outlook-read` to help you track context, but remember that `outlook-draft` uses its own parameters for creating the reply.
