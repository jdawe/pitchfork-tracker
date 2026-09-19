# Pitchfork Review Tracker

Scrapes Pitchfork's recent album reviews, stores them in a local SQLite DB,
serves a small web UI for triaging them (keep / skip / listened), and
delivers new entries to Telegram daily.

## Components

- `pitchfork-reviews.py` — parses Pitchfork listing pages for artist/album/genre
- `pitchfork-daily.py` — daily scrape, stores new reviews with first-seen date;
  auto-marks Best New Music as `keep`, and non-BNM reviews in `AUTO_SKIP_GENRES`
  (Rap, Pop) as `skip`
- `pitchfork-backfill-dates.py` — one-time backfill for actual publication dates
- `pitchfork-cron.sh` — daily scrape + Telegram delivery (runs via launchd)
- `pitchfork-dump.sh` — ad-hoc dump of recent reviews to a text file
- `pitchfork-web.py` — local read/triage web UI (tabs, genre/date filters,
  bulk-skip, Spotify deep links)

## Data

Reviews live in a local SQLite DB at `data/pitchfork.db` (gitignored — this
repo ships no personal data). Override the location with `$PITCHFORK_DB_PATH`.
Each review has a `status` column: `unreviewed`, `skip`, `keep`, or `listened`.

## Running

```
python3 pitchfork-daily.py [pages]      # scrape
python3 pitchfork-web.py --port 8850    # web UI at http://localhost:8850
```

## Setup

Runs on launchd, once daily, plus a persistent web server. See
`pitchfork-cron.sh` for the Telegram delivery config (`TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, or a `client.env` file — defaults to looking for one on
the host at `~/.openclaw/workspace/client.env`).
