#!/usr/bin/env python3
"""Send an approved Outlook draft via Microsoft Graph.

Reads the draft record from the S3 approval queue, calls Graph
POST /me/messages/{id}/send, and marks the record as sent.

Usage:
  outlook-send-approved --draft-id <id> [--json]
  outlook-send-approved --all [--json]          # send all approved drafts

Env:
  DRAFT_QUEUE_BUCKET   override S3 bucket name
  AWS_REGION           default: us-east-1
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

GRAPH_SEND_URL = "https://graph.microsoft.com/v1.0/me/messages/{draft_id}/send"
REGION = os.environ.get("AWS_REGION", "us-east-1")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve_bucket() -> str:
    env_bucket = os.environ.get("DRAFT_QUEUE_BUCKET")
    if env_bucket:
        return env_bucket
    account = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    return f"agent-cody-draft-queue-{account}"


def resolve_prefix() -> str:
    # Per-tenant runtimes share the same bucket but not the same key prefix.
    prefix = os.environ.get("DRAFT_QUEUE_PREFIX", "drafts").strip("/")
    return prefix or "drafts"


def draft_key(draft_id: str) -> str:
    return f"{resolve_prefix()}/{draft_id}.json"


def get_graph_token() -> str:
    script = os.path.join(os.path.dirname(__file__), "graph-token-fresh.py")
    proc = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "could not obtain Graph token")
    return proc.stdout.strip()


def load_draft(s3, bucket: str, draft_id: str) -> dict:
    key = draft_key(draft_id)
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        return json.loads(body)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in {"NoSuchKey", "404"}:
            raise FileNotFoundError(f"Draft {draft_id} not found in queue (bucket={bucket}, key={key})")
        raise


def send_draft(token: str, draft_id: str) -> None:
    import urllib.request
    url = GRAPH_SEND_URL.format(draft_id=draft_id)
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Length": "0",
        },
        data=b"",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            if resp.status not in (200, 202, 204):
                raise RuntimeError(f"Graph returned HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Graph error {exc.code}: {body}") from exc


def mark_sent(s3, bucket: str, draft_id: str, record: dict) -> None:
    record["approved"] = True
    record["sent_at"] = now_iso()
    key = draft_key(draft_id)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(record, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def process_draft(s3, bucket: str, draft_id: str, token: str, as_json: bool) -> dict:
    record = load_draft(s3, bucket, draft_id)

    if record.get("sent_at"):
        result = {"ok": True, "draft_id": draft_id, "status": "already_sent", "sent_at": record["sent_at"]}
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Already sent at {record['sent_at']}: {draft_id}")
        return result

    send_draft(token, draft_id)
    mark_sent(s3, bucket, draft_id, record)

    result = {
        "ok": True,
        "draft_id": draft_id,
        "status": "sent",
        "to": record.get("to"),
        "subject": record.get("subject"),
        "sent_at": record["sent_at"],
    }
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"✓ Sent to {record.get('to')}: {record.get('subject')} [{record['sent_at']}]")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send an approved Outlook draft from the S3 queue")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--draft-id", help="Send a specific draft by ID")
    group.add_argument("--all", action="store_true", help="Send all unsent drafts in the queue")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    bucket = resolve_bucket()
    s3 = boto3.client("s3", region_name=REGION)

    try:
        token = get_graph_token()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.draft_id:
        try:
            process_draft(s3, bucket, args.draft_id, token, args.json)
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    elif args.all:
        paginator = s3.get_paginator("list_objects_v2")
        results = []
        errors = []
        prefix = f"{resolve_prefix()}/"
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                draft_id = key.removeprefix(prefix).removesuffix(".json")
                try:
                    r = process_draft(s3, bucket, draft_id, token, as_json=False)
                    results.append(r)
                except (FileNotFoundError, RuntimeError) as exc:
                    errors.append({"draft_id": draft_id, "error": str(exc)})
                    print(f"ERROR [{draft_id}]: {exc}", file=sys.stderr)

        if args.json:
            print(json.dumps({"ok": len(errors) == 0, "sent": results, "errors": errors}, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
