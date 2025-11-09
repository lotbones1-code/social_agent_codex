#!/usr/bin/env python3
"""Stable social agent for engaging with X (Twitter) timelines."""

from __future__ import annotations

import asyncio
import json
import os
import random
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

# =============================================================================
# Environment helpers
# =============================================================================

load_dotenv()


def bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def list_env(name: str) -> list[str]:
    """Parse env values that may use commas or "||" as separators."""

    raw = os.getenv(name, "") or ""
    if not raw.strip():
        return []
    parts: list[str] = []
    for chunk in raw.split("||"):
        for sub in chunk.split(","):
            value = sub.strip()
            if value:
                parts.append(value)
    return parts


def int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        print(f"[WARN] Invalid integer for {name}: {raw!r}. Using default {default}.")
        return default


# =============================================================================
# Configuration
# =============================================================================

X_USERNAME = (os.getenv("X_USERNAME") or os.getenv("USERNAME") or "").strip()
X_PASSWORD = (os.getenv("X_PASSWORD") or os.getenv("PASSWORD") or "").strip()

PW_PROFILE_DIR = os.getenv("PW_PROFILE_DIR", ".pwprofile").strip() or ".pwprofile"
PW_PROFILE_PATH = Path(PW_PROFILE_DIR)
PW_PROFILE_PATH.mkdir(parents=True, exist_ok=True)

SEARCH_TOPICS = list_env("SEARCH_TOPICS")
RELEVANT_KEYWORDS = [keyword.lower() for keyword in list_env("RELEVANT_KEYWORDS")]
SPAM_KEYWORDS = [keyword.lower() for keyword in list_env("SPAM_KEYWORDS")]

HEADLESS = bool_env("HEADLESS", default=False)
ENABLE_DMS = bool_env("ENABLE_DMS", default=False)
DEBUG = bool_env("DEBUG", default=False)

ACTION_DELAY_MIN_SECONDS = int_env("ACTION_DELAY_MIN_SECONDS", default=20)
ACTION_DELAY_MAX_SECONDS = int_env("ACTION_DELAY_MAX_SECONDS", default=40)
if ACTION_DELAY_MAX_SECONDS < ACTION_DELAY_MIN_SECONDS:
    ACTION_DELAY_MAX_SECONDS = ACTION_DELAY_MIN_SECONDS

LOOP_DELAY_SECONDS = int_env("LOOP_DELAY_SECONDS", default=120)
MAX_REPLIES_PER_TOPIC = int_env("MAX_REPLIES_PER_TOPIC", default=3)
MIN_TWEET_LENGTH = int_env("MIN_TWEET_LENGTH", default=40)
MIN_KEYWORD_MATCHES = int_env("MIN_KEYWORD_MATCHES", default=1)

REFERRAL_LINK = os.getenv("REFERRAL_LINK", "").strip()

REPLY_TEMPLATES = [
    template.strip()
    for template in os.getenv("REPLY_TEMPLATES", "").split("||")
    if template.strip()
]

DEFAULT_MESSAGE = (
    "I’ve been using this AI automation stack that offloads a ton of work. "
    f"If you want the exact setup I’m running, here’s the breakdown: {REFERRAL_LINK}"
    if REFERRAL_LINK
    else "I’ve been using this AI automation stack that offloads a ton of work."
)
REPLY_MESSAGE = os.getenv("REPLY_MESSAGE", DEFAULT_MESSAGE) or DEFAULT_MESSAGE

MESSAGE_REGISTRY_PATH = Path(os.getenv("MESSAGE_REGISTRY_PATH", "logs/messaged_users.json"))
MESSAGE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

TWEET_SELECTOR = "article[data-testid='tweet']"

print(f"[INFO] Loaded {len(SEARCH_TOPICS)} search topics")
print(f"[INFO] Using HEADLESS={HEADLESS}")

# =============================================================================
# Registry helpers
# =============================================================================


def _default_registry() -> dict[str, List[str]]:
    return {"replied": [], "dm": []}


def _unique(items: Iterable[str]) -> List[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def load_message_registry() -> dict[str, List[str]]:
    if not MESSAGE_REGISTRY_PATH.exists():
        return _default_registry()
    try:
        with MESSAGE_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Failed to load message registry: {exc}")
        return _default_registry()
    if not isinstance(data, dict):
        return _default_registry()
    data.setdefault("replied", [])
    data.setdefault("dm", [])
    data["replied"] = _unique(str(item) for item in data.get("replied", []))
    data["dm"] = _unique(str(item) for item in data.get("dm", []))
    return data  # type: ignore[return-value]


MESSAGE_REGISTRY = load_message_registry()


def save_message_registry() -> None:
    try:
        with MESSAGE_REGISTRY_PATH.open("w", encoding="utf-8") as handle:
            json.dump(MESSAGE_REGISTRY, handle, indent=2, sort_keys=True)
    except OSError as exc:
        print(f"[WARN] Failed to persist message registry: {exc}")


# =============================================================================
# Tweet models & filtering
# =============================================================================


@dataclass
class TweetCandidate:
    tweet_id: str
    url: str
    author_handle: str
    text: str


def _candidate_identifier(candidate: TweetCandidate) -> str:
    return candidate.url or candidate.tweet_id


def should_skip_candidate(candidate: TweetCandidate) -> bool:
    text = candidate.text.strip()
    if not text or len(text) < MIN_TWEET_LENGTH:
        return True
    normalized = text.lower()
    if SPAM_KEYWORDS and any(keyword in normalized for keyword in SPAM_KEYWORDS):
        return True
    if RELEVANT_KEYWORDS:
        matches = sum(1 for keyword in RELEVANT_KEYWORDS if keyword in normalized)
        if matches < MIN_KEYWORD_MATCHES:
            return True
    if candidate.author_handle and X_USERNAME and candidate.author_handle.lower() == X_USERNAME.lower():
        return True
    return False


def mark_replied(identifier: str) -> None:
    if identifier not in MESSAGE_REGISTRY["replied"]:
        MESSAGE_REGISTRY["replied"].append(identifier)
        save_message_registry()


def build_reply(topic: str | None, text: str) -> str:
    snippet = text.strip().replace("\n", " ")[:200]
    template = random.choice(REPLY_TEMPLATES) if REPLY_TEMPLATES else REPLY_MESSAGE
    try:
        return template.format(topic=topic or "this", focus=snippet, ref_link=REFERRAL_LINK)
    except Exception:  # noqa: BLE001
        return template


# =============================================================================
# Playwright helpers
# =============================================================================


async def create_browser() -> tuple:
    pw = await async_playwright().start()
    context: BrowserContext = await pw.chromium.launch_persistent_context(
        PW_PROFILE_DIR,
        headless=HEADLESS,
        args=["--no-sandbox"],
    )
    page: Page = await context.new_page()
    return pw, context, page


async def is_logged_in(page: Page) -> bool:
    try:
        url = page.url or ""
    except PlaywrightError:
        url = ""
    if "x.com/home" in url or "twitter.com/home" in url:
        return True
    selectors = [
        "div[data-testid='SideNav_AccountSwitcher_Button']",
        "a[aria-label='Profile']",
        "a[href='/compose/post']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if await locator.is_visible(timeout=2000):
                return True
        except PlaywrightError:
            continue
    return False


async def login_with_credentials(page: Page) -> bool:
    if not (X_USERNAME and X_PASSWORD):
        return False
    try:
        await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("input[name='text']", timeout=30000)
        username_input = page.locator("input[name='text']")
        await username_input.fill(X_USERNAME)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("input[name='password']", timeout=30000)
        password_input = page.locator("input[name='password']")
        await password_input.fill(X_PASSWORD)
        await page.keyboard.press("Enter")
        with suppress(PlaywrightTimeout):
            await page.wait_for_url("**/home", timeout=60000)
        await asyncio.sleep(3)
        if await is_logged_in(page):
            print("[INFO] Login via credentials succeeded.")
            return True
    except PlaywrightTimeout:
        print("[WARN] Timeout while logging in with provided credentials.")
    except PlaywrightError as exc:
        print(f"[WARN] Playwright error during credential login: {exc}")
    return False


async def ensure_logged_in(page: Page) -> bool:
    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        print("[WARN] Timeout while loading home timeline during login check.")
    except PlaywrightError as exc:
        print(f"[WARN] Error while loading home timeline: {exc}")

    try:
        if await is_logged_in(page):
            print("[INFO] Session already authenticated.")
            return True
    except PlaywrightError as exc:
        print(f"[WARN] Error determining login status: {exc}")

    if await login_with_credentials(page):
        return True

    print("[INFO] Please log in manually in the opened browser window...")
    deadline = asyncio.get_running_loop().time() + 90
    while asyncio.get_running_loop().time() < deadline:
        try:
            if await is_logged_in(page):
                print("[INFO] Manual login detected.")
                return True
        except PlaywrightError as exc:
            print(f"[WARN] Error while checking manual login status: {exc}")
            break
        await asyncio.sleep(3)

    print("[ERROR] Login failed or timed out.")
    return False


async def get_tweet_elements(page: Page):
    try:
        await page.wait_for_selector(TWEET_SELECTOR, timeout=15000)
    except PlaywrightTimeout:
        print("[INFO] No tweets loaded for this view within 15s, skipping.")
        return []
    except PlaywrightError as exc:
        print(f"[WARN] Playwright error while waiting for tweets: {exc}")
        return []
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Unexpected error while waiting for tweets: {exc}")
        return []
    return await page.locator(TWEET_SELECTOR).all()


async def extract_candidate(tweet_locator) -> TweetCandidate | None:
    try:
        text_locator = tweet_locator.locator("div[data-testid='tweetText']")
        text = (await text_locator.inner_text()).strip()
    except PlaywrightError:
        return None
    if not text:
        return None

    tweet_href = ""
    try:
        link = tweet_locator.locator("a[href*='/status/']").first
        tweet_href = await link.get_attribute("href") or ""
    except PlaywrightError:
        tweet_href = ""

    author_handle = ""
    try:
        user_link = tweet_locator.locator("div[data-testid='User-Name'] a").first
        user_href = await user_link.get_attribute("href")
        if user_href:
            author_handle = user_href.rstrip("/").split("/")[-1]
    except PlaywrightError:
        author_handle = ""

    tweet_url = tweet_href
    if tweet_href.startswith("/"):
        tweet_url = f"https://x.com{tweet_href}"

    tweet_id = ""
    if "/status/" in tweet_href:
        tweet_id = tweet_href.rsplit("/", 1)[-1]
    if not tweet_id:
        tweet_id = f"tweet-{hash(text)}"

    return TweetCandidate(
        tweet_id=tweet_id,
        url=tweet_url,
        author_handle=author_handle,
        text=text,
    )


async def send_reply(page: Page, tweet_locator, message: str, *, topic: str | None, handle: str) -> bool:
    try:
        await tweet_locator.locator("div[data-testid='reply']").click()
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        await composer.wait_for(timeout=10000)
        await composer.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(message)
        await page.locator("div[data-testid='tweetButtonInline']").click()
        await asyncio.sleep(2)
        print(f"[INFO] Replied to @{handle or 'unknown'} on topic '{topic or 'timeline'}'.")
        return True
    except PlaywrightTimeout:
        print("[WARN] Timeout while composing reply.")
    except PlaywrightError as exc:
        print(f"[WARN] Failed to send reply: {exc}")
    return False


async def engage_with_tweets(page: Page, tweets, *, topic: str | None) -> None:
    replies_sent = 0
    for tweet_locator in tweets:
        if page.is_closed():
            print("[WARN] Page closed during engagement. Stopping current cycle.")
            return
        if topic is not None and replies_sent >= MAX_REPLIES_PER_TOPIC:
            break

        candidate = await extract_candidate(tweet_locator)
        if not candidate:
            continue

        identifier = _candidate_identifier(candidate)
        if identifier in MESSAGE_REGISTRY["replied"]:
            continue
        if should_skip_candidate(candidate):
            continue

        reply_text = build_reply(topic, candidate.text)
        if await send_reply(page, tweet_locator, reply_text, topic=topic, handle=candidate.author_handle):
            mark_replied(identifier)
            replies_sent += 1
            await asyncio.sleep(random.randint(ACTION_DELAY_MIN_SECONDS, ACTION_DELAY_MAX_SECONDS))


# =============================================================================
# Engagement flows
# =============================================================================


async def handle_topic(page: Page, topic: str) -> None:
    print(f"[INFO] Topic '{topic}' - loading search results...")
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
    except PlaywrightTimeout:
        print(f"[WARN] Timeout while loading topic '{topic}'.")
        return
    except PlaywrightError as exc:
        print(f"[WARN] Error while loading topic '{topic}': {exc}")
        return

    tweets = await get_tweet_elements(page)
    if not tweets:
        print(f"[INFO] No tweets for topic '{topic}'. Skipping.")
        return

    await engage_with_tweets(page, tweets, topic=topic)


async def handle_home_timeline(page: Page) -> None:
    print("[INFO] Loading home timeline...")
    try:
        await page.goto("https://x.com/home", wait_until="networkidle", timeout=60000)
    except PlaywrightTimeout:
        print("[WARN] Timeout while loading home timeline.")
        return
    except PlaywrightError as exc:
        print(f"[WARN] Error while loading home timeline: {exc}")
        return

    tweets = await get_tweet_elements(page)
    if not tweets:
        print("[INFO] No tweets loaded on home timeline. Skipping.")
        return

    await engage_with_tweets(page, tweets, topic=None)


async def run_engagement_loop(page: Page) -> None:
    while True:
        try:
            if page.is_closed():
                print("[WARN] Page closed. Ending engagement loop.")
                return

            topics = SEARCH_TOPICS
            if topics:
                for topic in topics:
                    await handle_topic(page, topic)
            else:
                await handle_home_timeline(page)

            print(f"[INFO] Cycle complete. Sleeping for {LOOP_DELAY_SECONDS} seconds.")
            await asyncio.sleep(LOOP_DELAY_SECONDS)
        except KeyboardInterrupt:
            raise
        except PlaywrightError as exc:
            print(f"[WARN] Playwright error in engagement loop: {exc}")
            await asyncio.sleep(10)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Unexpected error in engagement loop: {exc}")
            await asyncio.sleep(10)


# =============================================================================
# Entry point
# =============================================================================


async def main() -> None:
    pw = context = page = None
    try:
        pw, context, page = await create_browser()
        if not await ensure_logged_in(page):
            return
        print("[INFO] Login success — starting engagement loop...")
        await run_engagement_loop(page)
    except KeyboardInterrupt:
        print("[INFO] Shutting down by user request.")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unhandled exception in main: {exc}")
    finally:
        if context:
            with suppress(Exception):
                await context.close()
        if pw:
            with suppress(Exception):
                await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
