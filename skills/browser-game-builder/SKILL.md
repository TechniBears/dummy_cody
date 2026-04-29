---
name: browser-game-builder
description: Generate simple self-contained browser games as single HTML files and automatically deploy them to the Telegram Mini App games platform. Use when the user asks to build, create, or generate a browser game, mini-game, arcade game, or any playable game that runs in a web browser. Examples include Snake, Pong, Flappy Bird clones, Breakout, Tetris, memory card games, click-tap games, or any other simple 2D game concept. Always deploys automatically to CloudFront and updates the Telegram bot — no manual steps needed.
---

# browser-game-builder

Generate complete, playable browser games and deploy them live to the Telegram Mini App platform automatically.

## Infrastructure

- **Games dir:** `/opt/openclaw/.openclaw/workspace/games/`
- **S3 bucket:** `agent-cody-games-ACCOUNT_ID` (us-east-1) — replace ACCOUNT_ID with your AWS account
- **CloudFront:** `https://YOUR_CLOUDFRONT_DOMAIN` (permanent, HTTPS)
- **Bot:** `@YOUR_BOT_NAME` — token in `/run/openclaw/env`
- **Upload script:** `/opt/openclaw/.openclaw/workspace/scripts/upload_games.py`
- **Bot update script:** `/opt/openclaw/.openclaw/workspace/scripts/setup_botfather.py`

## Workflow — always follow this order

1. Write the game HTML to `/opt/openclaw/.openclaw/workspace/games/<game-name>.html`
2. Update `/opt/openclaw/.openclaw/workspace/games/index.html` to include the new game card
3. Run `python3 /opt/openclaw/.openclaw/workspace/scripts/upload_games.py`
4. Run `python3 /opt/openclaw/.openclaw/workspace/scripts/setup_botfather.py` (updates menu button + sends game message to the principal)
5. Tell the principal the game is live with the direct URL

## Telegram auth (mandatory)

Every game MUST include these two script tags in `<head>` before any other scripts:

```html
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<script src="tg-auth.js"></script>
```

And the entire game JS must be wrapped in the auth gate:

```js
if (!TG_AUTH.init()) { /* blocked */ }
else {
  // ... all game code here ...
} // end TG_AUTH gate
```

`tg-auth.js` is already in the games dir and served from CloudFront. It:
- Blocks non-Telegram access with a lock screen
- Calls `tg.ready()` and `tg.expand()` 
- Exposes `window.TG_USER` and `window.TG_THEME`

## Output format

Always produce **one `.html` file** with:
- All CSS inlined in `<style>`
- All game logic in `<script>` — vanilla JS only, no frameworks or CDN imports (except the two Telegram scripts above)
- Canvas-based rendering preferred; DOM-based acceptable for card/puzzle games
- Mobile-friendly: tap/swipe events alongside mouse/keyboard
- Visible title and brief on-screen controls

## Game quality bar

- Game must start on page load or on a clear "Start" button
- Win/lose/score state tracked and displayed
- Game loop must use `requestAnimationFrame` (not `setInterval`) for canvas games
- Keyboard + touch controls labeled on screen
- Responsive: playable at 360px wide minimum

## index.html — update on every new game

Add a new `<a>` card to the grid in `index.html`. Pattern:

```html
<a href="game-name.html">
  <div class="icon">🎮</div>
  GAME NAME
</a>
```

## Common game templates

| Game | Rendering | Notes |
|------|-----------|-------|
| Snake | Canvas | Grid-based, arrow keys |
| Breakout/Arkanoid | Canvas | Ball physics, brick grid |
| Pong | Canvas | Two-paddle, AI for single-player |
| Flappy Bird | Canvas | Gravity loop, gap pipes |
| Tetris | Canvas | Rotation, line clear |
| Memory cards | DOM | Flip pairs, match tracking |
| Whack-a-mole | DOM | Timer, score counter |
| 2048 | DOM | Slide/merge grid |

## References

- See `references/game-patterns.md` for reusable JS patterns (game loop, collision detection, input handling)
