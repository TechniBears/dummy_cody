# Agent Cody

Personal AI operator -- configurable per principal. Telegram voice/text in, Outlook drafts out, Graphiti memory that gets smarter over time.

Runs on a single EC2 gateway (us-east-1) with OpenClaw, Bedrock, and a Neo4j memory sidecar.

## Quick start
**you need to know some aws here or ask claude to write you a script at this point tbh**
Push to `main` and CI handles everything: bundle to S3, SSM to gateway, restart. No laptop scripts needed.

```
git push origin main    # CI publishes + deploys automatically
```
**hes retard but better everyday**
On Telegram, Cody responds to natural language. No skill names needed:
- "check my email" / "draft a reply to Sarah" / "what's on my calendar?"
- "/model sonnet" to switch models on the fly
- "what do you know about Acme?" to query memory

## Repo layout

```
scripts/     Gateway runtime: openclaw-init, renderers, admin helpers, skill binaries
skills/      Agent skills (SKILL.md + optional bin/). Auto-discovered by renderer
workspace/   Agent system prompt: IDENTITY, SKILLS, BOOTSTRAP, TOOLS, USER
terraform/   AWS infra (VPC, EC2, S3, IAM, KMS, SNS)
lambdas/     Send-approval Lambda chain
packer/      Gateway AMI builds
docs/        Architecture, security, roadmap, guides (numbered 00-11)
evidence/    Manual verification artifacts
.github/     CI: validate-agent-infra + publish-gateway-bundle
```

## How it works

1. Message arrives on Telegram (voice or text)
2. Voice notes get transcribed locally (whisper-ctranslate2)
3. Cody checks Graphiti memory for recipient/deal context
4. Drafts into Outlook via Graph API, queues for approval
5. The principal says SEND/EDIT/SKIP on Telegram
6. Morning brief runs daily at 07:30 Dubai time, scores inbox against memory

## Models

| Alias | Model | Use |
|---|---|---|
| `opus` | Claude Opus 4.6 (Bedrock) | default, drafting, hard reasoning |
| `opus-next` | Opus 4.7 (Bedrock) | premium experimental |
| `sonnet` | Sonnet 4.6 (Bedrock) | quick reasoning |
| `sonnet-1m` | Sonnet 4.5 1M (Bedrock) | long-context research |
| `haiku` | Haiku 4.5 (Bedrock) | memory ops, queue ops |
| `gemma` | Gemma 3 4B (local Ollama) | offline fallback |

## Deploy pipeline

```
push to main
  -> .github/workflows/publish-gateway-bundle.yml
    -> renders config, validates, tars bundle
    -> publishes to S3
    -> SSM: cody-admin --pull-latest on gateway
      -> openclaw-init.sh re-renders config, installs bins, syncs skills
      -> purges per-agent state (kills fallback-persistence bug)
      -> systemd restart
```

## Key files for developers

| File | What it does |
|---|---|
| `scripts/render_root_openclaw_config.py` | Single source of truth for model lineup + exec policy |
| `scripts/openclaw_exec_policy.py` | Tool allowlist (safeBins + profiles) |
| `scripts/openclaw-init.sh` | Gateway bootstrap (runs on every deploy) |
| `scripts/openclaw-admin-helper` | Root-owned maintenance (status/restart/pull-latest/set-model) |
| `scripts/set_primary_model.py` | Model switching helper |
| `scripts/validate_openclaw_config.py` | Config validator (runs pre-startup + CI) |
| `scripts/cody-refresh` | Laptop-side deploy tool (escape hatch, not primary path) |

## Design docs

Start with `docs/00-how-it-actually-works.md` for the plain-English walkthrough.
Full index in `docs/` numbered 00-11.
