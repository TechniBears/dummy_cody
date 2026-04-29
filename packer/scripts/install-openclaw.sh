#!/usr/bin/env bash
# Install OpenClaw pinned to a specific CalVer release.
# OPENCLAW_VERSION is set by the Packer template's environment_vars.
set -euxo pipefail

: "${OPENCLAW_VERSION:?OPENCLAW_VERSION must be set by Packer}"

echo "Installing openclaw@${OPENCLAW_VERSION}"
npm install -g --no-fund --no-audit "openclaw@${OPENCLAW_VERSION}"

# Verify
openclaw --version || which openclaw
node --version
npm ls -g openclaw

# Record pin for runtime verification (Gateway boot checks this against installed version)
echo "${OPENCLAW_VERSION}" > /opt/openclaw/OPENCLAW_VERSION
chown openclaw:openclaw /opt/openclaw/OPENCLAW_VERSION

# DO NOT run `openclaw onboard` during AMI build — that does interactive config that only
# makes sense on the actual deployed VM. Runtime init script (cloud-init) handles it.

echo "===== install-openclaw.sh complete (openclaw@${OPENCLAW_VERSION}) ====="
