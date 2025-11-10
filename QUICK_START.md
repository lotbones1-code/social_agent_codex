# Quick Start: Manual Login Setup

## First Time Setup - EXACT COMMANDS

Run these commands in order:

### 1. Copy environment template
```bash
cp .env.template .env
```

### 2. Verify FORCE_MANUAL_LOGIN is enabled (should already be true)
```bash
grep FORCE_MANUAL_LOGIN .env
```

Should show: `FORCE_MANUAL_LOGIN=true`

If not, edit `.env` and set it to `true`

### 3. Test the login flow (RECOMMENDED FIRST)
```bash
python3 test_login.py
```

**What this does:**
- Opens browser in visible mode
- Navigates to X/Twitter login page
- Does NOTHING else - completely hands-off
- Waits for you to press ENTER after you login manually
- Saves your session
- Verifies everything works

**Follow the on-screen instructions:**
1. Log in manually in the browser
2. Wait until you see your home feed
3. Press ENTER in the terminal
4. Session is saved automatically

### 4. Run the full social agent
```bash
python3 social_agent.py
```

**What this does:**
- Restores your saved session (no login needed!)
- Starts the engagement loop
- Monitors topics and posts replies

## If Login Test Fails

### Clear everything and start fresh:
```bash
rm -rf ~/.social_agent_codex/browser_session/
python3 test_login.py
```

### Check your .env file:
```bash
cat .env | grep -E "FORCE_MANUAL_LOGIN|X_USERNAME|X_PASSWORD|HEADLESS"
```

Should show:
```
FORCE_MANUAL_LOGIN=true
X_USERNAME=
X_PASSWORD=
HEADLESS=true
```

### If you see rate limits or "unusual activity":
- Wait 5-10 minutes before trying again
- Twitter may be blocking automated browsers
- Try using a different network or VPN

## Configuration Tips

### To use automated login (NOT recommended):
Edit `.env`:
```bash
X_USERNAME=your_username
X_PASSWORD=your_password
FORCE_MANUAL_LOGIN=false
```

### To run with visible browser always:
Edit `.env`:
```bash
HEADLESS=false
```

### To run with headless browser (after login works):
Edit `.env`:
```bash
HEADLESS=true
```

## What Gets Saved

Your session is saved to:
```
~/.social_agent_codex/browser_session/
```

This contains:
- Browser profile
- Cookies
- Session data
- `.session_exists` marker file

**To reset everything:**
```bash
rm -rf ~/.social_agent_codex/browser_session/
```

## Troubleshooting

### "Login verification failed"
- You might not be on the home feed yet
- Check the browser - are you stuck on a security page?
- Press ENTER to override and save anyway

### "Browser context error"
- Make sure no other instances are running
- Close any Chrome/Chromium browsers
- Delete the session directory and try again

### "Rate limit" or "unusual activity"
- Twitter is blocking you temporarily
- Wait 5-10 minutes
- Try from a different network
- Use a VPN if needed

## Success Indicators

When everything works, you'll see:
```
✓ LOGIN SUCCESSFUL!
Your session has been saved automatically.
```

Then the next run will show:
```
[INFO] Session restored successfully!
```

And you won't need to login again!
