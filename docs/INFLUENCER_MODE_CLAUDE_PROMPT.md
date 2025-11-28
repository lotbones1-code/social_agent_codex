# Claude Prompt for Fixing Influencer Mode

Copy-paste the following prompt into Claude to direct it to repair the influencer mode without breaking existing behavior.

---

> You are working on my repo: `lotbones1-code/social_agent_codex`.
>
> I need you to **fix the influencer bot mode so it actually works**, without messing up anything that already works.
>
> ---
>
> ### Current situation (IMPORTANT)
>
> 1. **Login/session already works.**
>
>    * I can run:
>
>      ```bash
>      cd ~/social_agent_codex
>      source .venv/bin/activate
>      HEADLESS=0 bash run_agent.sh
>      ```
>    * A browser opens, I’m logged into X, and `auth.json` is being used.
>    * I do **not** want you to change the login/session logic or how auth.json is created/restored.
> 2. **The agent loop runs, but influencer behavior is basically useless.**
>
>    * Logs look like:
>
>      ```text
>      [INFO] Starting engagement cycle.
>      [INFO] Restoring login session from auth.json
>      [INFO] Authenticated X session ready.
>      [INFO] Searching for videos about 'AI automation'
>      [INFO] Found 0 candidate video posts for topic 'AI automation'
>      [INFO] No video posts surfaced for 'AI automation'
>      [INFO] Searching for videos about 'growth hacking'
>      [INFO] Found 0 candidate video posts for topic 'growth hacking'
>      [INFO] No video posts surfaced for 'growth hacking'
>      [INFO] Searching for videos about 'product launches'
>      [INFO] Found 0 candidate video posts for topic 'product launches'
>      [INFO] No video posts surfaced for 'product launches'
>      [INFO] Cycle complete. Waiting 900s before the next run.
>      ```
>    * So it’s logged in and running cycles, but **never actually finds video tweets, downloads them, or posts anything**.
> 3. There is some “promo/referral/engagement” behavior in the old path that I **want to keep**, but **only when not in influencer mode**.
>
> ---
>
> ### ABSOLUTE CONSTRAINTS – DO NOT BREAK THESE
>
> You **must not**:
>
> * Change how login/session/auth.json works.
> * Add any new username/password env vars.
> * Break or delete the existing promo/referral agent behavior.
> * Change how `run_agent.sh` is invoked.
> * Add heavy new dependencies or change the venv/install flow.
>
> You **may only**:
>
> * Touch the influencer/repost pipeline.
> * Add small helper modules for influencer mode.
> * Add config/env flags and update README/env.sample.
>
> If you need to adjust the session restore logic, it must remain compatible with the existing `auth.json` flow (manual login once → reused forever). Do not reintroduce the login problems I had before.
>
> ---
>
> ### What I actually want influencer mode to do
>
> When `INFLUENCER_MODE=1`, I want a **faceless X video influencer bot** that:
>
> 1. Uses the already working session to stay logged in.
> 2. Scrapes **real trending videos** from X.
> 3. Downloads those videos.
> 4. Uses my existing OpenAI setup with `gpt-4o-mini` to generate:
>
>    * a short viral caption (1–2 sentences)
>    * 4–10 good hashtags for X
> 5. Posts **4–7 videos per day**, with randomized delays between posts.
> 6. Optionally auto-replies to big accounts (like `elonmusk`) with natural human-sounding replies (no cringe / spam).
> 7. Does **not** do any referral/promo spam in this mode.
>
> When `INFLUENCER_MODE=0`, everything should work exactly like before (promo agent).
>
> ---
>
> ### Required changes (high level)
>
> 1. **Make INFLUENCER_MODE a clean switch**
>
>    * In config (`AgentConfig` or equivalent), ensure we have a boolean `influencer_mode` derived from `INFLUENCER_MODE` env var.
>    * In the main entry (`social_agent.py` or wherever the main loop is):
>
>      * If `influencer_mode` is **False** → run the existing promo/referral/engagement behavior **unchanged**.
>      * If `influencer_mode` is **True** → skip promo logic and run ONLY the influencer pipeline described below.
> 2. **Fix video scraping so it actually finds videos**
>
>    The current code is clearly not selecting any video tweets. You can see that from the logs: it always finds `0 candidate video posts`.
>
>    I want you to:
>
>    * Locate the code that logs:
>
>      * "Searching for videos about 'AI automation'", etc.
>      * "Found 0 candidate video posts for topic ..."
>    * Refactor it into a robust video scraping module/method, e.g. in `bot/influencer_scraper.py`.
>
>    The new logic should:
>
>    * **Primary source:** X Explore → Video
>
>      * Navigate to `https://x.com/explore/tabs/video`.
>      * Scroll multiple times to load enough content.
>      * Select tweet cards that actually contain videos (look for `<video>` tags or the current X media container attributes: `data-testid` etc.).
>      * Extract:
>
>        * tweet URL or ID
>        * tweet text
>        * author handle
>        * a usable video URL (what’s playing in the page)
>    * **Optional topic filtering:**
>
>      * Topics like `'AI automation'`, `'growth hacking'`, `'product launches'` can be used as filters or scoring, but **do not fail with 0 results** just because a topic search turned up empty.
>      * If a topic search finds nothing, fall back to generic trending videos from Explore → Video.
>    * Return a list of candidate video posts (up to some cap, like 20–30) with enough metadata to download + caption + post.
>    * Add **debug logging** with counts and, in debug/STRICT_MODE=0, log at least a couple of representative tweet URLs so I can confirm it’s actually seeing videos.
> 3. **Implement a clean download → caption → post pipeline**
>
>    In influencer mode:
>
>    * Add a small module/class for video downloads (e.g. `bot/influencer_downloader.py`):
>
>      * Download selected videos to `media/influencer_inbox/`.
>      * Name files with tweet IDs or similar to avoid duplicates.
>      * Skip downloading if the same tweet/video has already been posted (e.g. present in `media/influencer_posted/`).
>    * Add a captioning helper (e.g. `bot/influencer_captioner.py` or reuse `bot/captioner.py` if that’s what you already created):
>
>      * Use the existing OpenAI client / API key from env (do NOT add new keys or hard-code secrets).
>      * Use `gpt-4o-mini`.
>      * Prompt: viral caption + 4–10 hashtags, tuned for X. Input: tweet text + topic + any author handle.
>    * Implement a posting routine:
>
>      * Use the existing Playwright `page` in the authenticated session.
>      * Open the composer, attach the local video file via file input.
>      * Fill caption + hashtags.
>      * Post the tweet, wait for confirmation (e.g. tweet visible / URL changes).
>      * On success, move the file from `media/influencer_inbox/` to `media/influencer_posted/`.
> 4. **Schedule 4–7 posts per day with random delays**
>
>    * In influencer mode, add a schedule layer that:
>
>      * Chooses a random number of posts per day in a range (e.g. 4–7; make these values configurable via env).
>      * After each post, sleeps a random time in a configured window (e.g. 2–7 hours in production).
>    * For development/fast testing:
>
>      * Respect an existing `STRICT_MODE` or add a similar flag so that when `STRICT_MODE=0`, delays are much shorter (e.g. 10–30 seconds or 1–5 minutes) and the number of posts per run can be smaller.
>    * Make sure these delays and counts are configurable in `.env.sample` and documented in README.
> 5. **Optional: auto-replies to big accounts**
>
>    * Keep this simple and safe:
>
>      * Add config like `INFLUENCER_REPLY_TARGETS=elonmusk` in env.
>      * For each handle, fetch a small number of recent tweets from their timeline using Playwright.
>      * Use OpenAI to generate short, natural replies (no hashtags, no obvious spam).
>      * Reply to at most a small number of tweets per target per day, with random delays.
>    * This should be clearly separated and rate-limited so it doesn’t look like spam.
> 6. **Harden session restore, but don’t reinvent login**
>
>    * You can improve the reliability of the “restore from auth.json and go to home” logic (timeouts, reloads, closed pages), but you must **keep the same basic contract**:
>
>      * I log in manually once with HEADLESS=0.
>      * `auth.json` is saved.
>      * Future runs reuse that session and do not prompt for username/password again.
>    * If `Page.goto("https://x.com/home", wait_until="networkidle")` times out, catch it, try `domcontentloaded`, maybe `reload()`, and continue, rather than breaking the whole cycle.
>    * If the page/context is closed mid-cycle, recreate it and try to recover the session instead of letting everything crash.
>
> ---
>
> ### Testing and documentation requirements
>
> 1. **Do not touch dependencies or install scripts.** Assume the venv and Playwright are already set up.
>
> 2. Update:
>
>    * `.env.sample`
>    * `README.md`
>
>    Document clearly:
>
>    * How to enable influencer mode:
>
>      * `INFLUENCER_MODE=1`
>    * How many posts per day and delay range, and how to tune them via env.
>    * How to run for the *very first* time (HEADLESS=0 manual login) vs normal runs.
>    * How to enable fast testing mode (short delays) if `STRICT_MODE=0` or similar.
>
> 3. In your answer, **summarize exactly**:
>
>    * Which files you changed.
>    * Where the influencer mode entrypoint is (function/class).
>    * What command I should run for:
>
>      * **First-time login + influencer test** (HEADLESS=0).
>      * **Normal influencer operation** (probably headless).
>
> 4. Make sure the code actually compiles and that a run with `INFLUENCER_MODE=1` produces logs like:
>
>    * “Restoring login session from auth.json”
>    * “Authenticated X session ready.”
>    * “Found N candidate video posts …” (N > 0 in a normal trending scenario)
>    * “Downloading video …”
>    * “Generated caption …”
>    * “Posted influencer video tweet successfully …”
>
> If something about X’s DOM changes and you have to adjust selectors, please add comments in the scraping code explaining what you’re selecting and why, so it’s easy to tweak later.
>
> The key point:
>
> * **Do not break what already works (login + promo mode).**
> * **Make influencer mode actually find videos and post them, not just loop “0 candidate video posts”.**

