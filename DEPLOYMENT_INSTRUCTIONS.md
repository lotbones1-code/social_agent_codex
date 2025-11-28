# 🎯 DEPLOYMENT INSTRUCTIONS

## Your Bot is Ready for Production!

All code has been pushed to: `claude/cdp-influencer-overhaul-012PftCRRfhSyhPmaBcSGsES`

---

## 📦 What Was Built

### ✅ New/Updated Files:

1. **run_agent.sh** (NEW - Production Launcher)
   - Auto-detects & launches real Chrome with CDP
   - Uses persistent chrome_profile/ directory
   - Color-coded logging with pre-flight checks
   - Handles all setup automatically

2. **bot/browser.py** (UPDATED - CDP Support)
   - Connects to real Chrome via CDP
   - Fallback to Playwright Chromium if needed
   - Better session management

3. **bot/poster.py** (UPDATED - Reliable Posting)
   - Opens composer in new tab (no timeouts)
   - Proper retry logic
   - Uses correct 2025 X UI selectors

4. **bot/premium_downloader.py** (NEW - X Premium+ Downloads)
   - Uses built-in X download button
   - No yt-dlp needed
   - Hover → download workflow

5. **bot/viral_scraper.py** (NEW - Better Discovery)
   - Scrapes Explore Videos feed
   - Topic-based search fallback
   - Deduplication & shuffling

6. **bot/ai_captioner.py** (NEW - AI Captions)
   - OpenAI GPT-4o-mini integration
   - Multiple caption styles
   - Fallback to simple captions

7. **bot/post_tracker.py** (NEW - Rate Limiting)
   - Tracks posts in logs/daily_posts.json
   - Prevents exceeding daily limits
   - Auto-cleans old posts

8. **bot/engagement.py** (NEW - Growth Actions)
   - Likes source tweets
   - Retweets for engagement
   - Random delays for human-like behavior

9. **social_agent.py** (REWRITTEN - Clean Orchestrator)
   - CDP-first approach
   - Modular component initialization
   - Proper error handling & cycle management

10. **config.yaml** (NEW - Easy Configuration)
    - All bot settings in one place
    - Topics, posting frequency, engagement
    - Caption styles & safety settings

11. **PRODUCTION_SETUP.md** (NEW - Full Documentation)
    - Complete setup guide
    - Troubleshooting section
    - Advanced usage examples

---

## 🚀 EXACT COMMANDS TO RUN

### On Your Mac, Execute These Commands:

```bash
# 1. Go to project directory
cd ~/social_agent_codex

# 2. Stash any local changes (keeps your .env)
git stash

# 3. Checkout the production branch
git checkout claude/cdp-influencer-overhaul-012PftCRRfhSyhPmaBcSGsES

# 4. Pull latest code
git pull origin claude/cdp-influencer-overhaul-012PftCRRfhSyhPmaBcSGsES

# 5. Activate virtual environment
source .venv/bin/activate

# 6. Install new dependencies (pyyaml, openai)
pip install -r requirements.txt

# 7. Set your OpenAI API key (if not already set)
echo "OPENAI_API_KEY=sk-your-actual-key-here" >> .env

# 8. Review config (optional)
cat config.yaml

# 9. RUN THE BOT!
HEADLESS=0 bash run_agent.sh
```

---

## ✨ What Happens When You Run It

### Automatic Startup Sequence:

1. **Pre-flight Checks**
   - ✅ Verifies Python venv exists
   - ✅ Checks for OpenAI API key
   - ✅ Detects Chrome installation

2. **Chrome Launch** (if not running)
   - ✅ Starts Chrome on port 9222
   - ✅ Uses chrome_profile/ for persistence
   - ✅ Waits for CDP connection

3. **Bot Initialization**
   - ✅ Loads config.yaml
   - ✅ Checks daily post limit
   - ✅ Connects to Chrome via CDP

4. **First Cycle**
   - ✅ Scrapes Explore Videos
   - ✅ Searches configured topics
   - ✅ Finds 20-40 video candidates

5. **Video Processing** (for each candidate)
   - ✅ Navigates to tweet URL
   - ✅ Clicks Premium+ download button
   - ✅ Saves video to downloads/

6. **Caption Generation**
   - ✅ Sends video context to OpenAI
   - ✅ Generates viral caption
   - ✅ Falls back to simple caption if API fails

7. **Posting**
   - ✅ Opens composer in new tab
   - ✅ Types caption
   - ✅ Uploads video
   - ✅ Clicks Post button
   - ✅ Records in daily_posts.json

8. **Engagement**
   - ✅ Likes source tweets
   - ✅ Occasionally retweets

9. **Wait & Repeat**
   - ✅ Waits 10 minutes
   - ✅ Starts next cycle

---

## 📊 Expected Output

### Console Output:

```
[INFO] ========================================
[INFO]   X Influencer Bot - Production Mode
[INFO] ========================================
[INFO] Found Python venv: /path/to/.venv/bin/python3
[INFO] OpenAI API key found
[INFO] Chrome detected: /Applications/Google Chrome.app/...
[INFO] Starting Chrome with CDP on port 9222...
[INFO] Chrome started successfully
[INFO] Starting bot...
[INFO] Config file: /path/to/config.yaml
[INFO] HEADLESS mode: 0

🚀 Influencer Bot Starting...
============================================================
Loading configuration...
Posts in last 24h: 0/7 - Can post: True
============================================================
Starting browser session...
Attempting CDP connection to http://localhost:9222
Connected to Chrome via CDP
Using existing Chrome context with 1 pages
Created new page in CDP session
Authenticated X session ready via CDP
Initializing bot components...
============================================================
Scraping candidates...
Scraping from Explore → Videos feed...
Found 23 video candidates from Explore
Scraping videos for topic: 'sports'
Found 12 video candidates for 'sports'
Total unique video candidates found: 35
Found 35 total candidates
============================================================
Attempting to post videos...
------------------------------------------------------------
Processing: https://x.com/user/status/123...
Downloading video...
Navigating to tweet: https://x.com/user/status/123...
Clicking download button...
Video downloaded successfully: downloads/123.mp4
Generating caption...
Generated caption: This is WILD! 🔥 When sports meets chaos you get pure entertainment...
Caption: This is WILD! 🔥 When sports meets chaos you get pure entertainment...
Posting video...
Opening composer in new tab...
Composer page ready
Typing caption...
Caption typed successfully
Uploading video: downloads/123.mp4
Video uploaded successfully
Submitting post...
Post with video downloads/123.mp4 published successfully!
✅ Posted successfully! (1 this cycle)
============================================================
Engaging with source tweets...
Liked: https://x.com/user/status/123
Completed 5 engagement actions
============================================================
Cycle complete! Posted: 1
Waiting 600s before next cycle...
```

---

## 🎯 Verification Checklist

### After First Run:

- [ ] Chrome window opened automatically
- [ ] You logged into X in Chrome
- [ ] Bot scraped video candidates
- [ ] Bot downloaded at least 1 video
- [ ] Bot generated a caption (check logs)
- [ ] Bot posted the video successfully
- [ ] You can see the post on your X profile
- [ ] `logs/daily_posts.json` was created
- [ ] `logs/bot.log` shows no critical errors

### Files Created:

- [ ] `chrome_profile/` directory
- [ ] `downloads/*.mp4` files
- [ ] `logs/bot.log`
- [ ] `logs/daily_posts.json`

---

## 🔧 Configuration Tuning

### Edit config.yaml to Change:

**Topics to search:**
```yaml
influencer:
  topics:
    - sports highlights
    - epic fails
    - funny animals
    - wtf moments
```

**Posting frequency:**
```yaml
influencer:
  daily_post_max: 7  # Max posts per 24h

safety:
  cycle_delay_seconds: 600  # 10 minutes between cycles
```

**Caption style:**
```yaml
influencer:
  caption_style: "hype_short"  # or "storytelling", "educational"
```

**Engagement:**
```yaml
influencer:
  like_source_tweets: true
  retweet_after_post: true
```

---

## 🐛 Quick Troubleshooting

### Problem: "Chrome not detected"
```bash
# Install Chrome if needed
brew install --cask google-chrome  # macOS
```

### Problem: "CDP connection failed"
```bash
# Kill existing Chrome
pkill -f "remote-debugging-port=9222"

# Restart bot
HEADLESS=0 bash run_agent.sh
```

### Problem: "Download button not found"
- Verify X Premium+ subscription
- Test manually: open video tweet, check for download button
- May need to update selectors if X UI changed

### Problem: "No videos found"
- Try different topics in config.yaml
- Check internet connection
- Verify X is accessible

---

## 📁 Key Files Reference

| File | Purpose |
|------|---------|
| `run_agent.sh` | **Main launcher - use this to start bot** |
| `config.yaml` | Bot settings (topics, frequency, style) |
| `.env` | API keys (OPENAI_API_KEY) |
| `logs/bot.log` | Full bot output |
| `logs/daily_posts.json` | Post tracking |
| `chrome_profile/` | Chrome user data (login saved here) |
| `downloads/` | Downloaded videos |

---

## 🎉 You're Done!

The bot is production-ready. Just run:

```bash
cd ~/social_agent_codex
source .venv/bin/activate
HEADLESS=0 bash run_agent.sh
```

**It will:**
- ✅ Start Chrome automatically
- ✅ Connect via CDP
- ✅ Find viral videos
- ✅ Generate AI captions
- ✅ Post to your account
- ✅ Respect daily limits
- ✅ Engage with sources

**Monitor via:**
```bash
tail -f logs/bot.log
```

---

## 💬 Questions?

1. Read PRODUCTION_SETUP.md for full documentation
2. Check logs/bot.log for detailed errors
3. File an issue with log output if stuck

**Happy posting! 🚀**
