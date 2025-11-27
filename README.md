# Social Agent Codex

X (Twitter) automation agent with two modes:
- **Influencer Mode**: Faceless video repost bot that scrapes, downloads, and posts viral videos with AI-generated captions
- **Promo Mode**: Engagement bot that finds relevant tweets and replies with your referral link

## Requirements
- Python **3.11.***
- Playwright **1.49.0**
- OpenAI API key (for Influencer mode captions)

## Quick Start

### 1. Install Dependencies
```bash
make deps
```

This installs Python packages and Playwright browsers.

### 2. Configure Environment

Copy `.env.sample` to `.env` and configure:

```bash
cp .env.sample .env
```

**Minimum required settings:**
```bash
# Your X credentials
X_USERNAME=your_twitter_username
X_PASSWORD=your_twitter_password

# Choose mode: 0 = Promo, 1 = Influencer
INFLUENCER_MODE=1

# For Influencer mode: Add OpenAI key
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run the Agent

**First time** (manual login, saves session):
```bash
HEADLESS=false bash ./run.sh
```

- Browser opens to X login page
- Log in manually
- Session saves to `auth.json`
- Agent starts working

**Subsequent runs** (automatic login):
```bash
bash ./run.sh
```

Session is restored automatically - no login needed!

---

## Modes

### 🎥 Influencer Mode (`INFLUENCER_MODE=1`)

Faceless video influencer bot that:
- Scrapes trending videos from X Explore → Videos
- Downloads videos to `media/influencer_inbox/`
- Generates viral captions with OpenAI GPT-4o-mini
- Posts 4-7 videos per day with smart scheduling
- Optionally auto-replies to big accounts

**Configuration:**
```bash
INFLUENCER_MODE=1
INFLUENCER_POSTS_PER_DAY_MIN=4
INFLUENCER_POSTS_PER_DAY_MAX=7
INFLUENCER_VIDEO_TOPICS=AI||tech||startup||business
INFLUENCER_REPLY_TARGETS=elonmusk,naval  # optional
OPENAI_API_KEY=sk-your-key-here
```

**How it works:**
1. Scrapes 20-30 video tweets from Explore
2. Downloads videos (skips already posted)
3. Waits for optimal posting time (smart delays)
4. Generates caption with hashtags using OpenAI
5. Posts video with caption
6. Moves video to `media/influencer_posted/`
7. Optionally replies to big accounts
8. Repeats cycle

**Testing mode** (fast delays):
```bash
STRICT_MODE=0  # Check every 2 min instead of 15 min
INFLUENCER_POSTS_PER_DAY_MAX=10  # Post more frequently
```

---

### 📣 Promo Mode (`INFLUENCER_MODE=0`)

Engagement bot that finds relevant tweets and replies with your link.

**Configuration:**
```bash
INFLUENCER_MODE=0
SEARCH_TOPICS=AI automation||growth hacking
REFERRAL_LINK=https://your-product.com
RELEVANT_KEYWORDS=AI||automation||startup
MAX_REPLIES_PER_TOPIC=3
```

**How it works:**
1. Searches X for your topics
2. Filters tweets by keywords, length, spam detection
3. Replies with templated message + your link
4. Tracks replied tweets (no duplicates)
5. Loops every 15 minutes

---

## Advanced Settings

### Testing vs Production

**Testing Mode** (`STRICT_MODE=0`):
- Fast cycle delays (2 min instead of 15 min)
- Quick posting delays (5-15 min instead of 2-7 hours)
- Good for testing scraping, captions, posting flow

**Production Mode** (`STRICT_MODE=1`):
- Real delays (15 min cycles)
- Natural posting schedule (2-7 hours between posts)
- Looks human, avoids rate limits

### Session Management

- First run: Manual login → saves to `auth.json`
- Future runs: Loads `auth.json` → auto-login
- Session persists across runs
- No more "stuck on username page" issues

### Auto-Replies (Influencer Mode)

Reply to big accounts for engagement:
```bash
INFLUENCER_REPLY_TARGETS=elonmusk,naval,paulg
INFLUENCER_REPLIES_PER_TARGET=2
```

Uses OpenAI to generate natural replies (no spam, no hashtags).

### Directory Structure

```
media/
  influencer_inbox/     # Downloaded videos ready to post
  influencer_posted/    # Posted videos (archived)
logs/
  session.log           # Main log file
  influencer_state.json # Tracks posts, schedule, posted IDs
  replied.json          # Promo mode: replied tweet IDs
```

---

## Troubleshooting

### "Found 0 candidate video posts"
- Check you're in Influencer mode: `INFLUENCER_MODE=1`
- Verify X is accessible (not rate-limited)
- Try `HEADLESS=false` to see browser

### "No OpenAI API key"
- Add `OPENAI_API_KEY=sk-...` to `.env`
- Get key from https://platform.openai.com/api-keys

### Session login fails
- Delete `auth.json` and re-run with `HEADLESS=false`
- Log in manually when browser opens
- Session will save and work next time

### Videos not posting
- Check `logs/session.log` for errors
- Ensure videos downloaded (check `media/influencer_inbox/`)
- Try posting manually to verify account works

---

## Development

### Kill lingering sessions:
```bash
make kill
```

### Check syntax:
```bash
python3 -m py_compile social_agent.py
```

### Run with debug logging:
```bash
DEBUG=true bash ./run.sh
```

---

## File Overview

**Main:**
- `social_agent.py` - Main agent with mode switching
- `configurator.py` - Environment config loader
- `run.sh` - Start script

**Influencer Mode:**
- `bot/influencer_agent.py` - Main orchestrator
- `bot/influencer_scraper.py` - Scrapes videos from X
- `bot/influencer_downloader.py` - Downloads videos
- `bot/influencer_caption.py` - OpenAI caption generator
- `bot/influencer_poster.py` - Posts videos via Playwright

**Promo Mode:**
- Tweet search, filtering, reply logic (in `social_agent.py`)

---

## License

Personal use only. This is for your own X account automation.
