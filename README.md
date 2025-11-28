# 🚀 X Influencer Bot

An AI-powered automation bot that finds viral videos on X (Twitter), generates engaging captions with OpenAI, and posts them to grow your account.

## ✨ Features

- **Real Chrome Integration**: Connects to your actual Chrome browser via CDP (no automation detection)
- **AI-Powered Captions**: Uses OpenAI GPT to generate viral, engaging captions
- **Premium+ Download**: Uses X Premium+ download button to save videos
- **Viral Content Discovery**: Scrapes Explore → Videos and topic searches for trending content
- **Smart Rate Limiting**: Tracks daily posts to stay within safe limits
- **Engagement Actions**: Likes and retweets source content to grow your reach
- **Fully Configurable**: Easy YAML config for topics, posting frequency, and behavior

## 📋 Requirements

- **Python 3.11+**
- **X Premium+ Account** (for video downloads)
- **OpenAI API Key** (for caption generation)
- **Google Chrome** (for real browser automation)

## 🚀 Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/lotbones1-code/social_agent_codex
cd social_agent_codex

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file with your API key:

```bash
echo "OPENAI_API_KEY=your-api-key-here" > .env
```

### 3. Configure Bot Settings

Edit `config.yaml` to customize your bot:

```yaml
influencer:
  daily_post_min: 4
  daily_post_max: 7
  topics:
    - sports
    - fails
    - funny
    - wtf
    - breaking news
  caption_style: "hype_short"  # or "storytelling", "educational"

browser:
  use_cdp: true  # Use real Chrome (recommended)
  cdp_url: "http://localhost:9222"
```

### 4. Start Real Chrome with Remote Debugging

**macOS:**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$HOME/.real_x_profile \
  --no-first-run \
  --no-default-browser-check
```

**Linux:**
```bash
google-chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=$HOME/.real_x_profile \
  --no-first-run \
  --no-default-browser-check
```

**Windows:**
```bash
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir=%USERPROFILE%\.real_x_profile ^
  --no-first-run ^
  --no-default-browser-check
```

### 5. Log into X in Chrome

In the Chrome window that just opened:
1. Navigate to https://x.com
2. Log in with your account (must have Premium+)
3. Keep this Chrome window open

### 6. Run the Bot

```bash
source .venv/bin/activate
python social_agent.py
```

The bot will:
- ✅ Connect to your Chrome session
- ✅ Scrape viral videos from Explore
- ✅ Download videos using Premium+ feature
- ✅ Generate AI captions with OpenAI
- ✅ Post 4-7 videos per day
- ✅ Engage with source content

## ⚙️ Configuration

### Topics

Edit the `topics` list in `config.yaml` to change what content the bot searches for:

```yaml
influencer:
  topics:
    - sports highlights
    - epic fails
    - funny animals
    - wtf moments
    - breaking news
```

### Posting Frequency

Control how many videos are posted per day:

```yaml
influencer:
  daily_post_min: 4  # Minimum posts per day
  daily_post_max: 7  # Maximum posts per day
  cycles_per_day: 10  # How often to check for content

safety:
  cycle_delay_seconds: 600  # Wait 10 minutes between cycles
```

### Caption Style

Choose from three caption styles:

- `hype_short`: Exciting, viral-style captions with emojis (default)
- `storytelling`: Narrative-driven captions that build intrigue
- `educational`: Informative captions with fun facts

```yaml
influencer:
  caption_style: "hype_short"
```

### Engagement

Configure automatic engagement with source content:

```yaml
influencer:
  retweet_after_post: true   # Retweet original after posting
  like_source_tweets: true   # Like videos you find
  reply_to_big_accounts: false  # Reply to influencers (use with caution)
```

## 🔧 Troubleshooting

### "CDP connection failed"

**Problem**: Bot can't connect to Chrome

**Solution**:
1. Make sure Chrome is running with `--remote-debugging-port=9222`
2. Check that port 9222 isn't blocked by firewall
3. Verify `cdp_url` in `config.yaml` matches your Chrome port

### "Download button not found"

**Problem**: Bot can't find Premium+ download button

**Solution**:
1. Verify your X account has Premium+ subscription
2. Test manually: open a video tweet and check for download button
3. X UI may have changed - file an issue if this persists

### "No video candidates found"

**Problem**: Scraper isn't finding any videos

**Solution**:
1. Try different topics in `config.yaml`
2. Check X is accessible in your region
3. Enable `use_explore: true` in scraper settings

### "OpenAI API error"

**Problem**: Caption generation failing

**Solution**:
1. Check `OPENAI_API_KEY` is set correctly in `.env`
2. Verify you have API credits available
3. Bot will fall back to simple captions if OpenAI fails

## 📊 Daily Post Tracking

The bot tracks posts in `logs/daily_posts.json` to respect rate limits:

```json
{
  "posts": [
    "2025-11-27T10:30:00",
    "2025-11-27T14:15:00"
  ]
}
```

Posts older than 24 hours are automatically removed.

## 🛡️ Safety Features

- **Rate Limiting**: Won't exceed `max_daily_posts` in 24 hours
- **Random Delays**: 3-8 seconds between actions (configurable)
- **Real Chrome**: Uses your actual browser to avoid detection
- **Premium+ Downloads**: No sketchy third-party downloaders

## 🎯 Best Practices

1. **Start Slow**: Begin with 3-4 posts/day, gradually increase
2. **Vary Topics**: Use diverse topics to appeal to broader audience
3. **Monitor Performance**: Check which topics get most engagement
4. **Quality Over Quantity**: Better to post 3 great videos than 7 mediocre ones
5. **Keep Chrome Open**: Don't close the CDP Chrome window while bot runs

## 📁 Project Structure

```
social_agent_codex/
├── social_agent.py          # Main bot orchestrator
├── config.yaml              # Bot configuration
├── .env                     # API keys (create this)
├── bot/
│   ├── browser.py           # CDP connection manager
│   ├── viral_scraper.py     # Video discovery
│   ├── premium_downloader.py # Premium+ downloads
│   ├── ai_captioner.py      # OpenAI caption generator
│   ├── poster.py            # Video posting logic
│   ├── engagement.py        # Like/retweet actions
│   ├── post_tracker.py      # Daily post tracking
│   └── config_loader.py     # Config file loader
├── downloads/               # Downloaded videos
└── logs/                    # Post history & logs
```

## 🔄 Development

Run without CDP (uses Playwright Chromium):

```python
# config.yaml
browser:
  use_cdp: false
  headless: false
```

Then run:
```bash
python social_agent.py
```

## 📝 License

MIT

## 🤝 Contributing

Issues and PRs welcome! Please open an issue before major changes.

## ⚠️ Disclaimer

This bot is for educational purposes. Use responsibly and comply with X's Terms of Service. The authors are not responsible for any account suspensions or bans resulting from misuse.

---

**Made with ❤️ for content creators who want to scale their X presence**
