#!/usr/bin/env python3
"""MSAL device-code flow for Microsoft Graph.

One-time bootstrap. Runs on the Gateway VM as the `openclaw` user.

1. Prints a verification URL + user code.
2. User opens URL in browser, enters code, authorizes the app.
3. Script polls Azure AD, receives tokens.
4. Token cache is encrypted with KMS + stored in Secrets Manager.

The agent's outlook-* skills read this cache at runtime, refresh tokens as needed,
and use the access token for Microsoft Graph API calls.

Scopes requested (per 05-research-findings.md §3.2):
  - Mail.ReadWrite   - read + create drafts, NOT send (send is Mail.Send)
  - Mail.Send        - send on behalf of user (via graph-sender Lambda only)
  - Files.ReadWrite.All
  - Sites.Read.All
  - offline_access   - enables refresh tokens
  - User.Read        - basic profile

Refresh token lifetime: 90 days of inactivity (non-configurable).
Each use mints a new RT, extending the window.

Requirements on Gateway VM:
  pip install msal boto3
"""
from __future__ import annotations

import json
import os
import sys

import boto3
import msal

# Optional log-file tee. Only used when running headless on the Gateway VM via SSM
# (where stdout isn't streamed until the command completes, so we tail a file to
# retrieve the device code before the user authenticates).
# Locally, stdout goes straight to your terminal — no log file needed.
LOG_FILE = os.environ.get("MSAL_LOG")

if LOG_FILE:
    class Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()

        def flush(self):
            for s in self.streams:
                s.flush()

    _log = open(LOG_FILE, "a", buffering=1)
    sys.stdout = Tee(sys.__stdout__, _log)

# Public client Azure AD app for MSAL device-code. This is the Microsoft-owned
# sample client registered for interactive desktop-app flows; no custom registration needed.
# If/when we want finer scope control, swap for our own App Registration (same Entra ID app
# that the dashboard SSO will use in Phase 3).
# Microsoft Graph Command Line Tools — first-party public client that supports BOTH
# personal Microsoft accounts (outlook.com, live.com, hotmail.com) AND work/school (M365).
# Azure CLI client (04b07795-…) is work-only, rejects personal accounts.
CLIENT_ID = os.environ.get("MSAL_CLIENT_ID", "14d82eec-204b-4c2f-b7e8-296a70dab67e")

# Authority choice:
#   /common     — accepts both MSA and AAD, but sometimes rejects MSA device-flow post-consent
#   /consumers  — MSA ONLY (outlook.com, live.com, hotmail.com). Required for personal accounts.
#   /organizations — AAD work/school only.
# Default to /consumers for personal Outlook; override via env if linking a work account.
AUTHORITY = os.environ.get("MSAL_AUTHORITY", "https://login.microsoftonline.com/consumers")
# Scope set tuned for PERSONAL Microsoft accounts (outlook.com, live.com, hotmail.com).
# Personal accounts cannot consent to Files.ReadWrite.All or Sites.Read.All (SharePoint-only),
# and Microsoft returns a generic "code expired" when any requested scope is unconsentable.
# Work/school accounts can override with MSAL_SCOPES env to include .All variants.
DEFAULT_SCOPES = [
    "Mail.ReadWrite",   # read + draft email
    "Mail.Send",         # send on behalf of user (only graph-sender Lambda calls this)
    "Files.ReadWrite",   # personal OneDrive — Excel sales tracker goes here
    "User.Read",         # basic profile for identity-consistency check
]
SCOPES = os.environ.get("MSAL_SCOPES", " ".join(DEFAULT_SCOPES)).split()
SECRET_ID = os.environ.get("GRAPH_MSAL_SECRET", "agent-cody/graph-msal-token-cache")
REGION = os.environ.get("AWS_REGION", "us-east-1")


def main() -> int:
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print("ERROR: device flow init failed:", json.dumps(flow, indent=2))
        return 2

    print()
    print("=" * 70)
    print("  MICROSOFT SIGN-IN REQUIRED")
    print("=" * 70)
    print(f"  1. Open:  {flow['verification_uri']}")
    print(f"  2. Code:  {flow['user_code']}")
    print(f"  3. Sign in with your M365 (or personal Microsoft) account.")
    print(f"  4. Approve the scopes: {', '.join(SCOPES)}")
    print("=" * 70)
    print(f"  (This script will wait up to {flow.get('expires_in', 900)}s.)")
    print()

    result = app.acquire_token_by_device_flow(flow)  # blocks until user completes

    if "access_token" not in result:
        print("ERROR: token acquisition failed:", json.dumps(result, indent=2))
        return 3

    print("OK: tokens acquired. Persisting to Secrets Manager...")
    cache_blob = cache.serialize()

    claims = result.get("id_token_claims", {}) or {}
    user_email = claims.get("preferred_username") or claims.get("email") or claims.get("upn") or "unknown"
    user_oid = claims.get("oid", "")
    user_name = claims.get("name", "")

    sm = boto3.client("secretsmanager", region_name=REGION)
    sm.put_secret_value(
        SecretId=SECRET_ID,
        SecretString=json.dumps({
            "cache": cache_blob,
            "scopes": SCOPES,
            "authority": AUTHORITY,
            "client_id": CLIENT_ID,
            "populated_at": claims.get("iat"),
            # Identity claims — used by dashboard SSO to verify the signed-in user
            # matches the MSAL-linked account. If they diverge, dashboard flags it.
            "user": user_email,
            "oid": user_oid,
            "name": user_name,
            "tid": claims.get("tid", ""),
        }),
    )

    print(f"OK: persisted for {user_email} (oid {user_oid[:8]}...). Cody can now use Microsoft Graph.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
