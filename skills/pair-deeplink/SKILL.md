---
name: pair-deeplink
description: |
  Intercept /start <pair_id> messages on the Telegram channel before the
  built-in pairing plugin sees them. POST the pair_id + chat_id to the
  Cody dashboard; reply to the user with the pair outcome.
match:
  channel: telegram
  command: /start
  argument_regex: "^[A-Za-z0-9_-]{22}$"
priority: 100
scopes:
  - secrets.read:agent-cody/dashboard/bot-callback-secret
  - egress:https:DASHBOARD_HOST
env:
  DASHBOARD_URL: https://cody-dash.internal  # override per env; see 00-how-it-actually-works.md
  BOT_CALLBACK_SECRET_NAME: agent-cody/dashboard/bot-callback-secret
---

# pair-deeplink skill

## When to fire

This skill runs only when the incoming Telegram message is **exactly** of the
form `/start <PAYLOAD>` where `<PAYLOAD>` matches `^[A-Za-z0-9_-]{22}$` —
the 22-character opaque `pair_id` shape minted by the Cody dashboard.

Any other `/start` (no arg, wrong-length arg, legacy 8-char OpenClaw pairing
codes) is **not** a match; those fall through to the built-in pairing plugin
as before. This preserves the existing `username / CODE`-style flow.

## What to do

1. Extract `pair_id = <PAYLOAD>`.
2. From the Telegram update, read:
   - `chat_id      = message.chat.id`
   - `username     = message.from.username` (may be null)
   - `first_name   = message.from.first_name` (may be null)
   - `last_name    = message.from.last_name` (may be null)
3. Fetch `BOT_CALLBACK_SECRET` from Secrets Manager at the name in
   `BOT_CALLBACK_SECRET_NAME`.
4. `POST {DASHBOARD_URL}/api/bot/pair-callback` with:
   ```
   Content-Type: application/json
   X-Bot-Secret: <BOT_CALLBACK_SECRET>
   ```
   Body:
   ```json
   {
     "pair_id":    "<22-char-payload>",
     "chat_id":    <integer>,
     "username":   "<string|null>",
     "first_name": "<string|null>",
     "last_name":  "<string|null>"
   }
   ```
5. Interpret the response and reply to the Telegram chat:
   - `200` with `{ok:true, identity:{first_name}}` — reply:
     `"Paired. Welcome${first_name ? ', ' + first_name : ''}. You're all set."`
   - `401 bad_secret` — log error; **do not disclose** to the user; reply
     with generic: `"Couldn't verify this link. Please try again from the dashboard."`
   - `400 pair_id_and_chat_id_required` — reply:
     `"This pair link looks malformed. Open the dashboard and tap Pair again."`
   - `404 pair_pair_not_found` — reply:
     `"That pair link isn't valid. Open the dashboard and tap Pair again."`
   - `410 pair_already_consumed` — reply:
     `"That pair link was already used. Tap Pair again on the dashboard to get a fresh one."`
   - `410 pair_expired` — reply:
     `"That pair link expired. Tap Pair again on the dashboard to get a fresh one."`
   - any 5xx / network error — log, reply:
     `"Couldn't reach Cody's dashboard. Try again in a minute."`
6. In all cases, emit an audit record with `source="pair-deeplink"`,
   `pair_id_prefix=<first 4 chars>`, `chat_id`, `outcome=<status>`.

## Safety rules

- **Never** log the full `pair_id` (first 4 chars only). Treat it as a
  short-lived capability.
- **Never** log the `X-Bot-Secret` value.
- **Never** fall back to the built-in pairing plugin when this skill has
  already replied — set the "handled" flag on the update.
- **Never** follow redirects from the dashboard POST. TLS required.
- Time out the POST at 5 seconds.

## Deploy checklist (Bee, when you're back on the gateway)

1. Copy this skill into the repo (already done): `skills/pair-deeplink/SKILL.md`
2. From your laptop, push it to the gateway:
   ```bash
   scp skills/pair-deeplink/SKILL.md \
     ec2-user@<gateway-ip>:/opt/openclaw/workspace/skills/pair-deeplink/
   ```
   (Or via `scripts/openclaw-init.sh` — it already copies all of `skills/` at
   boot per line 223-227.)
3. Create the Secrets Manager secret with the SAME value that's in
   `dashboard/.env.local`:
   ```bash
   aws secretsmanager create-secret \
     --name agent-cody/dashboard/bot-callback-secret \
     --secret-string '{"value":"<paste BOT_CALLBACK_SECRET here>"}'
   ```
4. Extend `agent-cody-gw-role` to include
   `secretsmanager:GetSecretValue` on
   `arn:aws:secretsmanager:<region>:<acct>:secret:agent-cody/dashboard/*`
   (already covered by the existing wildcard on `agent-cody/*` per
   `terraform/iam.tf:36-42`).
5. Set `DASHBOARD_URL` in `/run/openclaw/env` on the gateway to whatever
   address the dashboard ends up on (Tailscale name, CloudFront domain, etc.).
6. Restart: `sudo systemctl restart openclaw`.
7. Confirm the skill is registered:
   `openclaw-cli skills list | grep pair-deeplink`
8. From another Telegram account, open
   `https://t.me/Ibn_3bdo_bot?start=<paste-a-minted-pair_id>` → tap Start →
   should see the "Paired. Welcome, <name>." reply within ~2 seconds, and
   the dashboard's `/gate` should flip to Welcome Back within the next poll.

## Rollback

If the skill misbehaves:
```bash
sudo rm /opt/openclaw/workspace/skills/pair-deeplink/SKILL.md
sudo systemctl restart openclaw
```
Built-in pairing plugin takes over again; no state corruption.

## Testing without deploying

Until this skill is on the gateway, you can simulate the full flow end-to-end
by running (with the pair_id from the dashboard URL and the secret from
`dashboard/.env.local`):

```bash
curl -X POST http://localhost:3000/api/bot/pair-callback \
  -H "X-Bot-Secret: <BOT_CALLBACK_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
    "pair_id": "<22-char-from-tme-url>",
    "chat_id": 000000000,
    "username": "your_handle",
    "first_name": "YourFirst",
    "last_name": "YourLast"
  }'
```

The dashboard's `/gate` will flip to Welcome Back identically. This is how
the demo in `evidence/2026-04-20-dashboard-pair-flow/12-gate-paired.png` was
produced.
