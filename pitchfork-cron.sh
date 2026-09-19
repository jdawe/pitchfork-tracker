#!/usr/bin/env bash
# Pitchfork daily scrape + Telegram delivery — runs via launchd, no agent needed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "/Users/jd/.openclaw/workspace/client.env" ]] && source "/Users/jd/.openclaw/workspace/client.env"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(/usr/bin/jq -r .telegramBotToken /Users/jd/.openclaw/secrets/openclaw-secrets.json)}"
CHAT_ID="${TELEGRAM_CHAT_ID:-8040682185}"

# Run scrape
OUTPUT=$(python3 "$SCRIPT_DIR/pitchfork-daily.py" 2 2>&1)
echo "$OUTPUT"

# Parse counts
NEW=$(echo "$OUTPUT" | grep -oE 'scrape: ([0-9]+) new' | grep -oE '[0-9]+' | head -1 || echo "0")
TOTAL=$(echo "$OUTPUT" | grep -oE '([0-9]+) total' | grep -oE '[0-9]+' | head -1 || echo "?")

# Build + send the message in one python step.
#
# Two bugs fixed here (2026-07-29): this used parse_mode=Markdown with raw,
# unescaped album/artist/genre text. Any title containing * _ [ or ` produced
# malformed markup and Telegram rejected the whole send with HTTP 400 — the
# scrape still wrote to the DB, so it failed invisibly (e.g. "Sh*t" on 7/29,
# "diamond*" earlier). Genre was also wrapped in [brackets] = link syntax.
# Now uses HTML with html.escape() on every dynamic field.
#
# Values are passed via env rather than interpolated into the python source,
# so a quote or newline in a title can't break the script itself.
TODAY=$(date '+%Y-%m-%d')

DB_PATH="$SCRIPT_DIR/data/pitchfork.db" TODAY="$TODAY" NEW="$NEW" TOTAL="$TOTAL" \
CHAT_ID="$CHAT_ID" BOT_TOKEN="$BOT_TOKEN" python3 -c "
import os, sqlite3, html, urllib.request, urllib.parse, json

new, total = os.environ['NEW'], os.environ['TOTAL']

if new == '0':
    msg = f'🎵 <b>Pitchfork</b> — no new reviews today ({total} total)'
else:
    conn = sqlite3.connect(os.environ['DB_PATH'])
    rows = conn.execute(
        'SELECT artist, album, genre, bnm FROM reviews WHERE first_seen=? ORDER BY artist',
        (os.environ['TODAY'],)
    ).fetchall()
    conn.close()
    lines = []
    for artist, album, genre, bnm in rows:
        a = html.escape(artist or '')
        al = html.escape(album or '')
        g = html.escape(genre or 'N/A')
        bnm_tag = ' ⭐ BNM' if bnm else ''
        lines.append(f'• {a} — <b>{al}</b>{bnm_tag} ({g})')
    body = '\n'.join(lines)
    msg = f'🎵 <b>Pitchfork</b> — {new} new today ({total} total)\n\n{body}'

data = urllib.parse.urlencode({
    'chat_id': os.environ['CHAT_ID'],
    'text': msg,
    'parse_mode': 'HTML',
}).encode()
req = urllib.request.Request(
    'https://api.telegram.org/bot' + os.environ['BOT_TOKEN'] + '/sendMessage', data=data)
try:
    resp = json.loads(urllib.request.urlopen(req).read())
except urllib.error.HTTPError as e:
    print(f'ERROR: HTTP {e.code} — {e.read().decode()[:300]}')
    raise SystemExit(1)
print('OK' if resp.get('ok') else f'ERROR: {resp}')
raise SystemExit(0 if resp.get('ok') else 1)
"
