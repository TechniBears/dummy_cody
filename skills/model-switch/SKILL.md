---
name: model-switch
description: Switch the primary inference model used by the agent loop. Use when the user says "/model <name>" or "switch to <model>", or asks which model is active. Aliases: opus (default), opus-next, sonnet, sonnet-1m, haiku, gemma. Returns the new primary and fallback chain.
metadata: {"openclaw":{"emoji":"🔀","os":["linux"],"requires":{"bins":["model-switch"]}}}
---

# model-switch — change the primary inference model

Switches `agents.defaults.model.primary` in the managed OpenClaw config and
restarts the gateway. Per-agent state is purged on restart so the new model
sticks (mitigates OpenClaw bug #47705 where a transient fallback would
permanently overwrite the primary).

## When to use

- User: "/model opus" / "switch to sonnet" / "use the 1M model" / "go local"
- User: "what model are you on?" — run with no argument to show current

## Aliases

| Alias | Model | When to use |
|---|---|---|
| `opus` | claude-opus-4-6 (Bedrock) | default daily driver, drafting, hard reasoning |
| `opus-next` | claude-opus-4-7 (Bedrock) | premium experimental, costs more |
| `sonnet` | claude-sonnet-4-6 (Bedrock) | quick reasoning, cheaper than Opus |
| `sonnet-1m` | claude-sonnet-4-5 1M-context (Bedrock) | research, long-context work |
| `haiku` | claude-haiku-4-5 (Bedrock) | small ops, summarisation, fastest |
| `gemma` | gemma3:4b (local Ollama) | offline / sovereign, slower |

## Command

```bash
model-switch "$ALIAS"
```

## Report to user

Format the JSON result as:

> Switched to **<primary>**. Fallback chain: <fallbacks joined by " → ">.
