#!/usr/bin/env python3
"""Graphiti-ready temporal memory shim for Agent Cody.

This talks directly to the Neo4j memory VM over Neo4j's transactional HTTP API.
It intentionally models the core behavior Cody needs right now:
- current facts
- temporal invalidation instead of overwrite
- timeline reads
- narrow command surface suitable for OpenClaw allowlisting

This is not a full replacement for graphiti-core. It is the pragmatic bridge until we
choose an LLM/embedder path that Graphiti core can use cleanly in this AWS setup.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover - optional when password is provided by env/file
    boto3 = None

DEFAULT_URL = os.environ.get("GRAPHITI_NEO4J_URL", "http://localhost:7474")
DEFAULT_USER = os.environ.get("GRAPHITI_NEO4J_USER", "neo4j")
DEFAULT_SECRET = os.environ.get("GRAPHITI_NEO4J_PASSWORD_SECRET_ID", "agent-cody/neo4j-password")
DEFAULT_REGION = os.environ.get("AWS_REGION", "us-east-1")
DEFAULT_GROUP = os.environ.get("GRAPHITI_GROUP_ID", "agent-cody")
DB_NAME = os.environ.get("GRAPHITI_NEO4J_DB", "neo4j")


@dataclass
class Neo4jConfig:
    url: str
    user: str
    password: str
    db: str = DB_NAME


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_password(args: argparse.Namespace) -> str:
    if getattr(args, "password", None):
        return args.password

    env_password = os.environ.get("GRAPHITI_NEO4J_PASSWORD")
    if env_password:
        return env_password

    password_file = getattr(args, "password_file", None) or os.environ.get("GRAPHITI_NEO4J_PASSWORD_FILE")
    if password_file:
        with open(password_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()

    secret_id = getattr(args, "password_secret", None) or DEFAULT_SECRET
    if boto3 is None:
        raise RuntimeError(
            "No Neo4j password available. Set GRAPHITI_NEO4J_PASSWORD or provide --password-file."
        )

    client = boto3.client("secretsmanager", region_name=getattr(args, "aws_region", None) or DEFAULT_REGION)
    raw = client.get_secret_value(SecretId=secret_id)["SecretString"]
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in ("password", "neo4j_password", "value"):
                if parsed.get(key):
                    return str(parsed[key])
    except json.JSONDecodeError:
        pass
    return raw.strip()


def http_json(config: Neo4jConfig, statements: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.dumps({"statements": statements}).encode("utf-8")
    base = config.url.rstrip("/")
    endpoint = f"{base}/db/{config.db}/tx/commit"
    token = base64.b64encode(f"{config.user}:{config.password}".encode("utf-8")).decode("ascii")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(exc.read().decode("utf-8", "replace")) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc)) from exc

    data = json.loads(body)
    errors = data.get("errors", [])
    if errors:
        raise RuntimeError(json.dumps(errors, indent=2))
    return data


def run_query(config: Neo4jConfig, statement: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = http_json(
        config,
        [{"statement": statement, "parameters": parameters or {}, "resultDataContents": ["row"]}],
    )
    results = data.get("results", [])
    if not results:
        return []
    columns = results[0].get("columns", [])
    rows = []
    for item in results[0].get("data", []):
        row = item.get("row", [])
        rows.append(dict(zip(columns, row)))
    return rows


def ensure_schema(config: Neo4jConfig) -> None:
    statements = [
        "CREATE CONSTRAINT memory_entity_identity IF NOT EXISTS FOR (e:MemoryEntity) REQUIRE (e.group_id, e.name, e.kind) IS UNIQUE",
        "CREATE CONSTRAINT memory_fact_id IF NOT EXISTS FOR (f:MemoryFact) REQUIRE f.id IS UNIQUE",
        "CREATE INDEX memory_entity_lookup IF NOT EXISTS FOR (e:MemoryEntity) ON (e.group_id, e.name)",
        "CREATE INDEX memory_fact_temporal IF NOT EXISTS FOR (f:MemoryFact) ON (f.group_id, f.predicate, f.valid_from, f.valid_to)",
    ]
    http_json(config, [{"statement": item} for item in statements])


def ensure_entity(config: Neo4jConfig, group_id: str, name: str, kind: str) -> dict[str, Any]:
    rows = run_query(
        config,
        """
        MERGE (e:MemoryEntity {group_id: $group_id, name: $name, kind: $kind})
        ON CREATE SET e.id = $entity_id, e.created_at = $now, e.updated_at = $now
        ON MATCH SET e.updated_at = $now
        RETURN e.id AS id, e.group_id AS group_id, e.name AS name, e.kind AS kind
        """,
        {
            "group_id": group_id,
            "name": name,
            "kind": kind,
            "entity_id": str(uuid4()),
            "now": now_iso(),
        },
    )
    return rows[0]


def list_active_facts(config: Neo4jConfig, group_id: str, entity_name: str, entity_type: str, predicate: str) -> list[dict[str, Any]]:
    return run_query(
        config,
        """
        MATCH (e:MemoryEntity {group_id: $group_id, name: $name, kind: $kind})-[:HAS_FACT]->(f:MemoryFact {predicate: $predicate})
        WHERE f.valid_to IS NULL
        RETURN f.id AS id, f.value AS value, f.valid_from AS valid_from, f.confidence AS confidence
        ORDER BY f.valid_from DESC
        """,
        {
            "group_id": group_id,
            "name": entity_name,
            "kind": entity_type,
            "predicate": predicate,
        },
    )


def close_fact(config: Neo4jConfig, fact_id: str, valid_to: str) -> None:
    run_query(
        config,
        """
        MATCH (f:MemoryFact {id: $fact_id})
        SET f.valid_to = $valid_to, f.status = 'superseded', f.updated_at = $valid_to
        RETURN f.id AS id
        """,
        {"fact_id": fact_id, "valid_to": valid_to},
    )


def create_fact(
    config: Neo4jConfig,
    group_id: str,
    entity_name: str,
    entity_type: str,
    predicate: str,
    value: str,
    confidence: float,
    source: str,
    source_type: str,
    quote: str | None,
    valid_from: str,
    target_name: str | None,
    target_type: str | None,
) -> dict[str, Any]:
    params = {
        "group_id": group_id,
        "entity_name": entity_name,
        "entity_type": entity_type,
        "predicate": predicate,
        "value": value,
        "confidence": confidence,
        "source": source,
        "source_type": source_type,
        "quote": quote,
        "valid_from": valid_from,
        "fact_id": str(uuid4()),
        "target_name": target_name,
        "target_type": target_type,
    }
    rows = run_query(
        config,
        """
        MATCH (e:MemoryEntity {group_id: $group_id, name: $entity_name, kind: $entity_type})
        CREATE (f:MemoryFact {
          id: $fact_id,
          group_id: $group_id,
          predicate: $predicate,
          value: $value,
          confidence: $confidence,
          source: $source,
          source_type: $source_type,
          quote: $quote,
          valid_from: $valid_from,
          valid_to: NULL,
          status: 'active',
          created_at: $valid_from,
          updated_at: $valid_from
        })
        CREATE (e)-[:HAS_FACT]->(f)
        WITH f
        CALL {
          WITH f
          WITH f WHERE $target_name IS NOT NULL AND $target_type IS NOT NULL
          MERGE (t:MemoryEntity {group_id: $group_id, name: $target_name, kind: $target_type})
          ON CREATE SET t.id = randomUUID(), t.created_at = $valid_from, t.updated_at = $valid_from
          ON MATCH SET t.updated_at = $valid_from
          CREATE (f)-[:TARGETS]->(t)
          RETURN t.name AS target_name, t.kind AS target_type
          UNION
          WITH f
          WITH f WHERE $target_name IS NULL OR $target_type IS NULL
          RETURN NULL AS target_name, NULL AS target_type
        }
        RETURN f.id AS id, f.predicate AS predicate, f.value AS value, f.valid_from AS valid_from, target_name, target_type
        """,
        params,
    )
    return rows[0]


def command_smoke(config: Neo4jConfig, args: argparse.Namespace) -> int:
    start = time.time()
    ensure_schema(config)
    rows = run_query(config, "RETURN 1 AS ok")
    payload = {
        "ok": True,
        "url": config.url,
        "db": config.db,
        "elapsed_ms": round((time.time() - start) * 1000, 2),
    }
    emit(payload, args)
    return 0


def command_write_fact(config: Neo4jConfig, args: argparse.Namespace) -> int:
    ensure_schema(config)
    valid_from = args.valid_from or now_iso()
    ensure_entity(config, args.group_id, args.entity, args.entity_type)
    if args.target_entity and args.target_type:
        ensure_entity(config, args.group_id, args.target_entity, args.target_type)

    active = list_active_facts(config, args.group_id, args.entity, args.entity_type, args.predicate)
    same = [item for item in active if item.get("value") == args.value]
    changed = [item for item in active if item.get("value") != args.value]

    for item in changed:
        close_fact(config, item["id"], valid_from)

    if same:
        payload = {
            "ok": True,
            "action": "unchanged",
            "group_id": args.group_id,
            "entity": args.entity,
            "entity_type": args.entity_type,
            "predicate": args.predicate,
            "value": args.value,
            "active_fact_id": same[0]["id"],
            "closed_fact_ids": [item["id"] for item in changed],
        }
        emit(payload, args)
        return 0

    created = create_fact(
        config=config,
        group_id=args.group_id,
        entity_name=args.entity,
        entity_type=args.entity_type,
        predicate=args.predicate,
        value=args.value,
        confidence=args.confidence,
        source=args.source,
        source_type=args.source_type,
        quote=args.quote,
        valid_from=valid_from,
        target_name=args.target_entity,
        target_type=args.target_type,
    )
    payload = {
        "ok": True,
        "action": "created",
        "group_id": args.group_id,
        "entity": args.entity,
        "entity_type": args.entity_type,
        "predicate": args.predicate,
        "value": args.value,
        "fact": created,
        "closed_fact_ids": [item["id"] for item in changed],
    }
    emit(payload, args)
    return 0


def command_read_facts(config: Neo4jConfig, args: argparse.Namespace) -> int:
    ensure_schema(config)
    params = {
        "group_id": args.group_id,
        "query": args.query.lower(),
        "limit": args.limit,
        "as_of": args.as_of,
        "include_history": args.include_history,
    }
    rows = run_query(
        config,
        """
        MATCH (e:MemoryEntity {group_id: $group_id})-[:HAS_FACT]->(f:MemoryFact)
        WHERE (
          toLower(e.name) CONTAINS $query OR
          toLower(e.kind) CONTAINS $query OR
          toLower(f.predicate) CONTAINS $query OR
          toLower(coalesce(f.value, '')) CONTAINS $query
        )
        AND (
          $include_history = true OR f.valid_to IS NULL
        )
        AND (
          $as_of IS NULL OR (
            f.valid_from <= $as_of AND (f.valid_to IS NULL OR f.valid_to >= $as_of)
          )
        )
        OPTIONAL MATCH (f)-[:TARGETS]->(t:MemoryEntity)
        RETURN
          e.name AS entity,
          e.kind AS entity_type,
          f.id AS fact_id,
          f.predicate AS predicate,
          f.value AS value,
          f.valid_from AS valid_from,
          f.valid_to AS valid_to,
          f.confidence AS confidence,
          f.source AS source,
          f.source_type AS source_type,
          f.quote AS quote,
          t.name AS target_entity,
          t.kind AS target_type
        ORDER BY coalesce(f.valid_to, '9999-12-31T23:59:59Z') DESC, f.valid_from DESC
        LIMIT $limit
        """,
        params,
    )
    payload = {
        "ok": True,
        "group_id": args.group_id,
        "query": args.query,
        "count": len(rows),
        "facts": rows,
    }
    emit(payload, args)
    return 0


def emit(payload: dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "json_output", False):
        print(json.dumps(payload, indent=2))
        return
    if payload.get("ok") and payload.get("action") == "created":
        print(f"Stored fact: {payload['entity']} [{payload['entity_type']}] -> {payload['predicate']} = {payload['value']}")
        if payload.get("closed_fact_ids"):
            print(f"Superseded prior facts: {', '.join(payload['closed_fact_ids'])}")
        return
    if payload.get("ok") and payload.get("action") == "unchanged":
        print(f"No change: active fact already matches {payload['entity']} -> {payload['predicate']} = {payload['value']}")
        return
    if payload.get("ok") and payload.get("facts") is not None:
        print(f"Found {payload['count']} fact(s) for query '{payload['query']}':")
        for fact in payload["facts"]:
            target = f" -> {fact['target_entity']} [{fact['target_type']}]" if fact.get("target_entity") else ""
            validity = f" ({fact['valid_from']} to {fact['valid_to'] or 'now'})"
            print(f"- {fact['entity']} [{fact['entity_type']}] :: {fact['predicate']} = {fact['value']}{target}{validity}")
        return
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Cody temporal memory on Neo4j")
    parser.add_argument("--neo4j-url", default=DEFAULT_URL)
    parser.add_argument("--neo4j-user", default=DEFAULT_USER)
    parser.add_argument("--password")
    parser.add_argument("--password-file")
    parser.add_argument("--password-secret", default=DEFAULT_SECRET)
    parser.add_argument("--aws-region", default=DEFAULT_REGION)
    parser.add_argument("--db", default=DB_NAME)
    parser.add_argument("--json", dest="json_output", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke = subparsers.add_parser("smoke", help="Test Neo4j connectivity and ensure schema")
    smoke.set_defaults(func=command_smoke)

    write_fact = subparsers.add_parser("write-fact", help="Write or update a temporal fact")
    write_fact.add_argument("--group-id", default=DEFAULT_GROUP)
    write_fact.add_argument("--entity", required=True)
    write_fact.add_argument("--entity-type", default="entity")
    write_fact.add_argument("--predicate", required=True)
    write_fact.add_argument("--value", required=True)
    write_fact.add_argument("--target-entity")
    write_fact.add_argument("--target-type")
    write_fact.add_argument("--source", default="manual")
    write_fact.add_argument("--source-type", default="operator")
    write_fact.add_argument("--quote")
    write_fact.add_argument("--confidence", type=float, default=0.9)
    write_fact.add_argument("--valid-from")
    write_fact.set_defaults(func=command_write_fact)

    read_facts = subparsers.add_parser("read-facts", help="Search current or historical facts")
    read_facts.add_argument("--group-id", default=DEFAULT_GROUP)
    read_facts.add_argument("--query", required=True)
    read_facts.add_argument("--limit", type=int, default=10)
    read_facts.add_argument("--as-of")
    read_facts.add_argument("--include-history", action="store_true")
    read_facts.set_defaults(func=command_read_facts)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        config = Neo4jConfig(
            url=args.neo4j_url,
            user=args.neo4j_user,
            password=read_password(args),
            db=args.db,
        )
        return args.func(config, args)
    except Exception as exc:  # pragma: no cover - error path for operator CLI
        if getattr(args, "json_output", False):
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        else:
            print(f"graphiti-memory: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
