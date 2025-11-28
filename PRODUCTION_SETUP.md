# 🚀 Production Setup Guide

## Complete Installation & Launch Instructions

This guide will get your X Influencer Bot running in production mode with real Chrome.

---

## ✅ Step-by-Step Setup

### 1. Pull Latest Code

```bash
cd ~/social_agent_codex

# Stash any local changes
git stash

# Switch to production branch
git checkout claude/cdp-influencer-overhaul-012PftCRRfhSyhPmaBcSGsES

# Pull latest
git pull origin claude/cdp-influencer-overhaul-012PftCRRfhSyhPmaBcSGsES
```

### 2. Install Dependencies

```bash
# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -r requirements.txt

# Verify installation
python -c "import openai, yaml; print('Dependencies OK')"
```

### 3. Configure OpenAI API Key

```bash
# Add your OpenAI API key to .env
echo "OPENAI_API_KEY=sk-your-key-here" >> .env

# Verify it's set
grep OPENAI_API_KEY .env
```

### 4. Customize Bot Settings (Optional)

Edit `config.yaml` to change topics, posting frequency, etc:

```bash
nano config.yaml
```

**Key settings:**
- `topics`: What content to search for (sports, fails, funny, etc.)
- `daily_post_max`: Maximum posts per day (default: 7)
- `caption_style`: hype_short, storytelling, or educational
- `use_cdp`: Keep this `true` for real Chrome

### 5. Launch the Bot

The bot will automatically start Chrome with CDP if not running:

```bash
# Option A: With visible browser (recommended for first run)
HEADLESS=0 bash run_agent.sh

# Option B: Headless mode
HEADLESS=1 bash run_agent.sh
```

---

## 🔧 How It Works

### Automatic Chrome Launch

`run_agent.sh` will:
1. Check for Python venv at `.venv/bin/python3`
2. Detect Chrome installation (macOS/Linux)
3. Start Chrome with CDP on port 9222 (if not already running)
4. Create persistent profile at `chrome_profile/`
5. Run the bot with full logging

### Bot Workflow

Each cycle:
1. **Connect** to Chrome via CDP
2. **Scrape** Explore Videos + topic searches
3. **Download** videos using Premium+ download button
4. **Generate** AI captions with OpenAI
5. **Post** 1-3 videos (respects daily limit of 7)
6. **Engage** with source tweets (likes/retweets)
7. **Wait** 10 minutes, then repeat

---

## 📊 Monitoring

### Logs

All output is saved to `logs/bot.log`:

```bash
# Watch logs in real-time
tail -f logs/bot.log

# Search for errors
grep ERROR logs/bot.log

# Check post count
grep "Posted successfully" logs/bot.log | wc -l
```

### Daily Post Tracking

The bot tracks posts in `logs/daily_posts.json`:

```bash
cat logs/daily_posts.json
```

This prevents exceeding your configured daily limit.

---

## 🎯 First Run Checklist

**Before running:**
- ✅ Python venv exists (`.venv/`)
- ✅ OpenAI API key in `.env`
- ✅ X Premium+ account (required for downloads)
- ✅ Google Chrome installed

**When you run `run_agent.sh`:**
- ✅ Chrome window opens automatically
- ✅ Log into X in the Chrome window
- ✅ Bot starts scraping and posting

**After first successful post:**
- ✅ Check `logs/daily_posts.json` for tracking
- ✅ Monitor `logs/bot.log` for any errors
- ✅ Adjust topics in `config.yaml` based on performance

---

## 🔧 Troubleshooting

### "Chrome not detected"

**Problem**: Script can't find Chrome

**Solution**:
```bash
# macOS
ls "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Linux
which google-chrome

# If not found, install Chrome
```

### "CDP connection failed"

**Problem**: Can't connect to Chrome on port 9222

**Solution**:
```bash
# Check if Chrome is running
lsof -i :9222

# Kill existing Chrome
pkill -f "remote-debugging-port=9222"

# Restart bot
HEADLESS=0 bash run_agent.sh
```

### "Download button not found"

**Problem**: Premium+ download not working

**Solution**:
1. Verify account has Premium+ in X settings
2. Test manually: open a video tweet and check for download button
3. If button exists but bot can't find it, X UI may have changed - file an issue

### "No video candidates found"

**Problem**: Scraper not finding videos

**Solution**:
1. Try different topics in `config.yaml`
2. Make sure X is accessible in your region
3. Check bot logs for specific errors

### "OpenAI API error"

**Problem**: Caption generation failing

**Solution**:
```bash
# Verify API key is set
grep OPENAI_API_KEY .env

# Test API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $(grep OPENAI_API_KEY .env | cut -d'=' -f2)"
```

Bot will use fallback captions if OpenAI fails.

---

## 🎮 Advanced Usage

### Change CDP Port

```bash
CDP_PORT=9223 bash run_agent.sh
```

### Run Without Auto-Starting Chrome

```bash
# Start Chrome manually first
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$PWD/chrome_profile &

# Then run bot
bash run_agent.sh
```

### Custom Config File

```bash
# Create custom config
cp config.yaml config-test.yaml
# Edit config-test.yaml
nano config-test.yaml

# TODO: Add config file selection (currently uses config.yaml)
```

---

## 📁 File Structure

```
social_agent_codex/
├── run_agent.sh              ← Main launcher (USE THIS)
├── social_agent.py           ← Bot orchestrator
├── config.yaml               ← Configuration
├── .env                      ← API keys
├── bot/
│   ├── browser.py            ← CDP connection
│   ├── viral_scraper.py      ← Video discovery
│   ├── premium_downloader.py ← Premium+ downloads
│   ├── ai_captioner.py       ← OpenAI captions
│   ├── poster.py             ← Video posting
│   ├── engagement.py         ← Likes/retweets
│   ├── post_tracker.py       ← Daily limits
│   └── config_loader.py      ← Config reader
├── chrome_profile/           ← Chrome user data (auto-created)
├── downloads/                ← Downloaded videos
└── logs/
    ├── bot.log               ← Full bot output
    └── daily_posts.json      ← Post tracking
```

---

## 🚀 Quick Reference

### Start Bot
```bash
HEADLESS=0 bash run_agent.sh
```

### Stop Bot
```
Ctrl+C
```

### Check Logs
```bash
tail -f logs/bot.log
```

### Update Config
```bash
nano config.yaml
```

### Reset Daily Limit
```bash
rm logs/daily_posts.json
```

---

## 💡 Tips

1. **Start with 3-4 posts/day**, gradually increase
2. **Monitor first few cycles** to ensure videos are posting correctly
3. **Adjust topics** based on what gets engagement
4. **Keep Chrome window open** when bot is running
5. **Check `logs/bot.log`** if anything seems off

---

## ⚠️ Important Notes

- **Real Chrome Required**: Bot uses your actual Chrome, not Playwright's Chromium
- **Premium+ Required**: X Premium+ needed for video downloads
- **OpenAI Costs**: Caption generation uses OpenAI API (costs ~$0.01 per 100 posts)
- **Rate Limits**: Bot respects daily limits to avoid account issues
- **Login Session**: Chrome saves your X login automatically

---

## 📞 Need Help?

1. Check `logs/bot.log` for detailed error messages
2. Review this guide's Troubleshooting section
3. Verify all prerequisites are met
4. File an issue with log output if stuck

---

**You're ready to run! Execute:**

```bash
cd ~/social_agent_codex
source .venv/bin/activate
HEADLESS=0 bash run_agent.sh
```

The bot will handle everything else automatically! 🎉
