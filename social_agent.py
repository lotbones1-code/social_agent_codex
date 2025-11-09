#!/usr/bin/env python3
"""Simple X auto-reply bot driven by Playwright.

The script expects the user to already be logged in using the persistent
Playwright profile directory. It repeatedly loops through the configured
search topics, opens each topic's search page, switches to the "Latest" tab,
replies to the first three tweets with a fixed message, then waits 15 minutes
before repeating the cycle.
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Iterable, List
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

# --- Environment ----------------------------------------------------------

load_dotenv()

DEBUG_ENABLED = os.getenv("DEBUG", "").strip().lower() not in {"", "0", "false", "off"}
PROFILE_DIR = Path(os.getenv("PW_PROFILE_DIR", ".pwprofile")).expanduser()
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MESSAGE = (
    "Love the insights on {topic}! I'm building AI-driven automation plays and"
    " always keen to swap ideas. Shoot me a DM or grab my favorite toolkit here:"
    " {ref_link}"
)
REPLY_MESSAGE = os.getenv("REPLY_MESSAGE", DEFAULT_MESSAGE)
REFERRAL_LINK = os.getenv("REFERRAL_LINK", "https://example.com/referral")
MAX_REPLIES_PER_TOPIC = int(os.getenv("MAX_REPLIES_PER_TOPIC", "3"))
MIN_TWEET_LENGTH = int(os.getenv("MIN_TWEET_LENGTH", "40"))


def _split_keywords(raw: str) -> List[str]:
    return [part.strip().lower() for part in raw.replace("\n", ",").split(",") if part.strip()]


DEFAULT_RELEVANT_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "automation",
    "autonomous",
    "chatgpt",
    "gpt",
    "openai",
    "crypto",
    "cryptocurrency",
    "blockchain",
    "defi",
    "web3",
    "trading",
    "algorithmic trading",
    "quant",
    "quantitative",
    "machine learning",
]
DEFAULT_SPAM_KEYWORDS = [
    "giveaway",
    "airdrop",
    "free nft",
    "pump",
    "casino",
    "xxx",
    "sex",
    "nsfw",
    "follow for follow",
]

RELEVANT_KEYWORDS = _split_keywords(
    os.getenv("RELEVANT_KEYWORDS", ",".join(DEFAULT_RELEVANT_KEYWORDS))
)
SPAM_KEYWORDS = _split_keywords(os.getenv("SPAM_KEYWORDS", ",".join(DEFAULT_SPAM_KEYWORDS)))
LOOP_DELAY_SECONDS = int(os.getenv("LOOP_DELAY_SECONDS", str(15 * 60)))


def _split_topics(raw: str) -> List[str]:
    parts: Iterable[str]
    if "\n" in raw:
        parts = (chunk for line in raw.splitlines() for chunk in line.split(","))
    else:
        parts = raw.split(",")
    return [topic.strip() for topic in parts if topic.strip()]


SEARCH_TOPICS = _split_topics(os.getenv("SEARCH_TOPICS", ""))
if not SEARCH_TOPICS:
    raise SystemExit("SEARCH_TOPICS env var must list at least one topic.")


# --- Logging --------------------------------------------------------------

def log(message: str, *, level: str = "info") -> None:
    if level == "debug" and not DEBUG_ENABLED:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level.upper()}] {message}"
    print(line)
    sys.stdout.flush()


# --- Playwright helpers ---------------------------------------------------

async def ensure_page(context):
    page = context.pages[0] if context.pages else await context.new_page()
    await page.set_viewport_size({"width": 1280, "height": 720})
    return page


async def click_latest_tab(page) -> None:
    selectors = [
        "a[role='tab'][href*='f=live']",
        "a[role='tab']:has-text('Latest')",
        "a[href*='f=live']",
    ]
    for selector in selectors:
        tab = page.locator(selector).first
        if await tab.count():
            try:
                await tab.click()
                log("Selected Latest tab", level="debug")
                await page.wait_for_timeout(500)
                return
            except PlaywrightError as exc:
                log(f"Failed to click Latest tab via {selector}: {exc}", level="debug")
    log("Latest tab not found; continuing with default view.", level="warning")


async def wait_for_tweets(page) -> None:
    try:
        await page.wait_for_selector("article[data-testid='tweet']", timeout=15_000)
    except PlaywrightTimeout:
        log("No tweets found in Latest tab within timeout.", level="warning")


async def open_search(page, topic: str) -> None:
    encoded = quote_plus(topic)
    url = f"https://x.com/search?q={encoded}&src=typed_query"
    log(f"Navigating to search page for topic: {topic}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    except PlaywrightTimeout as exc:
        log(f"Timed out loading search page for '{topic}': {exc}", level="error")
        return
    except PlaywrightError as exc:
        log(f"Playwright failed to load search page for '{topic}': {exc}", level="error")
        return
    await page.wait_for_timeout(1500)
    await click_latest_tab(page)
    await wait_for_tweets(page)


async def close_composer_if_open(page) -> None:
    composer = page.locator("div[data-testid^='tweetTextarea_']").first
    if await composer.count():
        with suppress(Exception):
            await page.keyboard.press("Escape")
        await page.wait_for_timeout(250)


async def extract_tweet_text(tweet_locator) -> str:
    text_locator = tweet_locator.locator("div[data-testid='tweetText']").first
    if not await text_locator.count():
        return ""
    try:
        raw_text = await text_locator.inner_text()
    except PlaywrightError as exc:
        log(f"Failed to extract tweet text: {exc}", level="debug")
        return ""
    cleaned = " ".join(raw_text.split())
    return cleaned.strip()


def is_tweet_relevant(tweet_text: str) -> bool:
    if not tweet_text:
        return False

    normalized = tweet_text.lower()
    if len(normalized) < MIN_TWEET_LENGTH:
        return False

    if any(keyword in normalized for keyword in SPAM_KEYWORDS):
        return False

    if RELEVANT_KEYWORDS and any(keyword in normalized for keyword in RELEVANT_KEYWORDS):
        return True

    return False


async def reply_to_tweet(page, tweet_locator, topic: str, index: int) -> bool:
    log(f"Replying to tweet #{index + 1} for '{topic}'.", level="debug")
    try:
        reply_button = tweet_locator.locator("[data-testid='reply']").first
        if not await reply_button.count():
            log("Reply button not found for tweet; skipping.", level="warning")
            return False
        await reply_button.click()
        await page.wait_for_timeout(500)

        textbox = page.locator("div[data-testid='tweetTextarea_0']").first
        if not await textbox.count():
            textbox = page.locator("div[data-testid='tweetTextarea_1']").first
        if not await textbox.count():
            log("Reply textbox not found; skipping tweet.", level="warning")
            await close_composer_if_open(page)
            return False

        await textbox.click()
        try:
            message = REPLY_MESSAGE.format(topic=topic, ref_link=REFERRAL_LINK)
        except KeyError:
            message = REPLY_MESSAGE.format(topic=topic)
        await page.keyboard.type(message, delay=20)
        await page.wait_for_timeout(200)
        await page.keyboard.press("Meta+Enter")
        await page.wait_for_timeout(1500)
        log(f"Sent reply #{index + 1} for '{topic}'.")
        return True
    except PlaywrightTimeout as exc:
        log(f"Timeout while replying to tweet #{index + 1} for '{topic}': {exc}", level="error")
    except PlaywrightError as exc:
        log(f"Playwright error while replying to tweet #{index + 1} for '{topic}': {exc}", level="error")
    except Exception as exc:  # noqa: BLE001
        log(f"Unexpected error while replying to tweet #{index + 1} for '{topic}': {exc}", level="error")
    finally:
        await close_composer_if_open(page)
    return False


async def process_topic(page, topic: str) -> None:
    await open_search(page, topic)
    tweets = page.locator("article[data-testid='tweet']")
    count = await tweets.count()
    if count == 0:
        log(f"No tweets found for '{topic}'.", level="warning")
        return

    replies_sent = 0
    for idx in range(count):
        if replies_sent >= MAX_REPLIES_PER_TOPIC:
            break

        tweet = tweets.nth(idx)
        tweet_text = await extract_tweet_text(tweet)
        if not tweet_text:
            log(f"Skipped tweet #{idx + 1} for '{topic}' (no readable text).", level="debug")
            continue

        if not is_tweet_relevant(tweet_text):
            log(
                f"Skipped tweet #{idx + 1} for '{topic}' (irrelevant content).",
                level="debug",
            )
            continue

        success = await reply_to_tweet(page, tweet, topic, idx)
        if success:
            replies_sent += 1
            await page.wait_for_timeout(1500)
    log(f"Finished topic '{topic}' with {replies_sent} replies.")


async def run_bot() -> None:
    log(f"Starting bot with topics: {', '.join(SEARCH_TOPICS)}")
    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
    ]

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            headless=False,
            args=browser_args,
        )
        try:
            page = await ensure_page(context)
            log("Browser ready. Beginning main loop.")
            while True:
                for topic in SEARCH_TOPICS:
                    try:
                        await process_topic(page, topic)
                    except Exception as exc:  # noqa: BLE001
                        log(f"Error while processing topic '{topic}': {exc}", level="error")
                log(
                    f"Cycle complete. Waiting {LOOP_DELAY_SECONDS // 60} minutes before restarting.",
                    level="info",
                )
                await asyncio.sleep(LOOP_DELAY_SECONDS)
        finally:
            await context.close()


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log("Interrupted by user. Exiting.", level="info")


if __name__ == "__main__":
    main()
