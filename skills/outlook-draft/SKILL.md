---
name: outlook-draft
description: Create a draft email in the user's Outlook mailbox via Microsoft Graph. Use when the user asks to draft/compose an email, prepare a reply, or stage a message for later review. Returns the Graph draft ID. Never sends the message.
homepage: https://learn.microsoft.com/graph/api/user-post-messages
metadata: {"openclaw":{"emoji":"📝","os":["linux"],"requires":{"bins":["outlook-draft"]},"model":"amazon-bedrock/us.anthropic.claude-opus-4-6-v1"}}
---

# outlook-draft — Draft an Outlook email via Microsoft Graph

Create a draft in the signed-in user's mailbox. This skill NEVER sends. To queue for sending, invoke `outlook-queue-send` with the returned draft ID.

## When to use

- User asks to "draft", "compose", "write", or "prepare" an email.
- User asks for a reply/forward that needs human review before sending.
- User asks to stage a message for later.

## When NOT to use

- User asks to send immediately. There is no send path in Agent Cody — always stop at draft or queue.
- User asks to read mail — use `outlook-read`.

## Required inputs

- `to` — comma-separated recipient emails (required)
- `subject` — string (required)
- `body` — string, markdown or HTML (required)
- `cc` — optional, comma-separated
- `contentType` — `Text` or `HTML` (default `Text`)

## Procedure

Run the helper command below. Do not search the filesystem for credentials.

## Command

```bash
outlook-draft \
  --to "$TO" \
  --subject "$SUBJECT" \
  --body "$BODY" \
  ${CC:+--cc "$CC"} \
  --content-type "${CONTENT_TYPE:-Text}" \
  --json
```

## Report to the user

Summarize as:

> Draft created in Outlook.
> - Draft ID: `<DRAFT_ID>`
> - Web link: `<WEB_LINK>`
> - To queue for sending, run `outlook-queue-send` with this draft ID.

## Errors

- `401` from Graph → token expired/revoked. Tell the user the MSAL cache needs refresh (out-of-band).
- `403` → scope missing (`Mail.ReadWrite`). Tell the user to reconsent.
- Anything else → print the raw Graph error body verbatim. Don't swallow.

## Non-negotiable constraints

- Never call `POST /me/sendMail` or `POST /me/messages/{id}/send`. Drafts only.
- Never print the Graph token.
- Never search `/creds`, `.env`, or the workspace for Graph credentials.
