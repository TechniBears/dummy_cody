"""Phase 0 stub.

Phase 2 contract: polls the draft-queue bucket for S3 objects with approved=true
and no sent_at. Checks agent-cody/graph-sender-frozen secret FIRST; if frozen,
return without sending. Otherwise calls MS Graph POST /me/messages/{id}/send.
Writes every attempt (success or failure) to the audit log.
"""
from __future__ import annotations

import json
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def handler(event: dict, context) -> dict:
    log.info("graph-sender invoked (noop stub) event=%s", json.dumps(event, default=str))
    return {"statusCode": 200, "body": json.dumps({"ok": True, "stub": True})}
