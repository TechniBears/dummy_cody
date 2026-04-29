#!/usr/bin/env python3
"""Print a fresh Microsoft Graph access token, refreshing via MSAL if expired.

Reads the wrapped MSAL cache from AWS Secrets Manager, runs
acquire_token_silent, writes the updated cache back if it rotated, and
prints the access_token to stdout. Non-zero exit + diagnostic on stderr
on any failure (so a caller can bail safely).

Env:
  GRAPH_MSAL_SECRET_ID  default: agent-cody/graph-msal-token-cache
  AWS_REGION            default: us-east-1
"""
import json
import os
import sys

import boto3
import msal

SECRET_ID = os.environ.get("GRAPH_MSAL_SECRET_ID", "agent-cody/graph-msal-token-cache")
REGION = os.environ.get("AWS_REGION", "us-east-1")
SCOPES = ["Mail.ReadWrite", "Mail.Send", "Files.ReadWrite", "User.Read"]


def die(msg, code=1):
    print(f"graph-token-fresh: {msg}", file=sys.stderr)
    sys.exit(code)


sm = boto3.client("secretsmanager", region_name=REGION)
try:
    wrapper = json.loads(sm.get_secret_value(SecretId=SECRET_ID)["SecretString"])
except Exception as e:
    die(f"could not read secret {SECRET_ID}: {e}")

client_id = wrapper.get("client_id")
authority = wrapper.get("authority")
cache_str = wrapper.get("cache")
if not (client_id and authority and cache_str):
    die("secret is missing client_id/authority/cache; re-run msal-device-code.py")

cache = msal.SerializableTokenCache()
cache.deserialize(cache_str)

app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)
accounts = app.get_accounts()
if not accounts:
    die("no accounts in MSAL cache; re-run msal-device-code.py")

result = app.acquire_token_silent(SCOPES, account=accounts[0])
if not result or "access_token" not in result:
    die(f"silent refresh failed (refresh token may have expired): {result}")

if cache.has_state_changed:
    wrapper["cache"] = cache.serialize()
    try:
        sm.put_secret_value(SecretId=SECRET_ID, SecretString=json.dumps(wrapper))
    except Exception as e:
        die(f"refreshed token but failed to persist to Secrets Manager: {e}", code=3)

print(result["access_token"])
