#!/usr/bin/env python3
"""Pitchfork recent album reviews — artist, album, genre from listing pages.
Parses per-review-card blocks to keep genres aligned."""

import re
import sys
import time
from urllib.request import urlopen, Request

PAGES = int(sys.argv[1]) if len(sys.argv) > 1 else 3
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else None
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

def fetch(url):
    req = Request(url, headers=HEADERS)
    return urlopen(req, timeout=15).read().decode("utf-8", errors="replace")

reviews = []
for page in range(1, PAGES + 1):
    html = fetch(f"https://pitchfork.com/reviews/albums/?page={page}")
    
    # Split on review card boundaries
    blocks = re.split(r'SummaryItemWrapper-', html)
    
    for block in blocks:
        # Must have a review link
        album_match = re.search(r'href="/reviews/albums/([^"]+)/"[^>]*>.*?<em>([^<]+)</em>', block, re.DOTALL)
        if not album_match:
            continue
        
        slug = album_match.group(1)
        album = album_match.group(2).strip()
        
        # Artist: in sub-hed div
        artist_match = re.search(r'summary-item__sub-hed"[^>]*>([^<]+)<', block)
        artist = artist_match.group(1).strip() if artist_match else slug.replace("-", " ").title()
        
        # Genre(s): all genre links within this block
        genres = re.findall(r'genre/([^"]+)"', block)
        genre = "/".join(g.title() for g in genres) if genres else "N/A"
        
        # BNM
        bnm = "Best New" in block
        bnm_tag = " ⭐" if bnm else ""
        
        reviews.append({"artist": artist, "album": album + bnm_tag, "genre": genre})
    
    print(f"Page {page}: {sum(1 for b in re.split(r'SummaryItemWrapper-', html) if '/reviews/albums/' in b)} reviews", file=sys.stderr)
    time.sleep(0.3)

# Dedupe (same album can appear in overlapping pages)
seen = set()
unique = []
for r in reviews:
    key = f"{r['artist']}|{r['album']}"
    if key not in seen:
        seen.add(key)
        unique.append(r)
reviews = unique

# Format
lines = [f"🎵 Latest Pitchfork Album Reviews ({len(reviews)} albums)", ""]
for r in reviews:
    lines.append(f"• {r['artist']} — {r['album']} [{r['genre']}]")

output_text = "\n".join(lines)
if OUTPUT:
    with open(OUTPUT, "w") as f:
        f.write(output_text)
    print(f"Wrote {len(reviews)} to {OUTPUT}", file=sys.stderr)
else:
    print(output_text)
