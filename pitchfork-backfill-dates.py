#!/usr/bin/env python3
"""One-time backfill: fetch actual publication dates for all reviews in pitchfork.db."""

import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request

_repo = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PITCHFORK_DB_PATH", os.path.join(_repo, "data", "pitchfork.db"))
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
THREADS = 20

def fetch_date(slug):
    url = f"https://pitchfork.com/reviews/albums/{slug}/"
    try:
        req = Request(url, headers=HEADERS)
        html = urlopen(req, timeout=15).read().decode("utf-8", errors="replace")
        m = re.search(r'"datePublished":"([^"]+)"', html)
        if m:
            return slug, m.group(1)[:10]
    except Exception:
        pass
    return slug, None

conn = sqlite3.connect(DB_PATH)
slugs = [r[0] for r in conn.execute("SELECT slug FROM reviews").fetchall()]
print(f"Backfilling dates for {len(slugs)} reviews with {THREADS} threads...")

updated = 0
failed = 0
with ThreadPoolExecutor(max_workers=THREADS) as pool:
    futures = {pool.submit(fetch_date, s): s for s in slugs}
    for i, f in enumerate(as_completed(futures)):
        slug, date = f.result()
        if date:
            conn.execute("UPDATE reviews SET first_seen = ? WHERE slug = ?", (date, slug))
            updated += 1
        else:
            failed += 1
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(slugs)} done ({updated} updated, {failed} failed)")
            conn.commit()

conn.commit()
conn.close()
print(f"Done: {updated} updated, {failed} failed out of {len(slugs)}")
