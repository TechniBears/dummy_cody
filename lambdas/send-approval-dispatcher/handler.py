"""Phase 0 stub.

Phase 2 contract: parse inbound WhatsApp reply text matching r'^(SEND|EDIT|SKIP)\\b',
look up the corresponding draft in the draft-queue bucket by session_id, and flip
approved=true on exact match. Never sends the email; graph-sender does that.

The agent MUST NOT be the component that flips approved=true. That must come from
a deterministic regex match on inbound user WhatsApp text in channel middleware,
invoking this Lambda with the match result.
"""
from __future__ import annotations

import json
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def handler(event: dict, context) -> dict:
    log.info("send-approval-dispatcher invoked (noop stub) event=%s", json.dumps(event, default=str))
    return {"statusCode": 200, "body": json.dumps({"ok": True, "stub": True})}
