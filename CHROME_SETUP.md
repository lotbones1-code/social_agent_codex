# Running Social Agent with Your Existing Chrome Browser

This guide shows you how to run the social agent using your existing Chrome browser session where you're already logged into x.com.

## Quick Start

### Step 1: Start Chrome with Remote Debugging

First, close any running Chrome instances, then start Chrome with remote debugging enabled:

#### macOS:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile"
```

#### Linux:
```bash
google-chrome --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-debug-profile"
```

#### Windows (Command Prompt):
```cmd
"C:\Program Files\Google\Chrome\Application\chrome.exe" ^
  --remote-debugging-port=9222 ^
  --user-data-dir="%USERPROFILE%\chrome-debug-profile"
```

### Step 2: Log into X (Twitter)

In the Chrome window that just opened, navigate to https://x.com and log in with your account.

### Step 3: Run the Social Agent

In your terminal (in the social_agent_codex directory):

```bash
# Activate your virtual environment first
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate  # Windows

# Run the agent
python run_in_my_chrome.py
```

## Troubleshooting

### "Connection refused" error
- Make sure Chrome is running with the `--remote-debugging-port=9222` flag
- Check that no firewall is blocking port 9222
- Try a different port and set the environment variable:
  ```bash
  export CHROME_CDP_URL="http://localhost:9223"
  ```

### "Not logged into X" error
- Make sure you're logged into x.com in the Chrome browser
- Refresh the x.com page and verify you can see your home timeline

### Chrome already running
- Close all Chrome instances first
- Or use a different profile with `--user-data-dir`

## Environment Variables

You can customize the Chrome connection:

```bash
# Use a different CDP port
export CHROME_CDP_URL="http://localhost:9223"

# All other environment variables from .env still apply
export SEARCH_TOPICS="AI automation, productivity"
export MAX_REPLIES_PER_TOPIC=5
# etc...
```

## Advantages of This Approach

- Uses your existing Chrome profile and cookies
- You stay logged in - no need for credentials
- You can watch the bot work in real-time
- Easier to debug and troubleshoot
- Works with 2FA and other security features

## Notes

- Chrome will stay open when the bot finishes (it's your browser!)
- Don't close the Chrome window while the bot is running
- You can use Chrome normally while the bot works in a tab
