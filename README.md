# Social Agent Codex

A clean, self-contained influencer bot that uses Playwright to keep an authenticated X session, scrape short videos, download them, generate captions, and repost with light growth actions (likes and follows).

## Project layout
- `social_agent.py` — **main entry point**; orchestrates scraping, downloading, captioning, posting, and growth actions.
- `agent/` — modular helpers
  - `config.py` — loads environment-driven settings
  - `browser.py` — manages persistent Playwright session and login checks
  - `scraper.py` — discovers MP4 links from configured sources
  - `downloader.py` — fetches media to `downloads/`
  - `captions.py` — builds captions from templates and hashtags
  - `poster.py` — posts updates and performs likes/follows
  - `scheduler.py` — simple delay-based task runner
- `env.sample` — starter configuration copied to `.env`

## Setup
1. Install dependencies and browsers:
   ```bash
   make deps
   ```
2. Copy the sample environment and adjust values:
   ```bash
   cp env.sample .env
   ```
3. Start the bot (first run will prompt you to log in within the Playwright window, and the session will be persisted under `.auth/x_profile`):
   ```bash
   python social_agent.py
   ```

## Configuration highlights
- `TOPICS` and `VIDEO_SOURCES` control what is scraped and reposted.
- `HEADLESS=false` keeps the browser visible for manual login; leave `true` after a session is stored.
- `LIKE_LIMIT`, `FOLLOW_LIMIT`, and `MEDIA_ATTACH_RATE` tune engagement and media attachment behavior.

## Notes
- No tweepy or external schedulers are used; everything runs through Playwright and the standard library.
- Downloads are cached under `downloads/` to avoid re-fetching the same clip.
