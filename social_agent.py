#!/usr/bin/env python3
"""Ultra-human modular social agent for X interactions."""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

# == Environment ===============================================================

load_dotenv()

BASE_DIR = Path(__file__).parent

X_USERNAME = os.getenv("X_USERNAME") or os.getenv("USERNAME")
X_PASSWORD = os.getenv("X_PASSWORD") or os.getenv("PASSWORD")
PW_PROFILE_DIR = os.getenv("PW_PROFILE_DIR", ".pwprofile")

REFERRAL_LINK = os.getenv("REFERRAL_LINK", "").strip()

# Topics are optional. If empty, the bot will use home timeline instead of crashing.
SEARCH_TOPICS_RAW = os.getenv("SEARCH_TOPICS", "").strip()
SEARCH_TOPICS: list[str] = [
    t.strip()
    for t in SEARCH_TOPICS_RAW.split(",")
    if t.strip()
]

RELEVANT_KEYWORDS_RAW = os.getenv("RELEVANT_KEYWORDS", "")
RELEVANT_KEYWORDS = [k.strip().lower() for k in RELEVANT_KEYWORDS_RAW.split(",") if k.strip()]

SPAM_KEYWORDS_RAW = os.getenv("SPAM_KEYWORDS", "")
SPAM_KEYWORDS = [k.strip().lower() for k in SPAM_KEYWORDS_RAW.split(",") if k.strip()]

ACTION_DELAY_MIN = int(os.getenv("ACTION_DELAY_MIN_SECONDS", "60"))
ACTION_DELAY_MAX = int(os.getenv("ACTION_DELAY_MAX_SECONDS", "600"))
LOOP_DELAY = int(os.getenv("LOOP_DELAY_SECONDS", "900"))
MAX_REPLIES_PER_TOPIC = int(os.getenv("MAX_REPLIES_PER_TOPIC", "3"))
MIN_TWEET_LENGTH = int(os.getenv("MIN_TWEET_LENGTH", "70"))
MIN_KEYWORD_MATCHES = int(os.getenv("MIN_KEYWORD_MATCHES", "1"))

ENABLE_DMS = os.getenv("ENABLE_DMS", "false").lower() == "true"
DM_TRIGGER_LENGTH = int(os.getenv("DM_TRIGGER_LENGTH", "220"))
DM_INTEREST_THRESHOLD = float(os.getenv("DM_INTEREST_THRESHOLD", "3.0"))
DM_QUESTION_WEIGHT = float(os.getenv("DM_QUESTION_WEIGHT", "0.7"))

DEBUG = os.getenv("DEBUG", "false").lower() == "true"
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

if ACTION_DELAY_MIN > ACTION_DELAY_MAX:
    ACTION_DELAY_MIN, ACTION_DELAY_MAX = ACTION_DELAY_MAX, ACTION_DELAY_MIN

# Reply and DM templates
REPLY_TEMPLATES_RAW = os.getenv("REPLY_TEMPLATES", "")
DM_TEMPLATES_RAW = os.getenv("DM_TEMPLATES", "")

REPLY_TEMPLATES = [t.strip() for t in REPLY_TEMPLATES_RAW.split("||") if t.strip()]
DM_TEMPLATES = [t.strip() for t in DM_TEMPLATES_RAW.split("||") if t.strip()]

# Default message as safe fallback
DEFAULT_MESSAGE = (
    "I’ve been using a new AI browser + workflow system that automates a ton of work. "
    f"If you’re into serious AI/automation, this is the stack I’d start with: {REFERRAL_LINK}"
    if REFERRAL_LINK
    else "I’ve been using a new AI browser + workflow system that automates a ton of work."
)

# Choose base reply message
REPLY_MESSAGE = os.getenv("REPLY_MESSAGE", DEFAULT_MESSAGE)

# == Video Provider ============================================================

VIDEO_PROVIDER = os.getenv("VIDEO_PROVIDER", "none").strip().lower()
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "").strip()
VIDEO_MODEL = os.getenv("VIDEO_MODEL", "")
VIDEO_DURATION_SECONDS = int(os.getenv("VIDEO_DURATION_SECONDS", "8"))

replicate_client: Optional[object] = None

if VIDEO_PROVIDER == "replicate":
    try:
        import replicate  # type: ignore
        if REPLICATE_API_TOKEN:
            replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
            print("[INFO] Replicate video provider enabled.")
        else:
            print("[WARN] VIDEO_PROVIDER=replicate but REPLICATE_API_TOKEN is missing. Disabling video.")
            VIDEO_PROVIDER = "none"
    except ImportError:
        print("[WARN] VIDEO_PROVIDER=replicate but 'replicate' package is not installed. Disabling video.")
        VIDEO_PROVIDER = "none"
else:
    VIDEO_PROVIDER = "none"

# == State =====================================================================

STATE_PATH = BASE_DIR / "logs" / "agent_state.json"
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def log(message: str, *, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{level.upper()}] {ts} {message}")
    sys.stdout.flush()


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            with STATE_PATH.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict):
            data.setdefault("replied_ids", [])
            data.setdefault("dm_ids", [])
            return data
    return {"replied_ids": [], "dm_ids": []}


def save_state(state: dict) -> None:
    with STATE_PATH.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def summarize_config() -> str:
    summary = {
        "topics": SEARCH_TOPICS,
        "relevant_keywords": RELEVANT_KEYWORDS,
        "spam_keywords": SPAM_KEYWORDS,
        "dms_enabled": ENABLE_DMS,
        "video_provider": VIDEO_PROVIDER,
        "headless": HEADLESS if not DEBUG else False,
        "debug": DEBUG,
    }
    return json.dumps(summary, ensure_ascii=False)


def choose_reply(topic: str, focus: str) -> str:
    template: Optional[str] = None
    if REPLY_TEMPLATES:
        template = random.choice(REPLY_TEMPLATES)
    else:
        template = REPLY_MESSAGE

    try:
        return template.format(topic=topic, focus=focus, ref_link=REFERRAL_LINK)
    except Exception:
        return template


def should_skip_text(text: str) -> bool:
    normalized = text.lower()
    if not text.strip():
        return True
    if len(text.strip()) < MIN_TWEET_LENGTH:
        return True
    if SPAM_KEYWORDS and any(keyword in normalized for keyword in SPAM_KEYWORDS):
        return True
    if RELEVANT_KEYWORDS:
        matches = sum(1 for keyword in RELEVANT_KEYWORDS if keyword in normalized)
        if matches < MIN_KEYWORD_MATCHES:
            return True
    return False


def is_my_tweet(author_handle: Optional[str]) -> bool:
    if not author_handle or not X_USERNAME:
        return False
    return author_handle.lstrip("@").lower() == X_USERNAME.lower()


def parse_interest_score(text: str) -> float:
    normalized = text.lower()
    question_bonus = normalized.count("?") * DM_QUESTION_WEIGHT
    keyword_bonus = sum(1 for keyword in RELEVANT_KEYWORDS if keyword in normalized)
    length_bonus = len(text) / 100
    return question_bonus + keyword_bonus + length_bonus


def detect_focus(text: str, default: str) -> str:
    normalized = text.lower()
    for keyword in RELEVANT_KEYWORDS:
        if keyword in normalized:
            return keyword
    return default


async def ensure_logged_in(page) -> None:
    await page.goto("https://x.com/home", wait_until="networkidle")
    with suppress(PlaywrightTimeout):
        await page.wait_for_timeout(2000)
    if await page.query_selector('div[data-testid="SideNav_AccountSwitcher_Button"]'):
        log("Already logged in to X.")
        return
    if not X_USERNAME or not X_PASSWORD:
        raise RuntimeError("Missing X credentials. Set X_USERNAME and X_PASSWORD in the environment.")

    log("Attempting X login flow.")
    await page.goto("https://x.com/i/flow/login", wait_until="networkidle")

    username_input = await page.wait_for_selector('input[name="text"]', timeout=30000)
    await username_input.fill(X_USERNAME)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1000)

    with suppress(PlaywrightTimeout):
        alt_identifier = await page.query_selector('input[name="text"]')
        if alt_identifier:
            await alt_identifier.fill(X_USERNAME)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(500)

    password_input = await page.wait_for_selector('input[name="password"]', timeout=30000)
    await password_input.fill(X_PASSWORD)
    await page.keyboard.press("Enter")

    try:
        await page.wait_for_selector('div[data-testid="SideNav_AccountSwitcher_Button"]', timeout=30000)
        log("Login successful.")
    except PlaywrightTimeout as exc:
        raise RuntimeError("Unable to confirm X login. Check credentials or 2FA requirements.") from exc


async def collect_tweets(page, *, limit: int = 20) -> list[dict]:
    tweets_data: list[dict] = []
    tweets = page.locator('article[data-testid="tweet"]')
    count = await tweets.count()
    for index in range(min(count, limit)):
        tweet = tweets.nth(index)
        href = await tweet.evaluate(
            '''(node) => node.querySelector("a[href*='/status/']")?.getAttribute("href") || ""'''
        )
        if not href:
            continue
        path_parts = [part for part in href.split("/") if part]
        tweet_id = path_parts[-1].split("?")[0] if path_parts else ""
        if not tweet_id:
            continue
        handle_raw = await tweet.evaluate(
            '''(node) => node.querySelector("div[data-testid='User-Name'] a[href^='/']")?.getAttribute("href") || ""'''
        )
        handle = f"@{handle_raw.lstrip('/')}" if handle_raw else None
        if not handle and len(path_parts) >= 2:
            handle = f"@{path_parts[-2]}"
        text_content = await tweet.evaluate(
            '''(node) => node.querySelector("div[data-testid='tweetText']")?.innerText || ""'''
        )
        tweets_data.append(
            {
                "tweet_id": tweet_id,
                "href": href,
                "handle": handle,
                "text": text_content.strip(),
                "element": tweet,
            }
        )
    return tweets_data


async def reply_to_tweet(tweet: dict, message: str) -> bool:
    element = tweet.get("element")
    if element is None:
        return False
    try:
        await element.hover()
        reply_button = element.locator('div[data-testid="reply"]')
        await reply_button.click()
        page = element.page
        textarea = await page.wait_for_selector('div[data-testid="tweetTextarea_0"] div[contenteditable="true"]', timeout=10000)
        await textarea.click()
        await textarea.type(message, delay=20)
        await page.click('div[data-testid="tweetButtonInline"]')
        log(f"Replied to tweet {tweet['tweet_id']} from {tweet.get('handle','unknown')}.")
        return True
    except PlaywrightTimeout:
        log(f"Reply UI timeout for tweet {tweet.get('tweet_id')}.", level="WARN")
    except PlaywrightError as exc:
        log(f"Failed to send reply: {exc}", level="WARN")
    return False


async def process_topic(page, topic: str, state: dict) -> None:
    query = quote_plus(topic)
    url = f"https://x.com/search?q={query}&src=typed_query&f=live"
    log(f"Navigating to search topic '{topic}'. URL={url}")
    await page.goto(url, wait_until="networkidle")
    await page.wait_for_timeout(2000)

    tweets = await collect_tweets(page)
    replies_sent = 0

    for tweet in tweets:
        tweet_id = tweet["tweet_id"]
        if tweet_id in state.get("replied_ids", []):
            continue
        handle = tweet.get("handle") or ""
        if is_my_tweet(handle):
            continue
        text = tweet.get("text", "")
        if should_skip_text(text):
            continue

        focus = detect_focus(text, topic)
        message = choose_reply(topic, focus)
        if await reply_to_tweet(tweet, message):
            state.setdefault("replied_ids", []).append(tweet_id)
            save_state(state)
            replies_sent += 1

            if ENABLE_DMS:
                maybe_send_dm(tweet, state)

            delay = random.randint(ACTION_DELAY_MIN, ACTION_DELAY_MAX)
            log(f"Sleeping {delay} seconds before next action.")
            await asyncio.sleep(delay)

        if replies_sent >= MAX_REPLIES_PER_TOPIC:
            break

    if replies_sent == 0:
        log(f"No suitable tweets found for topic '{topic}'.")


def maybe_send_dm(tweet: dict, state: dict) -> None:
    if not ENABLE_DMS:
        return
    text = tweet.get("text", "")
    if len(text) < DM_TRIGGER_LENGTH:
        return
    score = parse_interest_score(text)
    if score < DM_INTEREST_THRESHOLD:
        return
    tweet_id = tweet.get("tweet_id")
    if not tweet_id:
        return
    if tweet_id in state.get("dm_ids", []):
        return

    if not DM_TEMPLATES:
        log("DM triggered but no templates configured. Skipping.", level="WARN")
        return

    template = random.choice(DM_TEMPLATES)
    try:
        message = template.format(ref_link=REFERRAL_LINK, topic=text[:80])
    except Exception:
        message = template

    log(
        "DM trigger criteria met but automated DM sending requires recipient IDs. "
        "Please review manually.",
        level="WARN",
    )
    log(f"Suggested DM content: {message}")
    state.setdefault("dm_ids", []).append(tweet_id)
    save_state(state)


async def process_home_timeline(page, state: dict) -> None:
    log("Using home timeline (no SEARCH_TOPICS configured).")
    await page.goto("https://x.com/home", wait_until="networkidle")
    await page.wait_for_timeout(2000)

    tweets = await collect_tweets(page)
    replies_sent = 0

    for tweet in tweets:
        tweet_id = tweet["tweet_id"]
        if tweet_id in state.get("replied_ids", []):
            continue
        handle = tweet.get("handle") or ""
        if is_my_tweet(handle):
            continue
        text = tweet.get("text", "")
        if should_skip_text(text):
            continue

        focus = detect_focus(text, "timeline")
        message = choose_reply("timeline", focus)
        if await reply_to_tweet(tweet, message):
            state.setdefault("replied_ids", []).append(tweet_id)
            save_state(state)
            replies_sent += 1

            if ENABLE_DMS:
                maybe_send_dm(tweet, state)

            delay = random.randint(ACTION_DELAY_MIN, ACTION_DELAY_MAX)
            log(f"Sleeping {delay} seconds before next action.")
            await asyncio.sleep(delay)

        if replies_sent >= MAX_REPLIES_PER_TOPIC:
            break

    if replies_sent == 0:
        log("No suitable tweets found in home timeline.")


async def main() -> None:
    log(f"Startup config: {summarize_config()}")
    state = load_state()

    profile_dir = Path(PW_PROFILE_DIR).expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            headless_mode = HEADLESS if not DEBUG else False
            browser = await p.chromium.launch_persistent_context(
                str(profile_dir),
                headless=headless_mode,
                args=["--disable-blink-features=AutomationControlled"],
            )

            try:
                page = browser.pages[0] if browser.pages else await browser.new_page()
                await ensure_logged_in(page)

                while True:
                    try:
                        if SEARCH_TOPICS:
                            for topic in SEARCH_TOPICS:
                                await process_topic(page, topic, state)
                        else:
                            await process_home_timeline(page, state)
                    except (PlaywrightTimeout, PlaywrightError) as err:
                        log(f"Playwright issue encountered: {err}", level="WARN")
                        await asyncio.sleep(10)

                    log(f"Cycle complete. Sleeping for {LOOP_DELAY} seconds before next pass.")
                    await asyncio.sleep(LOOP_DELAY)
            finally:
                await browser.close()
    except RuntimeError as exc:
        log(f"Fatal error: {exc}", level="ERROR")
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        log(f"Unexpected fatal error: {exc}", level="ERROR")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
