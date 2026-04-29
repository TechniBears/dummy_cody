#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_bucket() -> str:
    env_bucket = os.environ.get("DRAFT_QUEUE_BUCKET")
    if env_bucket:
        return env_bucket
    account = boto3.client("sts").get_caller_identity()["Account"]
    return f"agent-cody-draft-queue-{account}"


def resolve_prefix() -> str:
    # Per-tenant runtimes share the same bucket but not the same key prefix.
    prefix = os.environ.get("DRAFT_QUEUE_PREFIX", "drafts").strip("/")
    return prefix or "drafts"


def draft_key(draft_id: str) -> str:
    return f"{resolve_prefix()}/{draft_id}.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Queue an Outlook draft for approval")
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--preview", required=True)
    parser.add_argument("--web-link", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--thread-id", default="")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bucket = resolve_bucket()
    key = draft_key(args.draft_id)
    s3 = boto3.client("s3")

    existing = None
    try:
        existing = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in {"NoSuchKey", "404"}:
            print(str(exc), file=sys.stderr)
            return 1

    payload = {
        "draft_id": args.draft_id,
        "to": [item.strip() for item in args.to.split(",") if item.strip()],
        "subject": args.subject,
        "preview": args.preview,
        "web_link": args.web_link,
        "session_id": args.session_id,
        "thread_id": args.thread_id,
        "approved": False,
        "queued_at": now_iso(),
        "sent_at": None,
    }

    if existing:
        prior = json.loads(existing)
        payload["queued_at"] = prior.get("queued_at", payload["queued_at"])

    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(payload, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    result = {"ok": True, "bucket": bucket, "key": key, "draft_id": args.draft_id, "approved": False}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("Draft queued for approval.")
        print(f"bucket={bucket}")
        print(f"key={key}")
        print(f"draft_id={args.draft_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
