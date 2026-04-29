#!/usr/bin/env python3
"""Smoke-test the stored Graph token end-to-end.

Proves three things:
  1. The MSAL token cache loads correctly from Secrets Manager.
  2. MSAL can acquire a fresh access_token from the cached refresh_token (silent flow).
  3. The token authenticates real Graph API calls (/me + /me/messages).

If this script succeeds, every Cody skill that talks to Graph is unblocked.
If it fails, we find out now (not when Cody tries to draft an email for the first time).
"""
from __future__ import annotations

import json
import os
import sys

import boto3
import msal
import urllib.request
import urllib.error

SECRET_ID = os.environ.get("GRAPH_MSAL_SECRET", "agent-cody/graph-msal-token-cache")
REGION = os.environ.get("AWS_REGION", "us-east-1")
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def graph_get(url: str, token: str) -> dict:
    """Minimal HTTP client so we don't pull in requests just for a smoke test."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8", "replace"), "status": e.code}


def main() -> int:
    # Pull the secret
    sm = boto3.client("secretsmanager", region_name=REGION)
    blob = json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])
    print(f"secret user={blob.get('user')}  scopes={blob.get('scopes')}")

    # Rehydrate the MSAL cache
    cache = msal.SerializableTokenCache()
    cache.deserialize(blob["cache"])

    app = msal.PublicClientApplication(
        blob["client_id"],
        authority=blob["authority"],
        token_cache=cache,
    )

    # acquire_token_silent reuses the access_token if still valid, or transparently uses
    # the refresh_token to get a fresh one. This is the exact code path Cody will use.
    accounts = app.get_accounts()
    if not accounts:
        print("FAIL: no accounts in cache — something's off with the serialize format.")
        return 2

    result = app.acquire_token_silent(scopes=blob["scopes"], account=accounts[0])
    if not result or "access_token" not in result:
        print(f"FAIL: silent token acquisition failed. Got: {json.dumps(result, indent=2) if result else 'None'}")
        return 3

    token = result["access_token"]
    print(f"acquired access_token ({len(token)} chars); expires_in={result.get('expires_in')}s")
    print(f"from_cache={result.get('token_source', 'unknown')}")

    # Call 1: /me — proves basic identity
    me = graph_get(f"{GRAPH_BASE}/me", token)
    if "error" in me:
        print(f"FAIL: /me call rejected: {me}")
        return 4
    print(f"/me  → userPrincipalName={me.get('userPrincipalName')}  displayName={me.get('displayName')}  id={me.get('id', '')[:16]}...")

    # Call 2: /me/messages — proves Mail.ReadWrite scope actually works on the user's mailbox
    msgs = graph_get(f"{GRAPH_BASE}/me/messages?$top=1&$select=subject,from,receivedDateTime", token)
    if "error" in msgs:
        print(f"FAIL: /me/messages call rejected: {msgs}")
        return 5
    items = msgs.get("value", [])
    if items:
        m = items[0]
        frm = m.get("from", {}).get("emailAddress", {}).get("address", "<unknown>")
        print(f"/me/messages → latest: \"{m.get('subject', '<no subject>')}\" from {frm} at {m.get('receivedDateTime')}")
    else:
        print("/me/messages → mailbox reachable but empty")

    # If MSAL refreshed the access_token silently, re-persist the cache so next time uses the new state.
    if cache.has_state_changed:
        sm.put_secret_value(SecretId=SECRET_ID, SecretString=json.dumps({**blob, "cache": cache.serialize()}))
        print("cache state changed — re-persisted to Secrets Manager")

    print("\nOK — Graph auth path is fully working.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
