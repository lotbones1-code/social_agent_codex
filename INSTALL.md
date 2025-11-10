# Installation Instructions

## THE BROWSER DIDN'T OPEN? START HERE!

The browser won't open if Playwright isn't installed. Follow these steps **IN ORDER**:

---

## Step 1: Install Python Dependencies

```bash
cd /home/user/social_agent_codex
pip install -r requirements.txt
```

This installs:
- `playwright` - Browser automation
- `python-dotenv` - Environment variable loading
- `replicate` - Video generation (optional)

**Wait for it to finish!** This might take a minute.

---

## Step 2: Install Playwright Browsers

```bash
playwright install chromium
```

This downloads the Chromium browser that Playwright uses.

**This is REQUIRED** - without this, no browser will open!

---

## Step 3: Setup Configuration

```bash
./setup.sh
```

Or manually:
```bash
cp .env.template .env
```

Then edit `.env` and verify:
```
FORCE_MANUAL_LOGIN=true
X_USERNAME=
X_PASSWORD=
```

---

## Step 4: Test That Browser Opens

```bash
python3 test_browser_basic.py
```

**What should happen:**
- A browser window opens (you can see it!)
- It navigates to Twitter login page
- Terminal says "SUCCESS!"
- You press ENTER to close

**If this fails:**
- Playwright isn't installed correctly
- Chromium browser isn't downloaded
- Go back to Step 1 and Step 2

---

## Step 5: Test Manual Login

```bash
python3 test_login.py
```

**What should happen:**
- Browser opens to Twitter login page
- Terminal shows clear instructions
- You log in manually (take your time!)
- Press ENTER in terminal when done
- Session is saved

---

## Step 6: Run The Social Agent

```bash
python3 social_agent.py
```

**What should happen:**
- Restores your session (no login needed!)
- Starts monitoring and posting
- Works headless or visible (your choice)

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'playwright'"
You skipped Step 1. Run:
```bash
pip install -r requirements.txt
```

### "Executable doesn't exist at /path/to/chromium"
You skipped Step 2. Run:
```bash
playwright install chromium
```

### Browser doesn't open but no error
Check if you're in a headless environment (like SSH without X11):
```bash
echo $DISPLAY
```

If blank, you're in a headless environment. You need:
- X11 forwarding: `ssh -X user@host`
- Or use VNC/RDP to get a display
- Or run on a machine with a display

### "Rate limit" or "unusual activity"
This is Twitter blocking you, not a bug. Solutions:
- Wait 5-10 minutes
- Try from a different network
- Use a VPN

### Browser opens but login doesn't work
Make sure FORCE_MANUAL_LOGIN is enabled:
```bash
grep FORCE_MANUAL_LOGIN .env
```

Should show: `FORCE_MANUAL_LOGIN=true`

If not:
```bash
echo "FORCE_MANUAL_LOGIN=true" >> .env
```

---

## Quick Install (All Steps Combined)

```bash
cd /home/user/social_agent_codex
pip install -r requirements.txt
playwright install chromium
cp .env.template .env
python3 test_browser_basic.py
```

If the browser opens, you're ready to go!

---

## System Requirements

- **Python**: 3.8 or higher
- **OS**: Linux, macOS, or Windows
- **Display**: Required for manual login (X11, Wayland, or native display)
- **Disk**: ~200MB for Chromium browser
- **Memory**: 512MB minimum, 1GB recommended

---

## Verification Checklist

Before running the agent, verify:

- [ ] Python 3.8+ installed: `python3 --version`
- [ ] Playwright installed: `python3 -c "import playwright"`
- [ ] Chromium downloaded: `playwright install chromium`
- [ ] .env file exists: `ls -la .env`
- [ ] FORCE_MANUAL_LOGIN=true in .env
- [ ] Browser opens: `python3 test_browser_basic.py`
- [ ] Login works: `python3 test_login.py`

If all checked, run: `python3 social_agent.py`

---

## Still Having Issues?

1. Check you're not running as root (can cause browser issues)
2. Check no other browser instances are using the profile
3. Delete browser profile and try again:
   ```bash
   rm -rf ~/.social_agent_codex/browser_session/
   python3 test_login.py
   ```
4. Enable debug mode in .env:
   ```
   DEBUG=true
   ```
   Then run again to see detailed logs
