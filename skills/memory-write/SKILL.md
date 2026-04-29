---
name: memory-write
description: Write a temporal fact into Cody's Neo4j memory graph. Use when the user explicitly corrects Cody, updates a deal, changes a recipient preference, or confirms a high-stakes fact. Invalidates prior active facts for the same entity and predicate instead of overwriting them.
homepage: https://github.com/getzep/graphiti
metadata: {"openclaw":{"emoji":"🧠","os":["linux"],"requires":{"bins":["memory-write"]},"model":"amazon-bedrock/us.anthropic.claude-haiku-4-5-20251001-v1:0"}}
---

# memory-write

Use the `memory-write` helper to write temporal facts into Cody's graph memory.

## Required arguments

- `entity` — subject entity name, e.g. `Sarah`
- `entity-type` — e.g. `person`, `deal`, `company`, `thread`
- `predicate` — e.g. `register`, `deal_value`, `next_step`, `primary_contact`
- `value` — string value to store

## Recommended arguments

- `target-entity` and `target-type` when the fact points at another entity
- `source` — short tag like `user_correction`, `voice_note`, `briefing`, `operator`
- `quote` — raw phrase from the user if useful for auditability
- `confidence` — 0.0 to 1.0

## Command

```bash
memory-write \
  --entity "$ENTITY" \
  --entity-type "$ENTITY_TYPE" \
  --predicate "$PREDICATE" \
  --value "$VALUE" \
  ${TARGET_ENTITY:+--target-entity "$TARGET_ENTITY"} \
  ${TARGET_TYPE:+--target-type "$TARGET_TYPE"} \
  --source "${SOURCE:-manual}" \
  --source-type "${SOURCE_TYPE:-operator}" \
  ${QUOTE:+--quote "$QUOTE"} \
  --confidence "${CONFIDENCE:-0.9}" \
  --json
```

## Behavioral rules

- If the same active fact already exists, treat it as `unchanged`.
- If a different active fact exists for the same entity + predicate, it must be closed with `valid_to` and the new fact becomes current.
- Never silently write a high-stakes fact that the user has not confirmed.
- Summarize back to the user what changed.
