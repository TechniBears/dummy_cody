---
name: outlook-send-approved
description: Send a queued Outlook draft via Microsoft Graph AFTER the user has explicitly approved the SEND. Reads the draft record from the S3 approval queue, calls POST /me/messages/{id}/send, and marks it sent. Never use without an explicit SEND confirmation from the user in the current turn.
homepage: https://learn.microsoft.com/graph/api/message-send
metadata: {"openclaw":{"emoji":"📤","os":["linux"],"requires":{"bins":["outlook-send-approved"]},"model":"amazon-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"}}
---

# outlook-send-approved — Send a queued Outlook draft

Finalize the send of a draft that is already in the approval queue.

## When to use

- The user typed SEND (or a clear equivalent like "yep send it", "approved", "go ahead") in the same turn, in reply to a draft preview I produced via `outlook-draft` + `outlook-queue-send`.
- I have the `draft_id` from that preview.

## When NOT to use

- The user has not said SEND yet. Stop at the preview.
- The user said EDIT — go back to `outlook-draft` with the revision.
- The user said SKIP — do nothing.
- More than one draft is ambiguous. Ask which one.

## Required inputs

- `draft_id` — the Graph immutable ID returned by `outlook-draft` and queued by `outlook-queue-send`.

## Procedure

1. Confirm I have a SEND signal from the user for this specific `draft_id` in the current conversation turn.
2. Run the helper. It reads the S3 queue record, posts to Graph, and writes `sent_at` back to the record (idempotent — safe to retry).

## Command

```bash
outlook-send-approved --draft-id "$DRAFT_ID" --json
```

## Report to the user

On success:

> Sent.
> - To: `<TO>`
> - Subject: `<SUBJECT>`
> - Sent at: `<SENT_AT>`

If the record shows `already_sent`, tell the user it was already sent and when — do not retry.

## Errors

- `Draft <id> not found in queue` → the user never queued it, or they're referring to a different one. Ask.
- `Graph error 404` → the draft was deleted from the mailbox between queue and send. Tell the user and offer to re-draft.
- `Graph error 401` → token expired. Stop; tell the principal the MSAL cache needs refresh.
- Any other error → print verbatim, don't swallow.

## Non-negotiable constraints

- Never call `outlook-send-approved` without an explicit SEND from the user in the current turn.
- Never invoke with `--all`. Always pass `--draft-id` for a specific draft.
- Never re-send a draft that already has `sent_at` set in the queue record.
- Never print the Graph token.
