#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import ClientError
except ModuleNotFoundError:  # laptop path can rely on the AWS CLI instead
    boto3 = None
    ClientError = Exception

REGION = os.environ.get("AWS_REGION", "us-east-1")
DEFAULT_CHANNEL = "root"
PREFIX_ROOT = "bootstrap/deploy-bundles"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_bucket() -> str:
    if boto3 is not None:
        account = boto3.client("sts", region_name=REGION).get_caller_identity()["Account"]
    else:
        account = subprocess.check_output(
            ["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"],
            text=True,
        ).strip()
    return f"agent-cody-draft-queue-{account}"


def s3_upload_file(bucket: str, key: str, src: Path) -> None:
    if boto3 is not None:
        boto3.client("s3", region_name=REGION).upload_file(str(src), bucket, key)
        return
    subprocess.run(["aws", "s3", "cp", "--only-show-errors", str(src), f"s3://{bucket}/{key}"], check=True)


def s3_put_json(bucket: str, key: str, payload: dict) -> None:
    body = json.dumps(payload, indent=2).encode("utf-8")
    if boto3 is not None:
        boto3.client("s3", region_name=REGION).put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"deploy-bundle-{os.getpid()}.json"
    tmp.write_bytes(body)
    try:
        subprocess.run(["aws", "s3", "cp", "--only-show-errors", str(tmp), f"s3://{bucket}/{key}"], check=True)
    finally:
        tmp.unlink(missing_ok=True)


def s3_get_text(bucket: str, key: str) -> str:
    if boto3 is not None:
        try:
            return boto3.client("s3", region_name=REGION).get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in {"NoSuchKey", "404"}:
                raise SystemExit(f"ERROR: no published bundle found at s3://{bucket}/{key}")
            raise
    proc = subprocess.run(
        ["aws", "s3", "cp", "--only-show-errors", f"s3://{bucket}/{key}", "-"],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise SystemExit(f"ERROR: no published bundle found at s3://{bucket}/{key}")
    return proc.stdout


def s3_download_file(bucket: str, key: str, dst: Path) -> None:
    if boto3 is not None:
        boto3.client("s3", region_name=REGION).download_file(bucket, key, str(dst))
        return
    subprocess.run(["aws", "s3", "cp", "--only-show-errors", f"s3://{bucket}/{key}", str(dst)], check=True)


def channel_prefix(channel: str) -> str:
    return f"{PREFIX_ROOT}/{channel}"


def bundle_key(channel: str, bundle_sha256: str) -> str:
    return f"{channel_prefix(channel)}/bundles/{bundle_sha256}.tgz"


def latest_key(channel: str) -> str:
    return f"{channel_prefix(channel)}/latest.json"


def manifest_for(*, channel: str, bundle_sha256: str, source: str) -> dict:
    return {
        "schema_version": 1,
        "channel": channel,
        "bundle_sha256": bundle_sha256,
        "bundle_key": bundle_key(channel, bundle_sha256),
        "bucket": resolve_bucket(),
        "source": source,
        "published_at": now_iso(),
    }


def publish(bundle_path: Path, *, channel: str, source: str) -> dict:
    bucket = resolve_bucket()
    bundle_sha256 = sha256_file(bundle_path)
    manifest = manifest_for(channel=channel, bundle_sha256=bundle_sha256, source=source)

    s3_upload_file(bucket, manifest["bundle_key"], bundle_path)
    s3_put_json(bucket, latest_key(channel), manifest)
    return manifest


def load_latest(*, channel: str) -> dict:
    bucket = resolve_bucket()
    body = s3_get_text(bucket, latest_key(channel))
    return json.loads(body)


def fetch_latest(*, channel: str, output: Path, manifest_output: Path | None) -> dict:
    manifest = load_latest(channel=channel)
    output.parent.mkdir(parents=True, exist_ok=True)
    s3_download_file(manifest["bucket"], manifest["bundle_key"], output)
    actual_sha = sha256_file(output)
    if actual_sha != manifest["bundle_sha256"]:
        raise SystemExit(
            f"ERROR: bundle sha mismatch for s3://{manifest['bucket']}/{manifest['bundle_key']}: "
            f"expected {manifest['bundle_sha256']}, got {actual_sha}"
        )
    if manifest_output is not None:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish or fetch Agent Cody deploy bundles")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_publish = sub.add_parser("publish")
    p_publish.add_argument("--bundle", required=True)
    p_publish.add_argument("--channel", default=DEFAULT_CHANNEL)
    p_publish.add_argument("--source", default="cody-refresh")

    p_fetch = sub.add_parser("fetch-latest")
    p_fetch.add_argument("--output", required=True)
    p_fetch.add_argument("--channel", default=DEFAULT_CHANNEL)
    p_fetch.add_argument("--manifest-output")

    p_latest = sub.add_parser("latest")
    p_latest.add_argument("--channel", default=DEFAULT_CHANNEL)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "publish":
        manifest = publish(Path(args.bundle), channel=args.channel, source=args.source)
    elif args.cmd == "fetch-latest":
        manifest = fetch_latest(
            channel=args.channel,
            output=Path(args.output),
            manifest_output=Path(args.manifest_output) if args.manifest_output else None,
        )
    else:
        manifest = load_latest(channel=args.channel)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
