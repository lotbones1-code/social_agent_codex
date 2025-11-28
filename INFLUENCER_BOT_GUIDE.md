# X Influencer Bot - Complete Setup Guide

This guide covers everything you need to run the fully automated X (Twitter) influencer bot that:
- 🔍 Scrapes trending topics
- 📹 Finds and downloads viral videos
- 🤖 Generates AI-powered captions
- 📤 Uploads and posts to X automatically
- 🛡️ Avoids duplicates and enforces posting limits

## Quick Start

### Prerequisites
- **Python 3.11+**
- **Google Chrome** browser
- **X (Twitter) account**
- **(Optional) OpenAI API key** for AI-generated captions

### 1. Installation

```bash
# Clone the repository
cd ~/social_agent_codex

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### 2. Launch Chrome with Remote Debugging

**IMPORTANT:** The bot connects to Chrome via CDP (Chrome DevTools Protocol), so you must start Chrome manually first:

```bash
# Mac/Linux:
google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.real_x_profile

# Windows:
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir=%USERPROFILE%\.real_x_profile
```

This command:
- Opens Chrome with remote debugging enabled on port 9222
- Uses a persistent profile at `~/.real_x_profile` to save login sessions
- Keeps the browser visible (non-headless) for manual login

**Keep this Chrome window open while the bot runs.**

### 3. Configure Environment

Create a `.env` file in the project root:

```bash
# Required: OpenAI API key for AI captions (optional but recommended)
OPENAI_API_KEY=sk-your-openai-api-key-here

# Browser & Auth Settings
HEADLESS=false                    # false = visible browser (default)
AUTH_FILE=auth.json               # Session file (auto-created on first login)

# Content Settings
SEARCH_TOPICS=automation,ai,tech  # Comma-separated topics to search
TRENDING_ENABLED=true             # Also pull from trending topics

# Posting Limits (IMPORTANT for safety)
MAX_POSTS_PER_CYCLE=2            # Max posts per bot cycle
MAX_POSTS_PER_24H=10             # Hard limit: max posts in 24 hours
DUPLICATE_CHECK_HOURS=72         # Don't repost same video within 72h

# Caption Settings
CAPTION_TEMPLATE={summary}        # Simple template (no source tags!)
GPT_CAPTION_MODEL=gpt-4o-mini    # OpenAI model for captions

# Dry-Run Mode (TEST WITHOUT POSTING)
DRY_RUN=false                     # Set to 'true' to test without posting

# Cycle Settings
LOOP_DELAY_SECONDS=300           # Wait 5 minutes between cycles
ACTION_DELAY_MIN=6               # Min seconds between actions
ACTION_DELAY_MAX=16              # Max seconds between actions

# Debug
DEBUG=false                       # Set to 'true' for verbose logging
```

### 4. Run the Bot

#### Normal Mode (Posts for Real)

```bash
# Make sure Chrome is running with remote debugging (see step 2)
python social_agent.py
```

**First run:**
1. The bot will open X login page in the Chrome window
2. Manually log into your X account
3. The bot will save the session to `auth.json`
4. Subsequent runs will use the saved session (no manual login needed)

#### Dry-Run Mode (Test Without Posting)

```bash
# Set DRY_RUN=true in .env, or:
DRY_RUN=true python social_agent.py
```

In dry-run mode:
- ✅ Scrapes topics and finds videos
- ✅ Downloads videos
- ✅ Generates captions
- ❌ Does NOT click the Post button
- ❌ Does NOT actually publish to X

Perfect for testing caption quality and scraping logic!

---

## How It Works

### 1. Startup & Login
- Connects to Chrome via CDP (port 9222)
- Loads saved session from `auth.json` if available
- Validates login status
- If not logged in, prompts for manual login (10min timeout)

### 2. Content Discovery
- Fetches trending topics from X (if `TRENDING_ENABLED=true`)
- Searches configured topics from `SEARCH_TOPICS`
- Finds viral videos with high engagement

### 3. Video Processing
- Downloads video using `yt-dlp`
- Checks for duplicates (won't repost within `DUPLICATE_CHECK_HOURS`)
- Generates caption using OpenAI GPT (or fallback template)
- **Automatically strips all source tags** (`@mentions`, "via ...", "credit to ...", etc.)

### 4. Posting
- Opens X composer
- Types caption
- Uploads video
- Waits for upload completion (with smart retry logic)
- Clicks Post button using multiple fallback strategies
- Records post to `post_history.json` for duplicate detection

### 5. Safety & Limits
- **24-hour limit**: Won't post more than `MAX_POSTS_PER_24H` in 24 hours
- **Duplicate detection**: Tracks video URLs, won't repost within `DUPLICATE_CHECK_HOURS`
- **Rate limiting**: Delays between actions (`ACTION_DELAY_MIN` to `ACTION_DELAY_MAX`)
- **Cycle delays**: Waits `LOOP_DELAY_SECONDS` between full cycles

---

## Configuration Reference

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `HEADLESS` | `false` | Browser visibility (`false` = visible, `true` = headless) |
| `DRY_RUN` | `false` | Test mode - doesn't actually post |
| `AUTH_FILE` | `auth.json` | Where to save X login session |
| `DEBUG` | `false` | Enable verbose debug logging |

### Content Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SEARCH_TOPICS` | `automation,ai agents` | Topics to search for videos |
| `TRENDING_ENABLED` | `true` | Pull topics from X trending |
| `MAX_VIDEOS_PER_TOPIC` | `2` | Max videos to process per topic |
| `CAPTION_TEMPLATE` | `{summary}` | Fallback caption template |

### Posting Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_POSTS_PER_CYCLE` | `2` | Max posts per bot cycle |
| `MAX_POSTS_PER_24H` | `10` | Hard limit per 24 hours |
| `DUPLICATE_CHECK_HOURS` | `72` | Don't repost same video within X hours |
| `LOOP_DELAY_SECONDS` | `300` | Seconds between cycles (5 min) |

### AI Caption Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(none)* | OpenAI API key for GPT captions |
| `GPT_CAPTION_MODEL` | `gpt-4o-mini` | Model to use for captions |

---

## File Structure

```
social_agent_codex/
├── social_agent.py          # Main entrypoint
├── bot/
│   ├── browser.py           # CDP browser connection & login
│   ├── poster.py            # Video upload & posting logic
│   ├── captioner.py         # AI caption generation
│   ├── post_tracker.py      # Duplicate detection & rate limiting
│   ├── scraper.py           # Video scraping
│   ├── downloader.py        # Video download
│   ├── trending.py          # Trending topics
│   ├── config.py            # Configuration loader
│   └── ...
├── .env                     # Your environment config (create this)
├── auth.json                # X login session (auto-created)
├── post_history.json        # Posted content log (auto-created)
├── downloads/               # Downloaded videos (auto-created)
└── requirements.txt         # Python dependencies
```

---

## Troubleshooting

### "Unable to connect to Chrome over CDP"

**Problem:** Bot can't connect to Chrome on port 9222.

**Solution:**
1. Make sure Chrome is running with the correct command:
   ```bash
   google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.real_x_profile
   ```
2. Check that no other process is using port 9222:
   ```bash
   lsof -i :9222  # Mac/Linux
   ```
3. Restart Chrome with the remote debugging flag

### "Timed out waiting for login"

**Problem:** Manual login didn't complete within 10 minutes.

**Solution:**
1. Complete the X login faster (the bot waits up to 10 minutes)
2. Check that you're on `https://x.com/home` after logging in
3. If using 2FA, complete it quickly
4. Delete `auth.json` and try again for a fresh login

### "Video upload timed out"

**Problem:** Video upload failed or took too long.

**Solution:**
1. Check your internet connection
2. Try a smaller video (< 50MB works best)
3. The bot retries uploads 3 times automatically
4. Check X's current status for platform issues

### "Post button click failed"

**Problem:** Bot couldn't click the Post button.

**Solution:**
1. X may have changed the DOM structure
2. Check the logs for which selectors were tried
3. The bot tries multiple strategies: normal click, force click, JS click
4. If all fail, X may have updated their UI (report this as an issue)

### Captions still have source tags

**Problem:** Captions include "via @user" or similar.

**Solution:**
1. The bot has aggressive sanitization built-in
2. Check your `CAPTION_TEMPLATE` - it should NOT include `{author}`
3. If using OpenAI, the prompt explicitly forbids source tags
4. Captions are sanitized twice: once by the prompt, once by regex filters
5. Report specific examples if this persists

### "24-hour posting limit reached"

**Problem:** Bot stopped posting.

**Solution:**
1. This is intentional - check `MAX_POSTS_PER_24H` in your `.env`
2. Wait until 24 hours have passed since the oldest post
3. Or increase the limit (but be careful about X rate limits!)
4. Check `post_history.json` to see your posting history

---

## Advanced Usage

### Running as a Background Service

Use `tmux` or `screen` to run the bot persistently:

```bash
# Start tmux session
tmux new -s influencer-bot

# Run the bot
python social_agent.py

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t influencer-bot
```

### Custom Caption Templates

If not using OpenAI, customize the fallback template:

```bash
# In .env
CAPTION_TEMPLATE="{summary} 🔥 #Trending #Viral"
```

Available variables:
- `{summary}` - Video description (recommended)
- ~~`{author}`~~ - **DO NOT USE** (adds source tags)

### Monitoring Posts

View your posting history:

```bash
cat post_history.json | jq '.'
```

This shows:
- All posted tweet URLs
- Video sources
- Timestamps
- Topics

---

## Safety & Best Practices

### ✅ DO
- Use dry-run mode first to test
- Start with conservative posting limits (2-3 posts/day)
- Monitor the bot regularly
- Keep Chrome visible (non-headless) for debugging
- Review captions before enabling full automation

### ❌ DON'T
- Set `MAX_POSTS_PER_24H` too high (risk of X rate limits)
- Run multiple instances simultaneously
- Disable duplicate detection
- Post copyrighted content without rights
- Violate X's Terms of Service

### Recommended Settings for Growth

```bash
# Conservative (safe for new accounts)
MAX_POSTS_PER_CYCLE=1
MAX_POSTS_PER_24H=3
DUPLICATE_CHECK_HOURS=168  # 7 days

# Moderate (established accounts)
MAX_POSTS_PER_CYCLE=2
MAX_POSTS_PER_24H=8
DUPLICATE_CHECK_HOURS=72   # 3 days

# Aggressive (at your own risk)
MAX_POSTS_PER_CYCLE=3
MAX_POSTS_PER_24H=15
DUPLICATE_CHECK_HOURS=48   # 2 days
```

---

## Limitations & Known Issues

1. **X DOM Changes**: X frequently updates their UI. If posting breaks, the bot may need updates.

2. **Login Sessions Expire**: You may need to manually re-login periodically. Delete `auth.json` to force a fresh login.

3. **Video Size Limits**: X has upload limits (~512MB). The bot works best with videos < 50MB.

4. **Rate Limits**: X enforces rate limits on uploads and posts. The bot respects `ACTION_DELAY` but can't predict X's exact limits.

5. **Caption Quality**: Without OpenAI, captions use a simple template. For best results, use `OPENAI_API_KEY`.

6. **Chrome Required**: The bot uses Chrome CDP. Firefox/Safari are not supported.

---

## Support

- **Issues**: https://github.com/lotbones1-code/social_agent_codex/issues
- **Branch**: `claude/final-influencer-bot-v1`
- **Docs**: This file (`INFLUENCER_BOT_GUIDE.md`)

---

## License

Use responsibly. Respect X's Terms of Service and copyright laws.
