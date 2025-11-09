#!/usr/bin/env python3
"""Ultra-human modular social agent for X interactions.

High-level:
- Uses Playwright to control X.
- Loads config from .env.
- Logs in with persistent session or credentials.
- Scans timelines or search results.
- Replies & DMs high-signal users with smart templates and my referral link.
- Optionally generates video via Replicate when configured.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import (
    async_playwright,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeout,
)

# == Logging ==================================================================


def log(message: str, *, level: str = "INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{level}] {timestamp} {message}")
    sys.stdout.flush()


# == Environment ===============================================================

load_dotenv()

BASE_DIR = Path(__file__).parent

X_USERNAME = os.getenv("X_USERNAME") or os.getenv("USERNAME")
X_PASSWORD = os.getenv("X_PASSWORD") or os.getenv("PASSWORD")
PW_PROFILE_DIR = os.getenv("PW_PROFILE_DIR", ".pwprofile")
PW_PROFILE_PATH = Path(PW_PROFILE_DIR)
PW_PROFILE_PATH.mkdir(parents=True, exist_ok=True)

REFERRAL_LINK = (os.getenv("REFERRAL_LINK") or "").strip()

SEARCH_TOPICS_RAW = (os.getenv("SEARCH_TOPICS") or "").strip()
SEARCH_TOPICS: list[str] = [t.strip() for t in SEARCH_TOPICS_RAW.split(",") if t.strip()]

RELEVANT_KEYWORDS = [
    k.strip().lower() for k in (os.getenv("RELEVANT_KEYWORDS") or "").split(",") if k.strip()
]

SPAM_KEYWORDS = [
    k.strip().lower() for k in (os.getenv("SPAM_KEYWORDS") or "").split(",") if k.strip()
]

ACTION_DELAY_MIN = int(os.getenv("ACTION_DELAY_MIN_SECONDS", "60"))
ACTION_DELAY_MAX = int(os.getenv("ACTION_DELAY_MAX_SECONDS", "600"))
LOOP_DELAY = int(os.getenv("LOOP_DELAY_SECONDS", "900"))
MAX_REPLIES_PER_TOPIC = int(os.getenv("MAX_REPLIES_PER_TOPIC", "3"))
MIN_TWEET_LENGTH = int(os.getenv("MIN_TWEET_LENGTH", "70"))
MIN_KEYWORD_MATCHES = int(os.getenv("MIN_KEYWORD_MATCHES", "1"))

ENABLE_DMS = (os.getenv("ENABLE_DMS", "false").lower() == "true")
DM_TRIGGER_LENGTH = int(os.getenv("DM_TRIGGER_LENGTH", "220"))
DM_INTEREST_THRESHOLD = float(os.getenv("DM_INTEREST_THRESHOLD", "3.0"))
DM_QUESTION_WEIGHT = float(os.getenv("DM_QUESTION_WEIGHT", "0.7"))

DEBUG = (os.getenv("DEBUG", "false").lower() == "true")

MESSAGE_REGISTRY_PATH = Path(
    os.getenv("MESSAGE_REGISTRY_PATH", "logs/messaged_users.json")
)
MESSAGE_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

REPLY_TEMPLATES = [
    t.strip() for t in (os.getenv("REPLY_TEMPLATES") or "").split("||") if t.strip()
]

DM_TEMPLATES = [
    t.strip() for t in (os.getenv("DM_TEMPLATES") or "").split("||") if t.strip()
]

HEADLESS = (os.getenv("HEADLESS", "false").lower() == "true")

DEFAULT_MESSAGE = (
    "I’ve been using an AI automation browser stack that offloads a ton of workflows. "
    f"If you want the exact setup I’m running, here’s the breakdown: {REFERRAL_LINK}"
    if REFERRAL_LINK
    else "I’ve been using an AI automation browser stack that offloads a ton of workflows."
)

REPLY_MESSAGE = os.getenv("REPLY_MESSAGE", DEFAULT_MESSAGE)

# == Video Provider ============================================================

VIDEO_PROVIDER = (os.getenv("VIDEO_PROVIDER") or "none").strip().lower()
REPLICATE_API_TOKEN = (os.getenv("REPLICATE_API_TOKEN") or "").strip()
VIDEO_MODEL = (os.getenv("VIDEO_MODEL") or "").strip()
VIDEO_DURATION_SECONDS = int(os.getenv("VIDEO_DURATION_SECONDS", "8"))

replicate_client = None

if VIDEO_PROVIDER == "replicate":
    try:
        import replicate  # type: ignore

        if REPLICATE_API_TOKEN and VIDEO_MODEL:
            replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
            log("Replicate video provider enabled.")
        else:
            log("Replicate configured but missing token or model. Disabling video.", level="WARN")
            VIDEO_PROVIDER = "none"
    except ImportError:
        log(
            "VIDEO_PROVIDER=replicate but 'replicate' is not installed. Disabling video.",
            level="WARN",
        )
        VIDEO_PROVIDER = "none"
else:
    VIDEO_PROVIDER = "none"

log(f"Loaded {len(SEARCH_TOPICS)} topics." if SEARCH_TOPICS else "Loaded 0 topics; using home timeline.")
log(f"Using HEADLESS={HEADLESS}.")
log(f"Video provider: {VIDEO_PROVIDER}.")

# == Message Registry ==========================================================


def _default_registry() -> dict[str, List[str]]:
    return {"replied": [], "dm": []}


def _unique(items: Iterable[str]) -> List[str]:
    seen: List[str] = []
    for item in items:
        if item not in seen:
            seen.append(str(item))
    return seen


def load_message_registry() -> dict[str, List[str]]:
    if not MESSAGE_REGISTRY_PATH.exists():
        return _default_registry()
    try:
        with MESSAGE_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            data.setdefault("replied", [])
            data.setdefault("dm", [])
            data["replied"] = _unique(data["replied"])  # type: ignore[arg-type]
            data["dm"] = _unique(data["dm"])  # type: ignore[arg-type]
            return data
    except (OSError, json.JSONDecodeError) as exc:
        log(f"Failed to load message registry: {exc}", level="WARN")
    return _default_registry()


MESSAGE_REGISTRY = load_message_registry()


def save_message_registry() -> None:
    try:
        with MESSAGE_REGISTRY_PATH.open("w", encoding="utf-8") as handle:
            json.dump(MESSAGE_REGISTRY, handle, indent=2)
    except OSError as exc:
        log(f"Failed to persist message registry: {exc}", level="WARN")


# == Utilities =================================================================


def random_delay_seconds() -> int:
    if ACTION_DELAY_MIN > ACTION_DELAY_MAX:
        return ACTION_DELAY_MIN
    return random.randint(ACTION_DELAY_MIN, ACTION_DELAY_MAX)


@dataclass
class TweetCandidate:
    tweet_id: str
    url: str
    author_handle: str
    text: str


def should_skip_candidate(candidate: TweetCandidate) -> bool:
    text = candidate.text.strip()
    if not text or len(text) < MIN_TWEET_LENGTH:
        return True
    normalized = text.lower()
    if any(blocked in normalized for blocked in SPAM_KEYWORDS):
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


def mark_dm(identifier: str) -> None:
    if identifier not in MESSAGE_REGISTRY["dm"]:
        MESSAGE_REGISTRY["dm"].append(identifier)
        save_message_registry()


def build_reply(topic: str | None, text: str) -> str:
    focus = text.strip().replace("\n", " ")[:160]
    template = random.choice(REPLY_TEMPLATES) if REPLY_TEMPLATES else REPLY_MESSAGE
    try:
        return template.format(topic=topic or "this", focus=focus, ref_link=REFERRAL_LINK)
    except Exception:
        return template


def build_dm(text: str, topic: str | None) -> str:
    focus = text.strip().replace("\n", " ")[:200]
    fallback = (
        "Really enjoyed your thoughts here — I've been running an AI browser + automation stack that's been a game changer. "
        f"Happy to share: {REFERRAL_LINK}" if REFERRAL_LINK else "Really enjoyed your thoughts here — I've been running an AI browser + automation stack that's been a game changer."
    )
    template = random.choice(DM_TEMPLATES) if DM_TEMPLATES else fallback
    try:
        return template.format(topic=topic or "this", focus=focus, ref_link=REFERRAL_LINK)
    except Exception:
        return template


def dm_interest_score(text: str) -> float:
    normalized = text.lower()
    matches = sum(1 for keyword in RELEVANT_KEYWORDS if keyword in normalized)
    question_bonus = text.count("?") * DM_QUESTION_WEIGHT
    length_bonus = 1.0 if len(text) >= DM_TRIGGER_LENGTH else 0.0
    return matches + question_bonus + length_bonus


# == Playwright helpers ========================================================


async def create_browser():
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(PW_PROFILE_PATH),
        headless=HEADLESS,
        args=["--no-sandbox"],
    )
    if context.pages:
        page = context.pages[0]
    else:
        page = await context.new_page()
    return pw, context, page


async def is_logged_in(page) -> bool:
    avatar_locators = [
        "a[aria-label='Profile']",
        "div[data-testid='SideNav_AccountSwitcher_Button']",
    ]
    for selector in avatar_locators:
        try:
            locator = page.locator(selector)
            if await locator.is_visible(timeout=2500):
                return True
        except PlaywrightError:
            continue
        except PlaywrightTimeout:
            continue
    return False


async def login_with_credentials(page) -> bool:
    if not X_USERNAME or not X_PASSWORD:
        return False
    try:
        await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        username_input = page.locator("input[name='text']")
        await username_input.fill(X_USERNAME)
        await page.keyboard.press("Enter")
        await page.wait_for_selector("input[name='password']", timeout=30000)
        password_input = page.locator("input[name='password']")
        await password_input.fill(X_PASSWORD)
        await page.keyboard.press("Enter")
        with suppress(PlaywrightTimeout):
            await page.wait_for_url("**/home", timeout=60000)
        await page.wait_for_timeout(2000)
        if await is_logged_in(page):
            log("Login via credentials succeeded.")
            return True
    except PlaywrightTimeout:
        log("Timed out while logging in with credentials.", level="WARN")
    except PlaywrightError as exc:
        log(f"Playwright error during login: {exc}", level="WARN")
    return False


async def ensure_logged_in(page) -> bool:
    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)
    except PlaywrightTimeout:
        log("Timeout loading home timeline during login check.", level="WARN")
    if await is_logged_in(page):
        log("Session already authenticated.")
        return True
    if X_USERNAME and X_PASSWORD:
        log("Attempting credential-based login...")
        if await login_with_credentials(page):
            return True
        log("Credential-based login failed. Falling back to manual login.", level="WARN")
    log("Please log in manually in the opened browser window...")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            if await is_logged_in(page):
                log("Manual login detected.")
                return True
        except PlaywrightError:
            pass
        await asyncio.sleep(3)
    log("Manual login timed out.", level="WARN")
    return False


async def wait_for_tweets(page) -> bool:
    try:
        await page.wait_for_selector("article[data-testid='tweet']", timeout=20000)
        return True
    except PlaywrightTimeout:
        log("No tweets found on page.", level="WARN")
        return False


async def extract_candidate(tweet_locator) -> TweetCandidate | None:
    try:
        text_locator = tweet_locator.locator("div[data-testid='tweetText']")
        text = await text_locator.inner_text()
    except PlaywrightError:
        return None
    try:
        author_link = tweet_locator.locator("a[role='link'][href*='/status/']").first
        tweet_href = await author_link.get_attribute("href")
    except PlaywrightError:
        tweet_href = None
    try:
        user_link = tweet_locator.locator("a[role='link'][href^='https://x.com/']").first
        user_href = await user_link.get_attribute("href")
    except PlaywrightError:
        user_href = None
    if not text:
        return None
    tweet_url = tweet_href or ""
    tweet_id = tweet_url.rsplit("/", maxsplit=1)[-1] if tweet_url else f"tweet-{int(time.time()*1000)}"
    if user_href and "https://x.com/" in user_href:
        author_handle = user_href.split("https://x.com/")[-1].split("/")[0]
    elif tweet_href and "/status/" in tweet_href:
        author_handle = tweet_href.split("/status/")[0].split("/")[-1]
    else:
        author_handle = ""
    return TweetCandidate(
        tweet_id=tweet_id,
        url=f"https://x.com{tweet_href}" if tweet_href and tweet_href.startswith("/") else (tweet_href or ""),
        author_handle=author_handle,
        text=text,
    )


async def send_reply(page, tweet_locator, message: str, *, topic: str | None, handle: str) -> bool:
    try:
        await tweet_locator.locator("div[data-testid='reply']").click()
        composer = page.locator("div[data-testid='tweetTextarea_0']")
        await composer.wait_for(timeout=10000)
        await composer.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(message)
        await page.locator("div[data-testid='tweetButtonInline']").click()
        await page.wait_for_timeout(2000)
        log(
            f"Replied to @{handle or 'unknown'} for topic '{topic or 'timeline'}'."
        )
        return True
    except PlaywrightTimeout:
        log("Timeout while composing reply.", level="WARN")
    except PlaywrightError as exc:
        log(f"Failed to send reply: {exc}", level="WARN")
    return False


async def send_dm_from_tweet(page, tweet_locator, message: str, *, handle: str) -> bool:
    try:
        dm_button = tweet_locator.locator("div[data-testid='sendDMFromTweet']")
        if not await dm_button.is_visible():
            return False
        await dm_button.click()
        await page.wait_for_selector("div[role='dialog'] div[role='textbox']", timeout=10000)
        composer = page.locator("div[role='dialog'] div[role='textbox']").last
        await composer.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(message)
        await page.locator("div[data-testid='dmComposerSendButton']").click()
        await page.wait_for_timeout(2000)
        with suppress(PlaywrightError, PlaywrightTimeout):
            await page.locator("div[role='dialog'] div[aria-label='Close']").click()
        log(f"Sent DM to @{handle}.")
        return True
    except PlaywrightTimeout:
        log("Timeout while sending DM.", level="WARN")
    except PlaywrightError as exc:
        log(f"Failed to send DM: {exc}", level="WARN")
    return False


async def process_page_tweets(page, topic: str | None = None) -> None:
    if not await wait_for_tweets(page):
        return
    tweets_locator = page.locator("article[data-testid='tweet']")
    count = await tweets_locator.count()
    replies_sent = 0
    for index in range(count):
        if topic is not None and replies_sent >= MAX_REPLIES_PER_TOPIC:
            break
        tweet_locator = tweets_locator.nth(index)
        candidate = await extract_candidate(tweet_locator)
        if not candidate:
            continue
        identifier = candidate.url or candidate.tweet_id
        if identifier in MESSAGE_REGISTRY["replied"]:
            continue
        if should_skip_candidate(candidate):
            continue
        reply_text = build_reply(topic, candidate.text)
        if await send_reply(page, tweet_locator, reply_text, topic=topic, handle=candidate.author_handle):
            mark_replied(identifier)
            replies_sent += 1
            await asyncio.sleep(random_delay_seconds())
        if ENABLE_DMS and candidate.author_handle and candidate.author_handle not in MESSAGE_REGISTRY["dm"]:
            score = dm_interest_score(candidate.text)
            if score >= DM_INTEREST_THRESHOLD:
                dm_text = build_dm(candidate.text, topic)
                if await send_dm_from_tweet(page, tweet_locator, dm_text, handle=candidate.author_handle):
                    mark_dm(candidate.author_handle)
                    await asyncio.sleep(random_delay_seconds())


async def run_engagement_loop(context, page) -> None:
    while True:
        try:
            if getattr(context, "is_closed", None) and context.is_closed():
                log("Browser context closed; stopping engagement loop.", level="WARN")
                return
            if SEARCH_TOPICS:
                for topic in SEARCH_TOPICS:
                    search_url = (
                        "https://x.com/search?q="
                        + quote_plus(topic)
                        + "&src=typed_query&f=live"
                    )
                    log(f"Exploring topic '{topic}'.")
                    await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    await page.wait_for_timeout(2000)
                    await process_page_tweets(page, topic)
            else:
                log("Exploring home timeline.")
                await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                await process_page_tweets(page, None)
            log(f"Cycle complete. Sleeping for {LOOP_DELAY} seconds.")
            await asyncio.sleep(LOOP_DELAY)
        except PlaywrightTimeout as exc:
            log(f"Playwright timeout during engagement loop: {exc}", level="WARN")
            await asyncio.sleep(15)
        except PlaywrightError as exc:
            log(f"Playwright error during engagement loop: {exc}", level="WARN")
            await asyncio.sleep(30)
        except Exception as exc:  # noqa: BLE001
            log(f"Unhandled error in engagement loop: {exc}", level="ERROR")
            await asyncio.sleep(30)


# == Entry Point ===============================================================


async def main() -> None:
    pw = None
    context = None
    try:
        pw, context, page = await create_browser()
        logged_in = await ensure_logged_in(page)
        if not logged_in:
            log("Could not confirm login. Exiting.", level="ERROR")
            return
        log("Login success — starting engagement loop...")
        await run_engagement_loop(context, page)
    except KeyboardInterrupt:
        log("Shutting down by user request.")
    except Exception as exc:  # noqa: BLE001
        log(f"Unhandled exception: {exc}", level="ERROR")
    finally:
        if context is not None:
            with suppress(Exception):
                await context.close()
        if pw is not None:
            with suppress(Exception):
                await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
