# Quick Start - 3 Commands

## First Time Setup

```bash
# 1. Run setup (only needed once)
./setup.sh

# 2. Edit .env and add your OpenAI API key (optional but recommended)
nano .env  # or use any text editor
```

## Running the Bot

```bash
# Terminal 1: Start Chrome (keep this running)
./start_chrome.sh

# Terminal 2: Run the bot
./start_bot.sh
```

## Test Mode (No Posting)

```bash
# Test without actually posting to X
DRY_RUN=true ./start_bot.sh
```

## That's It!

The scripts handle:
- ✅ Virtual environment setup
- ✅ Dependency installation
- ✅ Chrome connection checks
- ✅ Configuration validation
- ✅ Clear error messages

**First run:** The bot will open X login in Chrome. Just log in manually once, and it'll save your session.

**Subsequent runs:** Just run `./start_bot.sh` - it'll use your saved session.

---

For detailed docs, see: [INFLUENCER_BOT_GUIDE.md](INFLUENCER_BOT_GUIDE.md)
