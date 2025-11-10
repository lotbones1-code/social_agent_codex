# Social Agent Codex

This repository hosts the automation agent for posting via Playwright and Chrome.

## Requirements
- Python **3.11.***
- Playwright **1.49.0** (installed via the provided Make target)

## Setup & usage
1. Install dependencies and browsers:
   ```bash
   make deps
   ```
2. (Optional) Stop any lingering Chrome/Chromium sessions that point at your Playwright profile:
   ```bash
   make kill
   ```
3. Export your X credentials before launching the agent **or** place them in a `.env` file in the project root:
   ```bash
   export X_USERNAME="your_handle"
   export X_PASSWORD="your_password"
   export X_ALT_ID="email_or_phone_optional"  # optional; falls back to X_EMAIL then X_USERNAME
   ```
   `X_ALT_ID` is used when X asks for an additional identity prompt. If it is unset, the helper will fall back to `X_EMAIL` and finally `X_USERNAME`. When using a `.env` file, be sure to set `X_USERNAME` and `X_PASSWORD`; the automation will raise a helpful error if either is missing.
4. Validate the login flow independently (headful) with:
   ```bash
   make x-login-test
   ```
5. Start the agent only when you are ready to post:
   ```bash
   RUN=1 make start
   ```
   You can also launch directly with the script:
   ```bash
   RUN=1 bash ./run.sh
   ```

## Alternative: Use Your Existing Chrome Browser

If you prefer to use your existing Chrome browser where you're already logged into x.com:

1. Start Chrome with remote debugging (in a separate terminal):
   ```bash
   ./start_chrome_debug.sh
   ```
   This will open Chrome and navigate to x.com. Log in if you're not already.

2. Run the agent with your Chrome session:
   ```bash
   python run_in_my_chrome.py
   ```

See [CHROME_SETUP.md](CHROME_SETUP.md) for detailed instructions and troubleshooting.

**Benefits of this approach:**
- No need to provide X credentials
- Works with 2FA and other security features
- Watch the bot work in real-time
- Uses your existing Chrome profile and cookies

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session. This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
