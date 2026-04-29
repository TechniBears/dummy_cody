"""Phase 0 stub.

Phase 3 contract: weekly cron. Fetches ~500 most recent sent emails via MS Graph,
compresses them into a <=200-token style card (formality, length, sign-offs,
banned phrases, register rules), and writes to the style-card secret. Writes an
audit record for the refresh event.
"""
from __future__ import annotations

import json
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def handler(event: dict, context) -> dict:
    log.info("style-card-refresh invoked (noop stub) event=%s", json.dumps(event, default=str))
    return {"statusCode": 200, "body": json.dumps({"ok": True, "stub": True})}
