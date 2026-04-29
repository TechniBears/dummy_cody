---
name: outlook-queue-send
description: Queue an existing Outlook draft into Cody's S3 approval queue. Use after a draft is created and the user wants it staged for SEND/EDIT/SKIP approval. Never sends the message.
homepage: https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutObject.html
metadata: {"openclaw":{"emoji":"📮","os":["linux"],"requires":{"bins":["outlook-queue-send"]},"model":"amazon-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"}}
---

# outlook-queue-send

Queue a Graph draft for approval. This skill never sends an email.

## Required inputs

- `draft_id`
- `to`
- `subject`
- `preview`

## Optional inputs

- `web_link`
- `session_id`
- `thread_id`

## Command

```bash
outlook-queue-send \
  --draft-id "$DRAFT_ID" \
  --to "$TO" \
  --subject "$SUBJECT" \
  --preview "$PREVIEW" \
  ${WEB_LINK:+--web-link "$WEB_LINK"} \
  ${SESSION_ID:+--session-id "$SESSION_ID"} \
  ${THREAD_ID:+--thread-id "$THREAD_ID"} \
  --json
```

## Rules

- Queue only. Never send directly.
- If the draft already exists in the queue, treat the operation as idempotent.
- Tell the user the draft is waiting for explicit approval.
