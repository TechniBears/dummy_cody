---
name: memory-read
description: Read Cody's temporal Neo4j memory graph. Use when drafting, briefing, or answering questions about current or historical contact/deal state.
homepage: https://github.com/getzep/graphiti
metadata: {"openclaw":{"emoji":"🔎","os":["linux"],"requires":{"bins":["memory-read"]},"model":"amazon-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"}}
---

# memory-read

Query Cody's graph memory through the `memory-read` helper.

## Required arguments

- `query` — free-text entity, predicate, or value search term

## Optional arguments

- `as-of` — ISO timestamp when you need a historical view
- `include-history` — include superseded facts, not just current ones
- `limit` — default 10

## Command

```bash
memory-read \
  --query "$QUERY" \
  --limit "${LIMIT:-10}" \
  ${AS_OF:+--as-of "$AS_OF"} \
  ${INCLUDE_HISTORY:+--include-history} \
  --json
```

## Reading rules

- Prefer current facts unless the user explicitly asks for history or an as-of date.
- When facts conflict, explain the validity window rather than flattening them.
- When the graph is empty or unreachable, say so plainly and continue without pretending memory exists.
