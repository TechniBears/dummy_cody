---
name: cody-admin
description: Inspect or repair the local Agent Cody gateway runtime through a narrow maintenance helper. Supports status, delayed restart, re-applying the last deployed server snapshot, and pulling the latest published deploy bundle from S3.
metadata: {"openclaw":{"emoji":"🛠️","os":["linux"],"requires":{"bins":["cody-admin"]}}}
---

# cody-admin

Use the `cody-admin` helper for bounded gateway maintenance.

## When to use

- The user explicitly asks whether the gateway is healthy, stale, or needs a restart.
- A helper bin or config change was deployed but the runtime behavior still looks stale.
- The user wants to re-apply the last deployed server snapshot from inside OpenClaw.

## When NOT to use

- The user wants new laptop-side repo changes shipped to the gateway. `cody-admin` cannot pull your laptop repo.
- The problem is inside Outlook, Graph, or S3 and a gateway restart would not change it.
- You need arbitrary shell access. Do not improvise around this helper.

## Commands

Status:

```bash
cody-admin --status --json
```

Delayed restart:

```bash
cody-admin --restart --json
```

Re-apply the last deployed server snapshot, then restart:

```bash
cody-admin --refresh-snapshot --json
```

Pull the latest published deploy bundle from S3, apply it locally, then restart:

```bash
cody-admin --pull-latest --json
```

## Notes

- `--restart` is delayed by a couple seconds so the current command can return before OpenClaw restarts.
- `--refresh-snapshot` only uses the root-owned snapshot already present on the gateway. It does not fetch new repo state from the laptop.
- `--pull-latest` downloads the latest published bundle from S3. That bundle must have been published earlier by `scripts/cody-refresh` or equivalent automation.
- Report helper errors verbatim. Do not suggest unrelated allowlist edits if `cody-admin` itself is present.
