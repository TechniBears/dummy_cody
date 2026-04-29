import urllib.request, json

TOKEN = open('/run/openclaw/env').read().split('TELEGRAM_BOT_TOKEN=')[1].split()[0]
BASE = f"https://api.telegram.org/bot{TOKEN}"

def api(method, data={}):
    url = f"{BASE}/{method}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
        print(f"{method}: {result.get('result', result)}")
        return result

# 1. Set commands only visible to the principal (scope: specific chat)
api('setMyCommands', {
    'commands': [
        {'command': 'snake',     'description': '🐍 Play Snake'},
        {'command': 'solitaire', 'description': '🃏 Play Solitaire'},
        {'command': 'tictactoe', 'description': '⭕ Play Tic-Tac-Toe'},
        {'command': 'games',     'description': '🎮 All games'},
        {'command': 'start',     'description': '👾 Start'},
    ],
    'scope': {
        'type': 'chat',
        'chat_id': 000000000
    }
})

# 2. Clear commands for all other users (empty = no commands shown)
api('deleteMyCommands', {
    'scope': {'type': 'all_private_chats'}
})
api('deleteMyCommands', {
    'scope': {'type': 'all_group_chats'}
})
api('deleteMyCommands', {
    'scope': {'type': 'all_chat_administrators'}
})

# 3. Remove menu button for everyone except the principal
api('setChatMenuButton', {
    'chat_id': 000000000,
    'menu_button': {
        'type': 'web_app',
        'text': '🎮 Games',
        'web_app': {'url': 'https://YOUR_CLOUDFRONT_DOMAIN/index.html'}
    }
})

# Remove default menu button (for anyone else who somehow lands here)
api('setChatMenuButton', {
    'menu_button': {'type': 'default'}
})

print("\nDone — bot commands and menu locked to principal only.")
