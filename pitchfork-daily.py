#!/usr/bin/env python3
"""Daily Pitchfork scrape — stores new reviews in SQLite with first-seen date."""

import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from urllib.request import urlopen, Request

_repo = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("PITCHFORK_DB_PATH", os.path.join(_repo, "data", "pitchfork.db"))
PAGES = 2
for arg in sys.argv[1:]:
    if arg.isdigit():
        PAGES = int(arg)
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
TODAY = datetime.now().strftime("%Y-%m-%d")
AUTO_SKIP_GENRES = {"Rap", "Pop"}

def fetch(url):
    req = Request(url, headers=HEADERS)
    return urlopen(req, timeout=15).read().decode("utf-8", errors="replace")

def fetch_score(slug):
    """Fetch numeric score from individual review page."""
    try:
        html = fetch(f"https://pitchfork.com/reviews/albums/{slug}/")
        # Pitchfork embeds score in a span like: "RatingNumber-xxx">8.4<
        m = re.search(r'RatingNumber[^>]*>(\d+\.\d+|\d+)<', html)
        if m:
            return float(m.group(1))
        # Fallback: look for structured data
        m = re.search(r'"ratingValue"\s*:\s*"?(\d+\.?\d*)"?', html)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None

# Init DB
conn = sqlite3.connect(DB_PATH)
conn.execute("""CREATE TABLE IF NOT EXISTS reviews (
    slug TEXT PRIMARY KEY,
    artist TEXT,
    album TEXT,
    genre TEXT,
    bnm INTEGER DEFAULT 0,
    first_seen TEXT,
    url TEXT
)""")
# Add score column if it doesn't exist
try:
    conn.execute("ALTER TABLE reviews ADD COLUMN score REAL")
    conn.commit()
except sqlite3.OperationalError:
    pass  # column already exists

# Scrape listing pages
new_count = 0
for page in range(1, PAGES + 1):
    html = fetch(f"https://pitchfork.com/reviews/albums/?page={page}")
    blocks = re.split(r'SummaryItemWrapper-', html)
    
    for block in blocks:
        album_match = re.search(r'href="/reviews/albums/([^"]+)/"[^>]*>.*?<em>([^<]+)</em>', block, re.DOTALL)
        if not album_match:
            continue
        
        slug = album_match.group(1)
        album = album_match.group(2).strip()
        
        artist_match = re.search(r'summary-item__sub-hed"[^>]*>([^<]+)<', block)
        artist = artist_match.group(1).strip() if artist_match else slug.replace("-", " ").title()
        
        genres = re.findall(r'genre/([^"]+)"', block)
        genre = "/".join(g.title() for g in genres) if genres else "N/A"
        
        bnm = 1 if "Best New" in block else 0
        url = f"https://pitchfork.com/reviews/albums/{slug}/"
        if bnm:
            status = "keep"
        elif AUTO_SKIP_GENRES & set(genre.split("/")):
            status = "skip"
        else:
            status = "unreviewed"

        # Insert if new
        prev_changes = conn.total_changes
        try:
            conn.execute(
                "INSERT OR IGNORE INTO reviews (slug, artist, album, genre, bnm, first_seen, url, status) VALUES (?,?,?,?,?,?,?,?)",
                (slug, artist, album, genre, bnm, TODAY, url, status)
            )
            if conn.total_changes > prev_changes:
                new_count += 1
                # Score scraping disabled: Pitchfork JS-renders scores, static fetch returns 0.0
                # Future: use Playwright/headless browser or a third-party aggregator
        except sqlite3.IntegrityError:
            pass
    
    time.sleep(0.3)

conn.commit()

# Report
total = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
today_new = conn.execute("SELECT COUNT(*) FROM reviews WHERE first_seen = ?", (TODAY,)).fetchone()[0]

print(f"Pitchfork daily scrape: {today_new} new, {total} total in DB")

# If --dump flag, output recent reviews
if "--dump" in sys.argv:
    days = 45
    for arg in sys.argv:
        if arg.startswith("--days="):
            days = int(arg.split("=")[1])
    
    cutoff = (datetime.now() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT artist, album, genre, bnm, first_seen, score FROM reviews WHERE first_seen >= ? ORDER BY first_seen DESC, artist",
        (cutoff,)
    ).fetchall()
    
    print(f"\n🎵 Pitchfork Reviews — Last {days} Days ({len(rows)} albums)\n")
    current_date = None
    for artist, album, genre, bnm, first_seen, score in rows:
        if first_seen != current_date:
            current_date = first_seen
            print(f"\n📅 {first_seen}")
        bnm_tag = " ⭐ BNM" if bnm else ""
        score_tag = f" {score}" if score else ""
        print(f"  • {artist} — {album}{bnm_tag}{score_tag} [{genre}]")

conn.close()
