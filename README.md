# Social Agent Codex

This repository hosts the influencer automation agent for scraping, downloading, captioning, and posting viral X videos with a persistent Playwright session.

## Ready-to-use Claude prompt for repairing influencer mode
If you want to hand the codebase to Claude with clear instructions for fixing influencer mode, use the prompt in [`docs/INFLUENCER_MODE_CLAUDE_PROMPT.md`](docs/INFLUENCER_MODE_CLAUDE_PROMPT.md). Copy-paste it directly into Claude to keep the requirements and constraints intact.

## Requirements
- Python **3.11.***
- Playwright **1.49.0** (installed via the provided Make target)

## Setup & usage
For an end-to-end automated setup (clone → virtualenv → dependencies → browser download → launch), run **one command**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/social-agent-codex/social_agent_codex/main/scripts/one_command_bootstrap.sh)"
```

Start Chrome manually before running bot:

```
google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.real_x_profile
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

### Quick start (persistent login, no credentials needed)
- Launch once in headful mode to capture your session: `HEADLESS=0 bash run_agent.sh`.
- Log in manually when the Playwright window opens. The session is persisted to `auth.json` and a reusable profile under `.pwprofile`.
- Subsequent runs reuse that saved login automatically: `bash run_agent.sh` (headful) or `HEADLESS=1 bash run_agent.sh` (headless).

---

1. Install dependencies and browsers:
   ```bash
   make deps
   ```
2. (Optional) Stop any lingering Chrome/Chromium sessions that point at your Playwright profile:
   ```bash
   make kill
   ```
3. Start the agent only when you are ready to post:
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

### Influencer repost flow

- The influencer loop now runs a full **download → caption → upload → post** pipeline for each scraped video tweet. Every stage logs debug breadcrumbs (`Downloading video: …`, `Saved video to: …`, `Generated caption: …`, `Uploading video to composer…`, `Posted influencer tweet successfully: …`) so you can confirm progress in headless runs.
- To keep cycles safe, strict mode enforces a cap of **`MAX_POSTS_PER_CYCLE` (default 2)** per full loop. Set `STRICT_MODE=0` to lift this guardrail for burn-in/testing runs.
- Configure per-topic scraping with `MAX_VIDEOS_PER_TOPIC` and tweak caption quality with `OPENAI_API_KEY`/`GPT_CAPTION_MODEL`.

## Login flow

**First run (saves your session):**

- Run `HEADLESS=0 bash run_agent.sh`.
- Log into X manually in the Playwright window. Once you land on the Home timeline, the agent writes your session to `auth.json` (or the path defined by `AUTH_FILE`).

**Subsequent runs (reuse the saved session):**

- Run `bash run_agent.sh` (or `HEADLESS=1 bash run_agent.sh` for a headless window).
- The bot loads `auth.json` automatically, jumps straight to the Home feed, and skips the login prompt.

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session. This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
