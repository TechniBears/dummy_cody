"""
setup_botfather.py — run after uploading new games.
Updates bot commands, menu button, and sends the principal a fresh games menu.
"""
import urllib.request, json, os, re

TOKEN = open('/run/openclaw/env').read().split('TELEGRAM_BOT_TOKEN=')[1].split()[0]
BASE = f"https://api.telegram.org/bot{TOKEN}"
CF_URL = 'https://YOUR_CLOUDFRONT_DOMAIN'
CHAT_ID = 000000000
GAMES_DIR = '/opt/openclaw/.openclaw/workspace/games'

GAME_META = {
    'snake':    {'emoji': '🐍', 'label': 'Snake'},
    'breakout': {'emoji': '🧱', 'label': 'Breakout'},
    'pong':     {'emoji': '🏓', 'label': 'Pong'},
    'tetris':   {'emoji': '🟦', 'label': 'Tetris'},
    'flappy':   {'emoji': '🐦', 'label': 'Flappy'},
    'memory':   {'emoji': '🃏', 'label': 'Memory'},
    'whack':    {'emoji': '🔨', 'label': 'Whack-a-Mole'},
    '2048':     {'emoji': '🔢', 'label': '2048'},
}

def api(method, data):
    url = f"{BASE}/{method}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

# Discover all games
games = []
for fname in sorted(os.listdir(GAMES_DIR)):
    if not fname.endswith('.html') or fname == 'index.html':
        continue
    name = fname.replace('.html', '')
    meta = next((v for k, v in GAME_META.items() if k in name), {'emoji': '🎮', 'label': name.title()})
    games.append({'name': name, 'file': fname, **meta})

print(f"Found {len(games)} game(s): {[g['name'] for g in games]}")

# Build commands list
commands = [{'command': g['name'], 'description': f"{g['emoji']} Play {g['label']}"} for g in games]
commands += [
    {'command': 'games', 'description': '🕹 All games'},
    {'command': 'start', 'description': '👾 Start'},
]
api('setMyCommands', {'commands': commands})
print("Commands updated")

# Update menu button
api('setChatMenuButton', {
    'menu_button': {
        'type': 'web_app',
        'text': '🎮 Games',
        'web_app': {'url': f'{CF_URL}/index.html'}
    }
})
print("Menu button updated")

# Build inline keyboard (2 per row)
rows = []
for i in range(0, len(games), 2):
    row = []
    for g in games[i:i+2]:
        row.append({'text': f"{g['emoji']} {g['label']}", 'web_app': {'url': f"{CF_URL}/{g['file']}"}})
    rows.append(row)
rows.append([{'text': '🕹 All Games', 'web_app': {'url': f'{CF_URL}/index.html'}}])

# Send to the principal
r = api('sendMessage', {
    'chat_id': CHAT_ID,
    'text': f"🎮 *Games updated* — {len(games)} game(s) available",
    'parse_mode': 'Markdown',
    'reply_markup': {'inline_keyboard': rows}
})
print(f"Sent menu message: {r['result']['message_id']}")
print(f"\nBase URL: {CF_URL}")
