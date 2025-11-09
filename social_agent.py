#!/usr/bin/env python3
"""Production-ready social agent for engaging with X (Twitter)."""

from __future__ import annotations

import asyncio
import json
import os
import random
from contextlib import suppress
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

load_dotenv()


def bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def list_env(name: str) -> list[str]:
    """
    Parse env var into a list of strings.

    Supports both comma-separated and '||'-separated values.
    Example:
      "AI automation, growth hacking"
      "AI automation||growth hacking"
    Both become ["AI automation", "growth hacking"].

    Trims whitespace, drops empties.
    """
    raw = os.getenv(name, "") or ""
    if not raw.strip():
        return []
    parts: list[str] = []
    for chunk in raw.split("||"):
        for sub in chunk.split(","):
            s = sub.strip()
            if s:
                parts.append(s)
    return parts


SEARCH_TOPICS = list_env("SEARCH_TOPICS")
RELEVANT_KEYWORDS_RAW = list_env("RELEVANT_KEYWORDS")
SPAM_KEYWORDS_RAW = list_env("SPAM_KEYWORDS")

RELEVANT_KEYWORDS = [k.lower() for k in RELEVANT_KEYWORDS_RAW]
SPAM_KEYWORDS = [k.lower() for k in SPAM_KEYWORDS_RAW]

try:
    MIN_TWEET_LENGTH = int(os.getenv("MIN_TWEET_LENGTH", "40"))
except ValueError:
    print("[WARN] Invalid MIN_TWEET_LENGTH value. Using default 40.")
    MIN_TWEET_LENGTH = 40

try:
    MIN_KEYWORD_MATCHES = int(os.getenv("MIN_KEYWORD_MATCHES", "1"))
except ValueError:
    print("[WARN] Invalid MIN_KEYWORD_MATCHES value. Using default 1.")
    MIN_KEYWORD_MATCHES = 1

try:
    MAX_REPLIES_PER_TOPIC = int(os.getenv("MAX_REPLIES_PER_TOPIC", "3"))
except ValueError:
    print("[WARN] Invalid MAX_REPLIES_PER_TOPIC value. Using default 3.")
    MAX_REPLIES_PER_TOPIC = 3

try:
    ACTION_DELAY_MIN = int(os.getenv("ACTION_DELAY_MIN_SECONDS", "20"))
except ValueError:
    print("[WARN] Invalid ACTION_DELAY_MIN_SECONDS value. Using default 20.")
    ACTION_DELAY_MIN = 20

try:
    ACTION_DELAY_MAX = int(os.getenv("ACTION_DELAY_MAX_SECONDS", "40"))
except ValueError:
    print("[WARN] Invalid ACTION_DELAY_MAX_SECONDS value. Using default 40.")
    ACTION_DELAY_MAX = 40

try:
    LOOP_DELAY_SECONDS = int(os.getenv("LOOP_DELAY_SECONDS", "120"))
except ValueError:
    print("[WARN] Invalid LOOP_DELAY_SECONDS value. Using default 120.")
    LOOP_DELAY_SECONDS = 120

if ACTION_DELAY_MAX < ACTION_DELAY_MIN:
    print("[WARN] ACTION_DELAY_MAX_SECONDS < ACTION_DELAY_MIN_SECONDS. Aligning to minimum.")
    ACTION_DELAY_MAX = ACTION_DELAY_MIN

if LOOP_DELAY_SECONDS < 0:
    print("[WARN] LOOP_DELAY_SECONDS was negative. Using default 120.")
    LOOP_DELAY_SECONDS = 120

HEADLESS = bool_env("HEADLESS", default=False)
DEBUG = bool_env("DEBUG", default=False)
ENABLE_DMS = bool_env("ENABLE_DMS", default=False)

REFERRAL_LINK = (os.getenv("REFERRAL_LINK") or "").strip()
REPLY_TEMPLATES_RAW = os.getenv("REPLY_TEMPLATES", "")
X_USERNAME = (os.getenv("X_USERNAME") or "").strip()
X_PASSWORD = (os.getenv("X_PASSWORD") or "").strip()

DEFAULT_MESSAGE = (
    f"I’ve been using this AI automation setup to offload a ton of work. "
    f"If you want the exact stack I use, here’s the breakdown: {REFERRAL_LINK}"
    if REFERRAL_LINK
    else "I’ve been using this AI automation setup to offload a ton of work."
)

REPLY_TEMPLATES = [
    t.strip() for t in REPLY_TEMPLATES_RAW.split("||") if t.strip()
]


def make_reply_text(topic: str, focus: str = "", ref_link: str | None = None) -> str:
    if REPLY_TEMPLATES:
        tpl = random.choice(REPLY_TEMPLATES)
        return tpl.format(
            topic=topic,
            focus=focus or topic,
            ref_link=ref_link or REFERRAL_LINK or "",
        ).strip()
    return DEFAULT_MESSAGE


PW_PROFILE_DIR = os.getenv("PW_PROFILE_DIR", ".pwprofile")
PW_PROFILE_PATH = Path(PW_PROFILE_DIR)
PW_PROFILE_PATH.mkdir(parents=True, exist_ok=True)

MESSAGE_LOG_PATH = Path(os.getenv("MESSAGE_REGISTRY_PATH", "logs/replied.json"))
MESSAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_registry() -> set[str]:
    if not MESSAGE_LOG_PATH.exists():
        return set()
    try:
        with MESSAGE_LOG_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return set()
    if isinstance(data, list):
        return {str(item) for item in data if isinstance(item, str)}
    return set()


def _save_registry(entries: Iterable[str]) -> None:
    try:
        with MESSAGE_LOG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(sorted(set(entries)), handle, indent=2)
    except OSError as exc:
        print(f"[WARN] Failed to persist registry: {exc}")


REPLIED_TWEETS: set[str] = _load_registry()

TWEET_SELECTOR = "article[data-testid='tweet']"

print(f"[INFO] Loaded {len(SEARCH_TOPICS)} search topics from SEARCH_TOPICS")
print(f"[INFO] Using HEADLESS={HEADLESS}")
if ENABLE_DMS:
    print("[INFO] ENABLE_DMS is true, but DM workflows are not implemented in this build.")


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
        if page.is_closed():
            return False
    except PlaywrightError:
        return False

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
    try:
        current_url = page.url
    except PlaywrightError:
        current_url = ""
    return "x.com/home" in current_url or "twitter.com/home" in current_url


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

    username = X_USERNAME
    password = X_PASSWORD

    if username and password:
        try:
            await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            await page.fill("input[name='text']", username)
            await page.keyboard.press("Enter")
            await page.wait_for_selector("input[name='password']", timeout=30000)
            await page.fill("input[name='password']", password)
            await page.keyboard.press("Enter")
            with suppress(PlaywrightTimeout):
                await page.wait_for_url("**/home", timeout=60000)
            await asyncio.sleep(3)
            if await is_logged_in(page):
                print("[INFO] Login via credentials succeeded.")
                return True
            print("[WARN] Credential login did not complete. Falling back to manual login.")
        except PlaywrightTimeout:
            print("[WARN] Timeout while logging in with provided credentials.")
        except PlaywrightError as exc:
            print(f"[WARN] Playwright error during credential login: {exc}")

    print("[INFO] Please log in manually in the opened browser window...")
    try:
        await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightError:
        pass

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


async def get_tweet_elements(page: Page) -> list[Locator]:
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


async def extract_tweet_data(tweet: Locator) -> dict[str, str] | None:
    try:
        text_locator = tweet.locator("div[data-testid='tweetText']")
        text = (await text_locator.inner_text()).strip()
    except PlaywrightError:
        return None

    if not text:
        return None

    tweet_href = ""
    try:
        link = tweet.locator("a[href*='/status/']").first
        tweet_href = (await link.get_attribute("href")) or ""
    except PlaywrightError:
        tweet_href = ""

    author_handle = ""
    try:
        user_link = tweet.locator("div[data-testid='User-Name'] a").first
        href = await user_link.get_attribute("href")
        if href:
            author_handle = href.rstrip("/").split("/")[-1]
    except PlaywrightError:
        author_handle = ""

    tweet_url = tweet_href
    if tweet_href.startswith("/"):
        tweet_url = f"https://x.com{tweet_href}"

    tweet_id = ""
    if "/status/" in tweet_href:
        tweet_id = tweet_href.rsplit("/", 1)[-1]
    if not tweet_id:
        tweet_id = f"tweet-{abs(hash(text))}"

    return {
        "id": tweet_id,
        "url": tweet_url,
        "handle": author_handle,
        "text": text,
    }


def _register_reply(identifier: str) -> None:
    REPLIED_TWEETS.add(identifier)
    _save_registry(REPLIED_TWEETS)


def _already_replied(identifier: str) -> bool:
    return identifier in REPLIED_TWEETS


async def send_reply(page: Page, tweet: Locator, message: str) -> bool:
    try:
        await tweet.locator("div[data-testid='reply']").click()
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        await composer.wait_for(timeout=10000)
        await composer.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(message)
        await page.locator("div[data-testid='tweetButtonInline']").click()
        await asyncio.sleep(2)
        return True
    except PlaywrightTimeout:
        print("[WARN] Timeout while composing reply.")
    except PlaywrightError as exc:
        print(f"[WARN] Failed to send reply: {exc}")
    return False


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
    print(f"[INFO] Loaded {len(tweets)} raw tweets for topic '{topic}'.")
    if not tweets:
        print(f"[INFO] No tweets for topic '{topic}'. Skipping.")
        return

    await process_tweets(page, tweets, topic)


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
    print(f"[INFO] Loaded {len(tweets)} raw tweets for topic 'home timeline'.")
    if not tweets:
        print("[INFO] No tweets loaded on home timeline. Skipping.")
        return

    await process_tweets(page, tweets, "home timeline")


async def process_tweets(page: Page, tweets: list[Locator], topic: str) -> None:
    candidates: list[tuple[dict[str, str], Locator]] = []

    for tweet in tweets:
        if page.is_closed():
            print("[WARN] Page closed during tweet processing. Stopping current cycle.")
            return

        data = await extract_tweet_data(tweet)
        if not data:
            continue

        text = data["text"].strip()
        identifier = data["url"] or data["id"]
        text_lower = text.lower()
        matches = sum(1 for kw in RELEVANT_KEYWORDS if kw in text_lower)
        is_spam = any(bad in text_lower for bad in SPAM_KEYWORDS)
        length_ok = len(text) >= MIN_TWEET_LENGTH
        keyword_ok = matches >= MIN_KEYWORD_MATCHES if RELEVANT_KEYWORDS else True
        self_authored = False
        if X_USERNAME and data["handle"]:
            self_authored = data["handle"].lower() == X_USERNAME.lower()
        already_replied = _already_replied(identifier)

        if DEBUG:
            print(
                f"[DEBUG] tweet {data['id']} by @{data['handle'] or 'unknown'}: "
                f"len={len(text)}, matches={matches}, spam={is_spam}, replied={already_replied}"
            )

        eligible = (
            length_ok
            and not is_spam
            and keyword_ok
            and not self_authored
            and not already_replied
        )

        if eligible:
            candidates.append((data, tweet))

    print(f"[INFO] {len(candidates)} eligible tweets for topic '{topic}' after filtering.")

    if not candidates:
        print(f"[INFO] No eligible tweets for topic '{topic}'.")
        return

    replies = 0
    for data, tweet in candidates:
        if replies >= MAX_REPLIES_PER_TOPIC:
            break

        reply_text = make_reply_text(topic, focus=data["text"])
        if await send_reply(page, tweet, reply_text):
            _register_reply(data["url"] or data["id"])
            print(
                f"[INFO] Replied to @{data['handle'] or 'unknown'} on topic '{topic}' "
                f"(tweet id {data['id']})."
            )
            replies += 1
            await asyncio.sleep(random.randint(ACTION_DELAY_MIN, ACTION_DELAY_MAX))


async def run_engagement_loop(page: Page) -> None:
    while True:
        try:
            if page.is_closed():
                print("[INFO] Page closed — ending engagement loop.")
                return

            topics = SEARCH_TOPICS or []
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
            message = str(exc).lower()
            if "has been closed" in message or "target closed" in message:
                print("[INFO] Browser or page closed — stopping engagement loop.")
                return
            await asyncio.sleep(10)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Unexpected error in engagement loop: {exc}")
            await asyncio.sleep(10)


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
    except PlaywrightError as exc:
        print(f"[ERROR] Playwright error in main: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unhandled exception in main: {exc}")
    finally:
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
