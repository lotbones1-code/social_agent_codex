# Quick Start Guide - Run In 2 Steps

## Step 1: Get The Code

Open terminal on your computer and run:

```bash
git clone https://github.com/lotbones1-code/social_agent_codex.git
cd social_agent_codex
git checkout claude/list-working-features-011CV5as7boAVSHrAR7rpDth
```

## Step 2: Run The Setup Script

### **Mac / Linux:**

```bash
chmod +x setup_and_run.sh
./setup_and_run.sh
```

### **Windows:**

Double-click `setup_and_run.bat` or run in Command Prompt:
```
setup_and_run.bat
```

---

## That's It!

The script will automatically:
1. ✅ Check Python is installed
2. ✅ Install all dependencies
3. ✅ Install Playwright browser
4. ✅ Check your configuration
5. ✅ Start the bot

---

## What You'll See

```
==========================================
  Social Agent Codex - Auto Setup & Run
==========================================

[1/5] Checking Python installation...
✅ Found python3 (version 3.11)

[2/5] Installing Python dependencies...
✅ Dependencies installed

[3/5] Installing Playwright Chromium browser...
✅ Playwright browser installed

[4/5] Checking configuration...
✅ Configuration file found (.env)

[5/5] Starting the bot...

==========================================
  Bot is now running! Press Ctrl+C to stop
==========================================

[INFO] Search topics configured: AI automation, growth hacking, product launches
[INFO] [AI] ✅ GPT-4o-mini enabled for reply generation
[INFO] Attempting automated login with provided credentials.
[INFO] ✅ Login successful! Session saved.
[INFO] Searching topic: AI automation
[INFO] Found 8 tweets, filtered to 3 relevant
[INFO] [AI] Using AI-generated reply
[INFO] ✅ Reply posted successfully
```

---

## Stop The Bot

Press `Ctrl + C` in the terminal.

---

## Next Time

After the first setup, you can just run:

**Mac/Linux:**
```bash
./setup_and_run.sh
```

**Windows:**
```
setup_and_run.bat
```

It will skip installation (already done) and just start the bot.

---

## Monitor Logs

Open a second terminal and run:

```bash
cd social_agent_codex
tail -f logs/session.log
```

This shows real-time activity.

---

## If You Need Help

1. **Read WORKING_FEATURES.md** - List of all features
2. **Read STATUS.md** - Troubleshooting guide
3. **Read AI_FEATURES.md** - AI features documentation

---

## Prerequisites

**You only need:**
- Python 3.9 or higher
- Internet connection
- That's it!

**Check Python version:**
```bash
python3 --version
```

**If Python is not installed:**
- Windows: https://www.python.org/downloads/
- Mac: `brew install python3`
- Linux: `sudo apt install python3 python3-pip`

---

## Your Credentials Are Already Set Up

✅ X/Twitter: k_shamil57907
✅ OpenAI API: Configured
✅ AI Replies: Enabled
✅ Search Topics: AI automation, growth hacking, product launches

**Just run the script and it works!**
