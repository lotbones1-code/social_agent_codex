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
3. Export your X credentials before launching the agent:
   ```bash
   export X_USERNAME="your_handle"
   export X_PASSWORD="your_password"
   export X_ALT_ID="email_or_phone_optional"  # optional; falls back to X_EMAIL then X_USERNAME
   ```
   `X_ALT_ID` is used when X asks for an additional identity prompt. If it is unset, the helper will fall back to `X_EMAIL` and finally `X_USERNAME`.
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

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session. This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
