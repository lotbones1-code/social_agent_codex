#!/usr/bin/env python3
"""Refined X auto-reply bot with modular filtering and messaging logic."""

from __future__ import annotations

import asyncio
import os
import random
import sys
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Iterable, List, Optional, Sequence
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

# --- Environment ----------------------------------------------------------

load_dotenv()


@dataclass(slots=True)
class BotConfig:
    debug_enabled: bool
    profile_dir: Path
    search_topics: List[str]
    relevant_keywords: List[str]
    spam_keywords: List[str]
    referral_link: str
    loop_delay_seconds: int
    max_replies_per_topic: int
    min_tweet_length: int
    min_keyword_matches: int
    dm_enabled: bool
    dm_trigger_length: int
    dm_question_weight: float

    @classmethod
    def from_env(cls) -> "BotConfig":
        debug_enabled = os.getenv("DEBUG", "").strip().lower() not in {"", "0", "false", "off"}
        profile_dir = Path(os.getenv("PW_PROFILE_DIR", ".pwprofile")).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)

        search_topics = _split_topics(os.getenv("SEARCH_TOPICS", ""))
        if not search_topics:
            raise SystemExit("SEARCH_TOPICS env var must list at least one topic.")

        relevant_keywords = _split_keywords(
            os.getenv("RELEVANT_KEYWORDS", ",".join(DEFAULT_RELEVANT_KEYWORDS))
        )
        spam_keywords = _split_keywords(os.getenv("SPAM_KEYWORDS", ",".join(DEFAULT_SPAM_KEYWORDS)))

        referral_link = os.getenv("REFERRAL_LINK", "https://example.com/referral")
        loop_delay_seconds = int(os.getenv("LOOP_DELAY_SECONDS", str(15 * 60)))
        max_replies_per_topic = int(os.getenv("MAX_REPLIES_PER_TOPIC", "3"))
        min_tweet_length = int(os.getenv("MIN_TWEET_LENGTH", "60"))
        min_keyword_matches = int(os.getenv("MIN_KEYWORD_MATCHES", "1"))
        dm_enabled = os.getenv("ENABLE_DMS", "true").strip().lower() not in {"", "0", "false", "off"}
        dm_trigger_length = int(os.getenv("DM_TRIGGER_LENGTH", "180"))
        dm_question_weight = float(os.getenv("DM_QUESTION_WEIGHT", "0.6"))

        return cls(
            debug_enabled=debug_enabled,
            profile_dir=profile_dir,
            search_topics=search_topics,
            relevant_keywords=relevant_keywords,
            spam_keywords=spam_keywords,
            referral_link=referral_link,
            loop_delay_seconds=loop_delay_seconds,
            max_replies_per_topic=max_replies_per_topic,
            min_tweet_length=min_tweet_length,
            min_keyword_matches=min_keyword_matches,
            dm_enabled=dm_enabled,
            dm_trigger_length=dm_trigger_length,
            dm_question_weight=dm_question_weight,
        )


DEFAULT_REPLY_TEMPLATES = [
    (
        "Been deep in {focus} lately and found this toolkit that keeps overdelivering—"
        "sharing because it sliced hours off my build time: {ref_link}"
    ),
    (
        "Every time {focus} comes up I think about how this playbook boosted my results."
        " If you want the exact steps I'm using, here it is: {ref_link}"
    ),
    (
        "Your take on {focus} reminds me of what helped me scale fast."
        " My go-to breakdown lives here if you want to peek: {ref_link}"
    ),
    (
        "I just walked a few friends through my {focus} setup—"
        "it's wild how much time it's saving us. Cliff notes + tools: {ref_link}"
    ),
    (
        "If you're experimenting with {focus}, the system I switched to paid for itself in a week."
        " Detailing the flow here: {ref_link}"
    ),
    (
        "Noticed you're diving into {focus} too."
        " Here's the resource that helped me automate the messy parts: {ref_link}"
    ),
    (
        "I'm seeing more creators win with {focus}; I know several who migrated after I did."
        " Dropping the same starter kit we rave about: {ref_link}"
    ),
    (
        "Whenever someone asks how I monetized {focus}, I point them to this breakdown."
        " It feels like cheating in the best way: {ref_link}"
    ),
]

DEFAULT_DM_TEMPLATES = [
    (
        "Hey {name}! Loved how you framed {focus}."
        " I pulled together a behind-the-scenes walkthrough that helped me ship faster—"
        "happy to send you the exact stack if you're curious: {ref_link}"
    ),
    (
        "Appreciated your deep dive on {focus}."
        " If you want more candid thoughts, I have a personal write-up here."
        " Feel free to poke me with questions: {ref_link}"
    ),
    (
        "You're clearly serious about {focus}, so I figured I'd share what worked for me."
        " This link is my private notes + tools—"
        "let me know if you want me to unpack anything: {ref_link}"
    ),
]


def _split_templates(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    parts: List[str]
    if "||" in raw:
        parts = raw.split("||")
    else:
        parts = raw.splitlines()
    return [part.strip() for part in parts if part.strip()]


ENV_REPLY_TEMPLATES = _split_templates(os.getenv("REPLY_TEMPLATES"))
REPLY_TEMPLATES = (
    ENV_REPLY_TEMPLATES if len(ENV_REPLY_TEMPLATES) >= 7 else DEFAULT_REPLY_TEMPLATES
)
ENV_DM_TEMPLATES = _split_templates(os.getenv("DM_TEMPLATES"))
DM_TEMPLATES = ENV_DM_TEMPLATES if ENV_DM_TEMPLATES else DEFAULT_DM_TEMPLATES


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
    "making money online",
    "side hustle",
    "passive income",
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


def _split_keywords(raw: str) -> List[str]:
    return [part.strip().lower() for part in raw.replace("\n", ",").split(",") if part.strip()]


def _split_topics(raw: str) -> List[str]:
    parts: Iterable[str]
    if "\n" in raw:
        parts = (chunk for line in raw.splitlines() for chunk in line.split(","))
    else:
        parts = raw.split(",")
    return [topic.strip() for topic in parts if topic.strip()]


# --- Logging --------------------------------------------------------------

def log(message: str, *, level: str = "info") -> None:
    if level == "debug" and not CONFIG.debug_enabled:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level.upper()}] {message}"
    print(line)
    sys.stdout.flush()


CONFIG = BotConfig.from_env()


# --- Template Management --------------------------------------------------


class TemplatePool:
    """Manages rotation of natural-sounding templates without repetition."""

    def __init__(self, templates: Sequence[str]):
        if len(templates) == 0:
            raise ValueError("At least one template is required.")
        self.templates = list(templates)
        self._queue: Deque[str] = deque()
        self._last_used: Optional[str] = None
        self._reshuffle()

    def _reshuffle(self) -> None:
        order = self.templates[:]
        random.shuffle(order)
        if self._last_used and order and order[0] == self._last_used:
            order.append(order.pop(0))
        self._queue = deque(order)

    def next(self, context: dict) -> str:
        if not self._queue:
            self._reshuffle()
        template = self._queue.popleft()
        self._last_used = template
        return template.format(**context)


reply_templates = TemplatePool(REPLY_TEMPLATES)
dm_templates = TemplatePool(DM_TEMPLATES)


SPECIAL_FOCUS_FORMATTING = {
    "ai": "AI",
    "gpt": "GPT",
    "chatgpt": "ChatGPT",
    "defi": "DeFi",
    "web3": "Web3",
}


def _prettify_focus(raw: str) -> str:
    key = raw.strip().lower()
    if key in SPECIAL_FOCUS_FORMATTING:
        return SPECIAL_FOCUS_FORMATTING[key]
    words = raw.split()
    formatted_words = [word.upper() if len(word) <= 3 else word.capitalize() for word in words]
    return " ".join(formatted_words)


@dataclass(slots=True)
class FilterDecision:
    is_relevant: bool
    reason: str
    matched_focus: str
    quality_score: float
    should_dm: bool


class TweetFilter:
    def __init__(self, config: BotConfig):
        self.config = config

    def analyze(self, topic: str, tweet_text: str) -> FilterDecision:
        normalized = tweet_text.lower()
        if not normalized:
            return FilterDecision(False, "empty text", topic, 0.0, False)

        if len(normalized) < self.config.min_tweet_length:
            return FilterDecision(False, "too short", topic, 0.0, False)

        if any(keyword in normalized for keyword in self.config.spam_keywords):
            return FilterDecision(False, "spam keywords", topic, 0.0, False)

        matched_focus = self._match_focus(topic, normalized)
        if not matched_focus:
            return FilterDecision(False, "topic mismatch", topic, 0.0, False)

        keyword_matches = sum(1 for keyword in self.config.relevant_keywords if keyword in normalized)
        if keyword_matches < self.config.min_keyword_matches:
            return FilterDecision(False, "insufficient keyword matches", matched_focus, 0.0, False)

        quality_score = self._score_quality(normalized, keyword_matches)
        should_dm = self._should_dm(normalized, quality_score)
        return FilterDecision(True, "relevant", matched_focus, quality_score, should_dm)

    def _match_focus(self, topic: str, normalized_text: str) -> str:
        topic_tokens = [token.strip("# ") for token in topic.lower().split() if token.strip("# ")]
        for token in topic_tokens:
            if token and token in normalized_text:
                return _prettify_focus(token)
        for keyword in self.config.relevant_keywords:
            if keyword in normalized_text:
                return _prettify_focus(keyword)
        return ""

    def _score_quality(self, normalized_text: str, keyword_matches: int) -> float:
        sentence_breaks = normalized_text.count(".") + normalized_text.count("!")
        question_marks = normalized_text.count("?")
        hashtags = normalized_text.count("#")
        length_factor = min(len(normalized_text) / (self.config.min_tweet_length * 1.5), 2.0)
        structure_bonus = 0.2 * sentence_breaks + 0.3 * question_marks
        keyword_bonus = 0.5 * min(keyword_matches, 4)
        hashtag_penalty = -0.2 if hashtags > 5 else 0.0
        return max(0.0, length_factor + structure_bonus + keyword_bonus + hashtag_penalty)

    def _should_dm(self, normalized_text: str, quality_score: float) -> bool:
        if not CONFIG.dm_enabled:
            return False
        long_form = len(normalized_text) >= self.config.dm_trigger_length
        question_focus = normalized_text.count("?") * self.config.dm_question_weight >= 1.0
        high_quality = quality_score >= 2.5
        return long_form or (question_focus and high_quality)


tweet_filter = TweetFilter(CONFIG)


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
        await page.wait_for_selector("article[data-testid='tweet']", timeout=20_000)
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


async def extract_author_name(tweet_locator) -> str:
    name_locator = tweet_locator.locator("div[data-testid='User-Names'] span").first
    if await name_locator.count():
        try:
            name_text = await name_locator.inner_text()
            return " ".join(name_text.split())
        except PlaywrightError:
            return "there"
    return "there"


async def build_reply_message(topic: str, tweet_text: str, focus: str) -> str:
    context = {
        "topic": topic,
        "focus": focus,
        "ref_link": CONFIG.referral_link,
    }
    return reply_templates.next(context)


async def build_dm_message(name: str, focus: str) -> str:
    context = {
        "name": name or "there",
        "focus": focus,
        "ref_link": CONFIG.referral_link,
    }
    return dm_templates.next(context)


async def send_reply(page, message: str) -> bool:
    textbox = page.locator("div[data-testid='tweetTextarea_0']").first
    if not await textbox.count():
        textbox = page.locator("div[data-testid='tweetTextarea_1']").first
    if not await textbox.count():
        log("Reply textbox not found; skipping tweet.", level="warning")
        await close_composer_if_open(page)
        return False

    await textbox.click()
    await page.keyboard.type(message, delay=random.randint(18, 26))
    await page.wait_for_timeout(200)
    await page.keyboard.press("Meta+Enter")
    await page.wait_for_timeout(1500)
    return True


async def open_reply_composer(page, tweet_locator) -> bool:
    reply_button = tweet_locator.locator("[data-testid='reply']").first
    if not await reply_button.count():
        log("Reply button not found for tweet; skipping.", level="warning")
        return False
    await reply_button.click()
    await page.wait_for_timeout(500)
    return True


async def send_dm_to_author(page, tweet_locator, focus: str) -> bool:
    if not CONFIG.dm_enabled:
        return False

    context = page.context
    user_link = tweet_locator.locator("div[data-testid='User-Names'] a").first
    if not await user_link.count():
        log("Author profile link not found for DM.", level="debug")
        return False

    profile_url = await user_link.get_attribute("href")
    if not profile_url:
        log("Unable to resolve author profile URL.", level="debug")
        return False

    dm_page = await context.new_page()
    try:
        await dm_page.goto(profile_url, wait_until="domcontentloaded", timeout=45_000)
        message_button = dm_page.locator("[data-testid='DMButton']").first
        if not await message_button.count():
            log("DM button not available for this user.", level="debug")
            return False
        await message_button.click()
        await dm_page.wait_for_timeout(1000)

        composer = dm_page.locator("div[data-testid='dmComposerTextInput']").first
        if not await composer.count():
            composer = dm_page.locator("div[data-testid^='tweetTextarea_']").first
        if not await composer.count():
            log("DM composer not found.", level="debug")
            return False

        await composer.click()
        author_name = await extract_author_name(tweet_locator)
        message = await build_dm_message(author_name, focus)
        await dm_page.keyboard.type(message, delay=random.randint(18, 26))
        await dm_page.wait_for_timeout(300)
        with suppress(Exception):
            await dm_page.keyboard.press("Meta+Enter")
        await dm_page.wait_for_timeout(1200)
        log(f"Sent DM to {author_name} about {focus}.")
        return True
    except PlaywrightTimeout as exc:
        log(f"Timeout while attempting DM: {exc}", level="debug")
        return False
    except PlaywrightError as exc:
        log(f"Playwright error while attempting DM: {exc}", level="debug")
        return False
    finally:
        await dm_page.close()


async def reply_to_tweet(page, tweet_locator, topic: str, index: int, tweet_text: str, decision: FilterDecision) -> bool:
    log(
        f"Replying to tweet #{index + 1} for '{topic}' with focus '{decision.matched_focus}'.",
        level="debug",
    )
    try:
        opened = await open_reply_composer(page, tweet_locator)
        if not opened:
            return False

        message = await build_reply_message(topic, tweet_text, decision.matched_focus)
        success = await send_reply(page, message)
        if success:
            log(f"Sent reply #{index + 1} for '{topic}'.")
            if decision.should_dm:
                dm_success = await send_dm_to_author(page, tweet_locator, decision.matched_focus)
                if dm_success:
                    log(
                        f"Followed up with DM for tweet #{index + 1} on '{topic}'.",
                        level="debug",
                    )
        return success
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
        if replies_sent >= CONFIG.max_replies_per_topic:
            break

        tweet = tweets.nth(idx)
        tweet_text = await extract_tweet_text(tweet)
        if not tweet_text:
            log(f"Skipped tweet #{idx + 1} for '{topic}' (no readable text).", level="debug")
            continue

        decision = tweet_filter.analyze(topic, tweet_text)
        if not decision.is_relevant:
            log(
                f"Skipped tweet #{idx + 1} for '{topic}' ({decision.reason}).",
                level="debug",
            )
            continue

        success = await reply_to_tweet(page, tweet, topic, idx, tweet_text, decision)
        if success:
            replies_sent += 1
            await page.wait_for_timeout(2000)
    log(f"Finished topic '{topic}' with {replies_sent} replies.")


async def run_bot() -> None:
    log(f"Starting bot with topics: {', '.join(CONFIG.search_topics)}")
    browser_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
    ]

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(CONFIG.profile_dir),
            headless=False,
            args=browser_args,
        )
        try:
            page = await ensure_page(context)
            log("Browser ready. Beginning main loop.")
            while True:
                for topic in CONFIG.search_topics:
                    try:
                        await process_topic(page, topic)
                    except Exception as exc:  # noqa: BLE001
                        log(f"Error while processing topic '{topic}': {exc}", level="error")
                log(
                    f"Cycle complete. Waiting {CONFIG.loop_delay_seconds // 60} minutes before restarting.",
                    level="info",
                )
                await asyncio.sleep(CONFIG.loop_delay_seconds)
        finally:
            await context.close()


def main() -> None:
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        log("Interrupted by user. Exiting.", level="info")


if __name__ == "__main__":
    main()
