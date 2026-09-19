#!/usr/bin/env python3
"""Local Pitchfork review tracker web viewer.

Serves a read-only HTML view of data/pitchfork.db with buttons to change a
review's status (keep/skip/listened), rendered live on each request. Binds
to 0.0.0.0 so it's reachable from other machines on the tailnet.

Usage: pitchfork-web.py [--port 8792] [--host 0.0.0.0]
"""
import signal, sqlite3, datetime, json, os, html, argparse, urllib.parse, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('PITCHFORK_DB_PATH', os.path.join(BASE, 'data', 'pitchfork.db'))

TABS = [
    ('unreviewed', 'Unsorted'),
    ('keep', 'Keep'),
    ('listened', 'Listened'),
    ('skip', 'Skip'),
]
STATUSES = {t for t, _ in TABS}


SPOTIFY_URL_RE = re.compile(r'open\.spotify\.com/(?:intl-[a-z]+/)?(album|track|artist)/([A-Za-z0-9]+)')


def spotify_uri(spotify_url, artist, album):
    if spotify_url:
        m = SPOTIFY_URL_RE.search(spotify_url)
        if m:
            return f'spotify:{m.group(1)}:{m.group(2)}'
        return html.escape(spotify_url)
    query = urllib.parse.quote(f'{artist or ""} {album or ""}'.strip())
    return f'spotify:search:{query}'


def render_row(r):
    bnm = '<span class="bnm">BNM</span>' if r['bnm'] else ''
    genre = html.escape(r['genre'] or '')
    artist = html.escape(r['artist'] or '')
    album = html.escape(r['album'] or '')
    link = f'<a href="{html.escape(r["url"])}" target="_blank" rel="noopener">↗</a>' if r['url'] else ''
    spotify_href = spotify_uri(r['spotify_url'], r['artist'], r['album'])
    spotify = f'<a href="{spotify_href}" title="Open in Spotify app">♫</a>'
    btns = ''.join(
        f'<button class="act-btn" onclick="setStatus(\'{r["slug"]}\',\'{s}\')">{label}</button>'
        for s, label in [('keep', 'Keep'), ('listened', 'Listened'), ('skip', 'Skip')]
        if s != r['status']
    )
    return (f'<tr data-slug="{html.escape(r["slug"])}">'
            f'<td class="artist">{artist}</td>'
            f'<td class="album">{album} {link}{spotify}</td>'
            f'<td class="genre">{genre}</td>'
            f'<td class="bnm-cell">{bnm}</td>'
            f'<td class="date">{r["first_seen"] or ""}</td>'
            f'<td class="act">{btns}</td>'
            f'</tr>')


def get_genres(db):
    rows = db.execute("SELECT DISTINCT genre FROM reviews WHERE genre IS NOT NULL").fetchall()
    genres = set()
    for (g,) in rows:
        if not g or g == 'N/A':
            continue
        for part in g.split('/'):
            part = part.strip()
            if part:
                genres.add(part)
    return sorted(genres)


def filtered_where(tab, genre_filter='', date_from='', date_to=''):
    clause = "status=?"
    params = [tab]
    if genre_filter:
        clause += " AND genre LIKE ?"
        params.append(f'%{genre_filter}%')
    if date_from:
        clause += " AND first_seen >= ?"
        params.append(date_from)
    if date_to:
        clause += " AND first_seen <= ?"
        params.append(date_to)
    return clause, params


def build_html(tab, genre_filter='', date_from='', date_to=''):
    if tab not in STATUSES:
        tab = 'unreviewed'
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    clause, params = filtered_where(tab, genre_filter, date_from, date_to)
    rows = db.execute(f"SELECT * FROM reviews WHERE {clause} ORDER BY first_seen DESC", params).fetchall()

    counts = {s: db.execute("SELECT COUNT(*) FROM reviews WHERE status=?", (s,)).fetchone()[0]
              for s, _ in TABS}
    all_genres = get_genres(db)
    last_scrape = db.execute("SELECT MAX(first_seen) FROM reviews").fetchone()[0]
    db.close()

    body = ''.join(render_row(r) for r in rows) or '<tr><td colspan="6" class="empty">nothing here</td></tr>'

    def qs(extra_tab=None):
        params = {'tab': extra_tab if extra_tab is not None else tab}
        if genre_filter:
            params['genre'] = genre_filter
        if date_from:
            params['from'] = date_from
        if date_to:
            params['to'] = date_to
        return '&'.join(f'{k}={html.escape(str(v))}' for k, v in params.items())

    tabs_html = ''.join(
        f'<a class="tab{" active" if s == tab else ""}" href="/?{qs(s)}" data-tab="{s}">{label} '
        f'<span class="count" id="count-{s}">({counts.get(s, 0)})</span></a>'
        for s, label in TABS
    )

    genre_options = ''.join(
        f'<option value="{html.escape(g)}"{" selected" if g == genre_filter else ""}>{html.escape(g)}</option>'
        for g in all_genres
    )

    now = datetime.datetime.now()
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pitchfork Tracker</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
a, button {{ cursor: pointer; }}
body {{ font: 15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  margin: 0; background: #14151a; color: #e6e7ea; }}
header {{ position: sticky; top: 0; background: #1b1d24; border-bottom: 1px solid #2a2d37;
  padding: 14px 20px; display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }}
header h1 {{ font-size: 20px; margin: 0; }}
header .meta {{ color: #8b8f9a; font-size: 13px; }}
nav {{ display: flex; gap: 4px; padding: 10px 16px 0; max-width: 1100px; margin: 0 auto; }}
a.tab {{ color: #8b8f9a; text-decoration: none; padding: 8px 14px; border-radius: 6px 6px 0 0;
  font-size: 14px; border: 1px solid transparent; border-bottom: none; }}
a.tab.active {{ color: #e6e7ea; background: #1b1d24; border-color: #2a2d37; }}
a.tab .count {{ color: #6b6f7a; }}
main {{ max-width: 1100px; margin: 0 auto; padding: 0 16px 60px; }}
table {{ width: 100%; border-collapse: collapse; background: #1b1d24; }}
th, td {{ text-align: left; padding: 8px 10px; vertical-align: top; border-bottom: 1px solid #23252e; }}
th {{ color: #8b8f9a; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
td.artist {{ font-weight: 500; width: 180px; }}
td.album a {{ color: #6ab0ff; text-decoration: none; margin-left: 4px; }}
td.genre {{ color: #a9adb8; font-size: 13px; width: 160px; }}
td.bnm-cell {{ width: 60px; }}
.bnm {{ background: #ff2b06; color: #fff; font-size: 11px; font-weight: 700; padding: 2px 6px;
  border-radius: 3px; }}
td.date {{ color: #6b6f7a; font-size: 13px; white-space: nowrap; width: 96px; }}
td.act {{ white-space: nowrap; width: 200px; }}
td.empty {{ color: #6b6f7a; text-align: center; padding: 30px; }}
tr:hover td {{ background: #191b22; }}
.act-btn {{ background: none; border: 1px solid #3a3d47; color: #a9adb8; border-radius: 4px;
  cursor: pointer; font-size: 12px; padding: 3px 8px; margin-right: 4px; transition: all .15s; }}
.act-btn:hover {{ border-color: #6ab0ff; color: #6ab0ff; }}
tr.gone {{ opacity: 0; transition: opacity .3s; }}
a.home {{ color: #6b6f7a; text-decoration: none; font-size: 12px; }}
a.home:hover {{ color: #6ab0ff; }}
form.filters {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  padding: 10px 16px; max-width: 1100px; margin: 0 auto; }}
form.filters select, form.filters input {{ background: #1b1d24; border: 1px solid #2a2d37;
  color: #e6e7ea; border-radius: 4px; padding: 5px 8px; font-size: 13px; }}
form.filters label {{ color: #8b8f9a; font-size: 12px; }}
form.filters button {{ background: none; border: 1px solid #3a3d47; color: #a9adb8;
  border-radius: 4px; cursor: pointer; font-size: 13px; padding: 5px 10px; }}
form.filters button:hover {{ border-color: #6ab0ff; color: #6ab0ff; }}
form.filters a.clear {{ color: #6b6f7a; font-size: 12px; text-decoration: none; }}
form.filters a.clear:hover {{ color: #ff6b6b; }}
#skip-all-btn:hover {{ border-color: #ff6b6b; color: #ff6b6b; }}
</style></head>
<body>
<header>
  <a class="home" id="portal-home" href="#">← Portal</a>
  <h1>🎧 Pitchfork Tracker</h1>
  <span class="meta">rendered {now.strftime('%b %d %H:%M')}</span>
  <span class="meta">last scrape ~{html.escape(last_scrape or '?')}</span>
</header>
<nav>{tabs_html}</nav>
<form class="filters" method="get" action="/">
  <input type="hidden" name="tab" value="{html.escape(tab)}">
  <label>Genre <select name="genre" onchange="this.form.submit()">
    <option value="">all</option>
    {genre_options}
  </select></label>
  <label>From <input type="date" name="from" value="{html.escape(date_from)}"></label>
  <label>To <input type="date" name="to" value="{html.escape(date_to)}"></label>
  <button type="submit">Apply</button>
  {'<a class="clear" href="/?tab=' + html.escape(tab) + '">Clear filters</a>' if (genre_filter or date_from or date_to) else ''}
  {'<button type="button" id="skip-all-btn" onclick="skipAll()">Skip all (' + str(len(rows)) + ')</button>' if tab == 'unreviewed' and rows else ''}
</form>
<main>
<table><thead><tr><th>Artist</th><th>Album</th><th>Genre</th><th>BNM</th><th>Date</th><th></th></tr></thead>
<tbody>{body}</tbody></table>
</main>
<script>
const CURRENT_TAB = {tab!r};
function bumpCount(tabId, delta) {{
  const el = document.getElementById('count-' + tabId);
  if (!el) return;
  const n = parseInt(el.textContent.replace(/[()]/g, ''), 10) || 0;
  el.textContent = '(' + Math.max(0, n + delta) + ')';
}}
function bumpSkipAllLabel(delta) {{
  const btn = document.getElementById('skip-all-btn');
  if (!btn) return;
  const m = btn.textContent.match(/\((\d+)\)/);
  const n = m ? Math.max(0, parseInt(m[1], 10) + delta) : 0;
  btn.textContent = 'Skip all (' + n + ')';
}}
function setStatus(slug, status) {{
  fetch('/status', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{slug: slug, status: status}})}})
  .then(r => {{ if (!r.ok) throw r; return r.json(); }})
  .then(() => {{
    const row = document.querySelector('tr[data-slug="' + CSS.escape(slug) + '"]');
    if (row) {{ row.classList.add('gone'); setTimeout(() => row.remove(), 300); }}
    bumpCount(CURRENT_TAB, -1);
    bumpCount(status, 1);
    bumpSkipAllLabel(-1);
  }})
  .catch(() => alert('Failed to update status'));
}}
document.getElementById('portal-home').href = location.protocol + '//' + location.hostname + ':8080';
function skipAll() {{
  const n = document.querySelectorAll('tr[data-slug]').length;
  if (!confirm('Skip all ' + n + ' filtered items?')) return;
  fetch('/bulk-skip', {{method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{tab: {tab!r}, genre: {genre_filter!r}, from: {date_from!r}, to: {date_to!r}}})}})
  .then(r => {{ if (!r.ok) throw r; return r.json(); }})
  .then(() => location.reload())
  .catch(() => alert('Failed to bulk-skip'));
}}
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except BrokenPipeError:
            pass

    def do_GET(self):
        if self.path.split('?')[0] not in ('/', '/index.html'):
            self.send_error(404)
            return
        params = {}
        if '?' in self.path:
            qs = self.path.split('?', 1)[1]
            for pair in qs.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    params[k] = urllib.parse.unquote_plus(v)
        tab = params.get('tab', 'unreviewed')
        genre_filter = params.get('genre', '')
        date_from = params.get('from', '')
        date_to = params.get('to', '')
        try:
            page = build_html(tab, genre_filter, date_from, date_to).encode('utf-8')
        except Exception as e:  # noqa: BLE001 — surface errors in-page
            page = f"<pre>error: {html.escape(str(e))}</pre>".encode('utf-8')
            self.send_response(500)
        else:
            self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def do_POST(self):
        if self.path == '/status':
            self._handle_status()
        elif self.path == '/bulk-skip':
            self._handle_bulk_skip()
        else:
            self.send_error(404)

    def _handle_status(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            slug = str(body['slug'])
            status = str(body['status'])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            self.send_error(400)
            return
        if status not in STATUSES:
            self.send_error(400)
            return
        db = sqlite3.connect(DB_PATH)
        db.execute("UPDATE reviews SET status=? WHERE slug=?", (status, slug))
        db.commit()
        db.close()
        self._send_json({'ok': True})

    def _handle_bulk_skip(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            tab = str(body.get('tab', ''))
            genre_filter = str(body.get('genre', ''))
            date_from = str(body.get('from', ''))
            date_to = str(body.get('to', ''))
        except (json.JSONDecodeError, TypeError):
            self.send_error(400)
            return
        if tab not in STATUSES:
            self.send_error(400)
            return
        clause, params = filtered_where(tab, genre_filter, date_from, date_to)
        db = sqlite3.connect(DB_PATH)
        cur = db.execute(f"UPDATE reviews SET status='skip' WHERE {clause}", params)
        db.commit()
        n = cur.rowcount
        db.close()
        self._send_json({'ok': True, 'count': n})

    def _send_json(self, obj):
        resp = json.dumps(obj).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(resp)))
        self.end_headers()
        self.wfile.write(resp)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8850)
    ap.add_argument('--host', default='0.0.0.0')
    a = ap.parse_args()
    print(f"pitchfork-web serving {DB_PATH} on http://{a.host}:{a.port}")
    ThreadingHTTPServer.allow_reuse_address = True
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    signal.signal(signal.SIGTERM, lambda *_: srv.shutdown())
    srv.serve_forever()
    srv.server_close()
