#!/usr/bin/env python3
"""Refined X auto-reply bot with modular filtering and messaging logic."""

from __future__ import annotations

import asyncio
import os
import random
import sys
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Deque, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

from configurator import (
    DEFAULT_DM_TEMPLATES,
    DEFAULT_REPLY_TEMPLATES,
    TEMPLATE_DELIMITER,
    ensure_env_file,
    parse_delimited_list,
    update_env,
)

# --- Environment ----------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ensure_env_file(ROOT_DIR)
load_dotenv(ENV_PATH)


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
    dm_interest_threshold: float

    @classmethod
    def from_env(cls) -> "BotConfig":
        debug_enabled = os.getenv("DEBUG", "").strip().lower() not in {"", "0", "false", "off"}
        profile_dir = Path(os.getenv("PW_PROFILE_DIR", ".pwprofile")).expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)

        search_topics = _split_topics(os.getenv("SEARCH_TOPICS", ""))
        if not search_topics:
            raise SystemExit("SEARCH_TOPICS env var must list at least one topic.")

        relevant_keywords = _split_keywords(os.getenv("RELEVANT_KEYWORDS", ""))
        spam_keywords = _split_keywords(os.getenv("SPAM_KEYWORDS", ""))

        referral_link = os.getenv("REFERRAL_LINK", "https://example.com/referral")
        loop_delay_seconds = int(os.getenv("LOOP_DELAY_SECONDS", str(15 * 60)))
        max_replies_per_topic = int(os.getenv("MAX_REPLIES_PER_TOPIC", "3"))
        min_tweet_length = int(os.getenv("MIN_TWEET_LENGTH", "60"))
        min_keyword_matches = int(os.getenv("MIN_KEYWORD_MATCHES", "1"))
        dm_enabled = os.getenv("ENABLE_DMS", "true").strip().lower() not in {"", "0", "false", "off"}
        dm_trigger_length = int(os.getenv("DM_TRIGGER_LENGTH", "180"))
        dm_question_weight = float(os.getenv("DM_QUESTION_WEIGHT", "0.6"))
        dm_interest_threshold = float(os.getenv("DM_INTEREST_THRESHOLD", "3.2"))

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
            dm_interest_threshold=dm_interest_threshold,
        )
def _split_keywords(raw: str) -> List[str]:
    if not raw:
        return []
    normalized = raw.replace("\n", TEMPLATE_DELIMITER).replace(",", TEMPLATE_DELIMITER)
    return [part.strip().lower() for part in normalized.split(TEMPLATE_DELIMITER) if part.strip()]


def _split_topics(raw: str) -> List[str]:
    if not raw:
        return []
    if TEMPLATE_DELIMITER in raw:
        parts = raw.split(TEMPLATE_DELIMITER)
    else:
        parts = (chunk for line in raw.splitlines() for chunk in line.split(","))
    return [topic.strip() for topic in parts if topic.strip()]


def _tokenize_phrase(text: str) -> List[str]:
    sanitized = (
        text.replace("#", " ")
        .replace("/", " ")
        .replace("-", " ")
        .replace("_", " ")
    )
    return [token for token in sanitized.lower().split() if token]


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


class TemplateManager:
    """Manages template collections sourced from the environment file."""

    def __init__(
        self,
        env_path: Path,
        env_key: str,
        fallback: Sequence[str],
        *,
        min_count: int = 1,
    ):
        self.env_path = env_path
        self.env_key = env_key
        self.fallback = list(fallback)
        self.min_count = max(1, min_count)
        self.templates = self._load_templates()
        self._pool = TemplatePool(self.templates)

    def _load_templates(self) -> List[str]:
        raw = os.getenv(self.env_key, "")
        templates = self._dedupe(parse_delimited_list(raw))
        if len(templates) < self.min_count:
            templates = self._dedupe(self.fallback)
            if len(templates) < self.min_count:
                raise ValueError(
                    f"At least {self.min_count} templates are required for {self.env_key}."
                )
            self._persist(templates)
        return templates

    def _persist(self, templates: Sequence[str]) -> None:
        serialized = TEMPLATE_DELIMITER.join(templates)
        update_env(self.env_path, {self.env_key: serialized})
        os.environ[self.env_key] = serialized

    @staticmethod
    def _dedupe(templates: Sequence[str]) -> List[str]:
        seen: set[str] = set()
        ordered: List[str] = []
        for template in templates:
            if template not in seen:
                seen.add(template)
                ordered.append(template)
        return ordered

    def _refresh_pool(self) -> None:
        if not self.templates:
            self.templates = self._dedupe(self.fallback)
        if len(self.templates) < self.min_count:
            replenished = self._dedupe(self.templates + list(self.fallback))
            if len(replenished) < self.min_count:
                raise ValueError(
                    f"At least {self.min_count} templates are required for {self.env_key}."
                )
            self.templates = replenished
        self._pool = TemplatePool(self.templates)

    def next(self, context: dict) -> str:
        return self._pool.next(context)

    def add_template(self, template: str) -> None:
        template = template.strip()
        if not template:
            raise ValueError("Template content cannot be empty.")
        self.templates.append(template)
        self._persist(self.templates)
        self._refresh_pool()

    def remove_template(self, index: int) -> None:
        if not (0 <= index < len(self.templates)):
            raise IndexError("Template index out of range.")
        del self.templates[index]
        self._persist(self.templates or self.fallback)
        self._refresh_pool()

    def edit_template(self, index: int, template: str) -> None:
        if not (0 <= index < len(self.templates)):
            raise IndexError("Template index out of range.")
        template = template.strip()
        if not template:
            raise ValueError("Template content cannot be empty.")
        self.templates[index] = template
        self._persist(self.templates)
        self._refresh_pool()


reply_manager = TemplateManager(
    ENV_PATH,
    "REPLY_TEMPLATES",
    DEFAULT_REPLY_TEMPLATES,
    min_count=10,
)
dm_manager = TemplateManager(ENV_PATH, "DM_TEMPLATES", DEFAULT_DM_TEMPLATES)


def add_reply_template(template: str) -> None:
    """Add a new public reply template and persist it to the .env file."""

    reply_manager.add_template(template)


def remove_reply_template(index: int) -> None:
    """Remove a reply template by index and persist the change."""

    reply_manager.remove_template(index)


def edit_reply_template(index: int, template: str) -> None:
    """Edit an existing reply template in place and persist it."""

    reply_manager.edit_template(index, template)


def add_dm_template(template: str) -> None:
    """Add a new DM template and persist it."""

    dm_manager.add_template(template)


def remove_dm_template(index: int) -> None:
    """Remove a DM template by index and persist the change."""

    dm_manager.remove_template(index)


def edit_dm_template(index: int, template: str) -> None:
    """Edit an existing DM template."""

    dm_manager.edit_template(index, template)


# --- Relevance Engine -----------------------------------------------------


@dataclass(slots=True)
class TopicProfile:
    """Representation of a search topic with derived alias information."""

    raw: str
    raw_lower: str = field(init=False)
    tokens: List[str] = field(init=False)
    pretty: str = field(init=False)
    key: str = field(init=False)
    aliases: List[str] = field(init=False)
    hashtags: set[str] = field(init=False)

    def __post_init__(self) -> None:
        self.raw = self.raw.strip()
        self.raw_lower = self.raw.lower()
        self.tokens = _tokenize_phrase(self.raw)
        self.pretty = _prettify_focus(self.raw)
        self.key = " ".join(self.tokens) if self.tokens else self.raw_lower
        self.aliases = self._build_aliases()
        self.hashtags = {f"#{token}" for token in self.tokens if token}

    def _build_aliases(self) -> List[str]:
        aliases = {self.raw_lower}
        if len(self.tokens) > 1:
            joined = " ".join(self.tokens)
            aliases.add(joined)
            aliases.add("-".join(self.tokens))
            aliases.add(joined.replace(" ", ""))
        for token in self.tokens:
            aliases.add(token)
        return sorted(aliases)

    def score(self, normalized_text: str) -> Tuple[float, str]:
        score = 0.0
        best_focus = self.pretty
        best_score = 0.0

        if self.raw_lower in normalized_text:
            score += 2.8
            best_focus = self.pretty
            best_score = 2.8

        for alias in self.aliases:
            if alias and alias in normalized_text:
                alias_score = 1.6 if " " in alias else 1.0 + min(len(alias) / 9, 0.8)
                score += alias_score
                if alias_score > best_score:
                    best_score = alias_score
                    best_focus = _prettify_focus(alias)

        for tag in self.hashtags:
            if tag in normalized_text:
                tag_score = 1.4
                score += tag_score
                if tag_score > best_score:
                    best_score = tag_score
                    best_focus = _prettify_focus(tag.strip("#"))

        coverage = sum(1 for token in self.tokens if token in normalized_text)
        if self.tokens:
            score += coverage / len(self.tokens)

        return score, best_focus


@dataclass(slots=True)
class RelevanceResult:
    is_relevant: bool
    topic_label: str
    focus: str
    topic_key: str
    topic_score: float
    keyword_hits: int
    interest_score: float


class RelevanceEngine:
    """Determines whether a tweet is relevant to configured search topics."""

    def __init__(
        self,
        topics: Sequence[str],
        keywords: Sequence[str],
        *,
        min_keyword_matches: int,
        base_threshold: float = 2.4,
    ) -> None:
        self.profiles = [TopicProfile(topic) for topic in topics]
        self.keyword_inventory = self._build_keywords(keywords)
        self.min_keyword_matches = max(1, min_keyword_matches)
        self.base_threshold = base_threshold

    def _build_keywords(self, keywords: Sequence[str]) -> set[str]:
        inventory = {keyword.lower() for keyword in keywords if keyword}
        for profile in self.profiles:
            inventory.update(profile.tokens)
        return inventory

    def assess(self, text: str) -> RelevanceResult:
        normalized = text.lower()
        best_profile: Optional[TopicProfile] = None
        best_focus = ""
        best_score = 0.0

        for profile in self.profiles:
            score, focus = profile.score(normalized)
            if score > best_score:
                best_score = score
                best_profile = profile
                best_focus = focus

        keyword_hits = sum(1 for keyword in self.keyword_inventory if keyword and keyword in normalized)
        interest_score = self._interest_score(text)

        if best_profile is None:
            return RelevanceResult(False, "", "", "", 0.0, keyword_hits, interest_score)

        threshold = self._topic_threshold(best_profile)
        is_relevant = best_score >= threshold and keyword_hits >= self.min_keyword_matches

        return RelevanceResult(
            is_relevant,
            best_profile.raw,
            best_focus or best_profile.pretty,
            best_profile.key,
            best_score,
            keyword_hits,
            interest_score,
        )

    def _topic_threshold(self, profile: TopicProfile) -> float:
        adjustment = 0.0
        token_count = len(profile.tokens)
        if token_count <= 1:
            adjustment -= 0.4
        elif token_count >= 3:
            adjustment += 0.3
        return self.base_threshold + adjustment

    def _interest_score(self, text: str) -> float:
        normalized = text.lower()
        length_score = min(len(normalized) / 95, 4.0)
        question_score = normalized.count("?") * 1.5
        exclamation_score = normalized.count("!") * 0.4
        detail_score = sum(1 for word in normalized.split() if len(word) >= 7) * 0.08
        callout_phrases = (
            "any tips",
            "need help",
            "looking for",
            "recommend",
            "how do you",
            "what tools",
            "anyone else",
            "best way",
            "curious how",
            "does anyone",
        )
        intent_score = 0.0
        if any(phrase in normalized for phrase in callout_phrases):
            intent_score += 1.0
        if "dm me" in normalized or "hit me up" in normalized:
            intent_score += 0.6
        return length_score + question_score + exclamation_score + detail_score + intent_score


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


relevance_engine = RelevanceEngine(
    CONFIG.search_topics,
    CONFIG.relevant_keywords,
    min_keyword_matches=CONFIG.min_keyword_matches,
)


@dataclass(slots=True)
class FilterDecision:
    is_relevant: bool
    reason: str
    matched_focus: str
    topic_score: float
    interest_score: float
    should_dm: bool


class TweetFilter:
    def __init__(self, config: BotConfig, engine: RelevanceEngine):
        self.config = config
        self.engine = engine

    def analyze(self, topic: str, tweet_text: str) -> FilterDecision:
        text = tweet_text.strip()
        if not text:
            return FilterDecision(False, "empty text", topic, 0.0, 0.0, False)

        normalized = text.lower()
        if len(normalized) < self.config.min_tweet_length:
            return FilterDecision(False, "too short", topic, 0.0, 0.0, False)

        if any(keyword and keyword in normalized for keyword in self.config.spam_keywords):
            return FilterDecision(False, "spam keywords", topic, 0.0, 0.0, False)

        relevance = self.engine.assess(text)
        if not relevance.is_relevant:
            return FilterDecision(False, "topic mismatch", relevance.focus or topic, relevance.topic_score, relevance.interest_score, False)

        if not self._topic_alignment(topic, relevance.topic_key):
            return FilterDecision(False, "topic mismatch", relevance.focus, relevance.topic_score, relevance.interest_score, False)

        should_dm = self._should_dm(normalized, relevance)
        return FilterDecision(True, "relevant", relevance.focus, relevance.topic_score, relevance.interest_score, should_dm)

    def _topic_alignment(self, search_topic: str, result_key: str) -> bool:
        search_tokens = set(_tokenize_phrase(search_topic))
        result_tokens = set(result_key.split())
        if not result_tokens:
            return False
        if not search_tokens:
            return True
        overlap = len(search_tokens & result_tokens) / len(result_tokens)
        return overlap >= 0.6 or result_tokens.issubset(search_tokens)

    def _should_dm(self, normalized_text: str, relevance: RelevanceResult) -> bool:
        if not self.config.dm_enabled:
            return False
        long_form = len(normalized_text) >= self.config.dm_trigger_length
        question_focus = normalized_text.count("?") * self.config.dm_question_weight >= 1.0
        high_interest = relevance.interest_score >= self.config.dm_interest_threshold
        intent_language = " dm " in f" {normalized_text} " or "message me" in normalized_text
        return (high_interest and (long_form or question_focus)) or (high_interest and intent_language)


tweet_filter = TweetFilter(CONFIG, relevance_engine)


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


def get_reply_message(topic: str, focus: str) -> str:
    normalized_focus = focus.strip() if focus else ""
    normalized_topic = topic.strip() if topic else normalized_focus
    context = {
        "topic": normalized_topic or normalized_focus,
        "focus": normalized_focus or normalized_topic,
        "ref_link": CONFIG.referral_link,
    }
    message = reply_manager.next(context)

    if normalized_topic and normalized_topic.lower() not in message.lower():
        suffix = f" Curious where you’re taking {normalized_topic} next."
        message = f"{message.rstrip()} {suffix}".strip()

    if CONFIG.referral_link and CONFIG.referral_link not in message:
        connector = (
            "." if message and message[-1] not in {".", "!", "?"} else ""
        )
        message = f"{message}{connector} Here’s what I’m leaning on: {CONFIG.referral_link}"

    return message


async def build_dm_message(name: str, focus: str) -> str:
    context = {
        "name": name or "there",
        "focus": focus,
        "ref_link": CONFIG.referral_link,
    }
    return dm_manager.next(context)


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

        message = get_reply_message(topic, decision.matched_focus)
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
                (
                    f"Skipped tweet #{idx + 1} for '{topic}' ({decision.reason}; "
                    f"topic_score={decision.topic_score:.2f}, interest={decision.interest_score:.2f})."
                ),
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
