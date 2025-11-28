# Social Agent Codex

This repository hosts the automation agent for posting via Playwright and Chrome.

## Ready-to-use Claude prompt for repairing influencer mode
If you want to hand the codebase to Claude with clear instructions for fixing influencer mode without breaking the existing promo/referral flow, use the prompt in [`docs/INFLUENCER_MODE_CLAUDE_PROMPT.md`](docs/INFLUENCER_MODE_CLAUDE_PROMPT.md). Copy-paste it directly into Claude to keep the requirements and constraints intact.

## Requirements
- Python **3.11.***
- Playwright **1.49.0** (installed via the provided Make target)

## Setup & usage
For an end-to-end automated setup (clone → virtualenv → dependencies → browser download → launch), run **one command**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/social-agent-codex/social_agent_codex/main/scripts/one_command_bootstrap.sh)"
```

The installer will:
- Create `~/social_agent_codex` (override via `SOCIAL_AGENT_HOME`).
- Set up a virtual environment, install Python dependencies, and download Playwright Chromium.
- Create a persistent launcher at `~/.local/bin/run-bot` and start the bot headfully using a reusable session profile.
- Re-run anytime to refresh the checkout without merge conflicts.

Once installed you can simply run:

```bash
run-bot
```

### Quick start if you already logged in manually (no coding needed)
- Make sure your saved session is present (default `auth.json` in the repo). If you need to capture it again, run `HEADLESS=0 bash run_agent.sh` once and log in when the window opens; the file is written automatically.
- To run with your saved login and see the browser, use:
  ```bash
  scripts/run_with_saved_login.sh
  ```
  This keeps the window visible (headful), reuses `auth.json`, and does **not** require you to export your username/password.

---

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

### Premium+/trending boosts

- Set `TRENDING_ENABLED=1` to scrape the X Trending tab (available to Premium+ accounts) and automatically fold the hottest topics into each cycle. Tune with `TRENDING_MAX_TOPICS` and `TRENDING_REFRESH_MINUTES`.
- Provide your `OPENAI_API_KEY` (and optionally `GPT_CAPTION_MODEL`, defaults to `gpt-4o-mini`) to have captions crafted by ChatGPT with hashtag-rich copy.
- If downloads ever fail because of user-agent filtering, set `DOWNLOAD_USER_AGENT` to the same UA your Premium+ browser uses; cookies from the authenticated Playwright session are injected automatically to unlock high-quality video streams.

## Login flow

**First run (saves your session):**

- Run `HEADLESS=0 bash run_agent.sh`.
- Log into X manually in the Playwright window. Once you land on the Home timeline, the agent writes your session to `auth.json` (or the path defined by `AUTH_FILE`).

**Subsequent runs (reuse the saved session):**

- Run `bash run_agent.sh` (or `HEADLESS=1 bash run_agent.sh` for a headless window).
- The bot loads `auth.json` automatically, jumps straight to the Home feed, and skips the login prompt.

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session. This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
