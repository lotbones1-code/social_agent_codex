#!/usr/bin/env python3
"""Sync Playwright social agent with persistent X session handling."""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)

try:  # Playwright 1.49 exports TargetClosedError; older builds may not.
    from playwright.sync_api import TargetClosedError  # type: ignore
except ImportError:  # pragma: no cover - fallback for minimal builds.
    TargetClosedError = PlaywrightError  # type: ignore

DEFAULT_AUTH_FILE = "auth.json"
DEFAULT_REPLY_TEMPLATES = [
    "Been riffing with other builders about {topic}, and this {focus} breakdown keeps delivering wins. Shortcut link: {ref_link}",
    "Every time {topic} comes up, I point people to this {focus} playbook: {ref_link}",
]
DEFAULT_HELPFUL_REPLY_TEMPLATES = [
    "This is a really interesting perspective on {topic}. The way you explained {focus} is spot on.",
    "Love this take! I've been exploring {topic} too and your point about {focus} resonates.",
    "Great thread on {topic}. Your insights on {focus} are really valuable.",
    "This {focus} approach to {topic} is exactly what more people need to understand.",
    "Couldn't agree more about {topic}. Your breakdown of {focus} is excellent.",
    "Really appreciate how you framed {topic} here. The {focus} angle is underrated.",
    "This is gold! More people need to see this perspective on {topic} and {focus}.",
    "Been thinking about {topic} a lot lately, and your {focus} point is really well articulated.",
]
DEFAULT_ORIGINAL_TWEET_TEMPLATES = [
    "Been diving deep into {topic} lately. The patterns I'm seeing are wild.",
    "Quick thought on {topic}: most people are missing the core fundamentals.",
    "Unpopular opinion: {topic} is way more nuanced than people realize.",
    "Just finished a deep dive into {topic}. Thread coming soon 👀",
    "The best {topic} advice I got this year: start small, iterate fast, learn constantly.",
    "Working on something related to {topic}. Can't wait to share what I'm building.",
    "Hot take: if you're not experimenting with {topic} yet, you're already behind.",
    "Three things I wish I knew about {topic} when I started...",
]
DEFAULT_SEARCH_TOPICS = ["AI automation"]
MESSAGE_LOG_PATH = Path("logs/replied.json")
MESSAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_DM_NOTICE_LOGGED = False


class SessionStats:
    """Track session statistics and enforce safety limits."""
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.replies_sent = 0
        self.likes_given = 0
        self.retweets_made = 0
        self.follows_made = 0
        self.bookmarks_made = 0
        self.quote_tweets_made = 0
        self.original_tweets_posted = 0
        self.errors_encountered = 0
        self.start_time = time.time()

        # Safety limits per hour
        self.max_actions_per_hour = 60
        self.action_timestamps: list[float] = []

    def record_action(self, action_type: str) -> bool:
        """Record an action and check if we're within safe limits."""
        now = time.time()

        # Remove actions older than 1 hour
        self.action_timestamps = [t for t in self.action_timestamps if now - t < 3600]

        # Check if we're hitting rate limits
        if len(self.action_timestamps) >= self.max_actions_per_hour:
            self.logger.warning(
                "[SAFETY] Hit action rate limit (%d actions/hour). Consider slowing down.",
                self.max_actions_per_hour
            )
            return False

        # Record the action
        self.action_timestamps.append(now)

        # Update counters
        if action_type == "reply":
            self.replies_sent += 1
        elif action_type == "like":
            self.likes_given += 1
        elif action_type == "retweet":
            self.retweets_made += 1
        elif action_type == "follow":
            self.follows_made += 1
        elif action_type == "bookmark":
            self.bookmarks_made += 1
        elif action_type == "quote_tweet":
            self.quote_tweets_made += 1
        elif action_type == "original_tweet":
            self.original_tweets_posted += 1

        return True

    def record_error(self) -> None:
        """Record an error."""
        self.errors_encountered += 1

    def get_summary(self) -> str:
        """Get a summary of session statistics."""
        runtime = time.time() - self.start_time
        runtime_hours = runtime / 3600

        return (
            f"\n=== SESSION STATISTICS ===\n"
            f"Runtime: {runtime_hours:.2f} hours\n"
            f"Replies: {self.replies_sent}\n"
            f"Likes: {self.likes_given}\n"
            f"Retweets: {self.retweets_made}\n"
            f"Follows: {self.follows_made}\n"
            f"Bookmarks: {self.bookmarks_made}\n"
            f"Quote Tweets: {self.quote_tweets_made}\n"
            f"Original Tweets: {self.original_tweets_posted}\n"
            f"Errors: {self.errors_encountered}\n"
            f"Actions/hour: {len(self.action_timestamps)}\n"
            f"========================="
        )


def ensure_auth_storage_path(auth_file: str, logger: logging.Logger) -> str:
    path = Path(auth_file).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.debug("Unable to create directory for auth file '%s': %s", path.parent, exc)
    return str(path)


@dataclass
class BotConfig:
    search_topics: list[str]
    relevant_keywords: list[str]
    spam_keywords: list[str]
    min_tweet_length: int
    min_keyword_matches: int
    max_replies_per_topic: int
    action_delay_min: int
    action_delay_max: int
    loop_delay_seconds: int
    headless: bool
    debug: bool
    x_username: Optional[str]
    x_password: Optional[str]
    referral_link: Optional[str]
    reply_templates: list[str]
    enable_dms: bool
    dm_templates: list[str]
    dm_interest_threshold: float
    dm_question_weight: float
    video_provider: str
    video_model: str
    enable_video: bool
    auth_file: str
    like_before_reply: bool
    retweet_probability: float
    link_reply_probability: float
    helpful_reply_templates: list[str]
    follow_after_reply: bool
    follow_probability: float
    bookmark_probability: float
    quote_tweet_probability: float
    post_original_probability: float
    original_tweet_templates: list[str]


def _parse_bool(value: Optional[str], *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_env(name: str) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return []
    items: list[str] = []
    for chunk in raw.replace("||", "|").split("|"):
        for piece in chunk.split(","):
            stripped = piece.strip()
            if stripped:
                items.append(stripped)
    return items


def _parse_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid value for %s -> %r. Using %s instead.", name, raw, default
        )
        return default


def _parse_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        logging.getLogger(__name__).warning(
            "Invalid value for %s -> %r. Using %s instead.", name, raw, default
        )
        return default


def load_config() -> BotConfig:
    search_topics = _split_env("SEARCH_TOPICS") or DEFAULT_SEARCH_TOPICS
    relevant_keywords = [k.lower() for k in _split_env("RELEVANT_KEYWORDS")]
    spam_keywords = [k.lower() for k in _split_env("SPAM_KEYWORDS")]

    min_tweet_length = _parse_int("MIN_TWEET_LENGTH", 40)
    min_keyword_matches = _parse_int("MIN_KEYWORD_MATCHES", 1)
    max_replies_per_topic = _parse_int("MAX_REPLIES_PER_TOPIC", 3)
    action_delay_min = _parse_int("ACTION_DELAY_MIN_SECONDS", 20)
    action_delay_max = _parse_int("ACTION_DELAY_MAX_SECONDS", 40)
    loop_delay_seconds = _parse_int("LOOP_DELAY_SECONDS", 120)

    if action_delay_max < action_delay_min:
        logging.getLogger(__name__).warning(
            "ACTION_DELAY_MAX_SECONDS < ACTION_DELAY_MIN_SECONDS. Aligning maximum to minimum."
        )
        action_delay_max = action_delay_min

    if loop_delay_seconds < 0:
        logging.getLogger(__name__).warning(
            "LOOP_DELAY_SECONDS was negative. Using default of 120."
        )
        loop_delay_seconds = 120

    headless = _parse_bool(os.getenv("HEADLESS"), default=True)
    debug = _parse_bool(os.getenv("DEBUG"), default=False)
    enable_dms = _parse_bool(os.getenv("ENABLE_DMS"), default=False)

    referral_link = (os.getenv("REFERRAL_LINK") or "").strip() or None
    reply_templates = _split_env("REPLY_TEMPLATES")
    if not reply_templates:
        reply_templates = DEFAULT_REPLY_TEMPLATES.copy()

    dm_templates = _split_env("DM_TEMPLATES")

    dm_interest_threshold = _parse_float("DM_INTEREST_THRESHOLD", 3.0)
    dm_question_weight = _parse_float("DM_QUESTION_WEIGHT", 0.75)

    x_username = (os.getenv("X_USERNAME") or "").strip() or None
    x_password = (os.getenv("X_PASSWORD") or "").strip() or None

    video_provider_raw = (os.getenv("VIDEO_PROVIDER") or "none").strip()
    video_provider = video_provider_raw.lower()
    video_model = (os.getenv("VIDEO_MODEL") or "").strip()
    enable_video = video_provider not in {"", "none", "disabled"}

    auth_file = (os.getenv("AUTH_FILE") or DEFAULT_AUTH_FILE).strip() or DEFAULT_AUTH_FILE

    # New engagement settings to avoid spam filters
    like_before_reply = _parse_bool(os.getenv("LIKE_BEFORE_REPLY"), default=True)
    retweet_probability = _parse_float("RETWEET_PROBABILITY", 0.15)  # 15% chance to retweet
    link_reply_probability = _parse_float("LINK_REPLY_PROBABILITY", 0.25)  # Only 25% of replies have links

    helpful_reply_templates = _split_env("HELPFUL_REPLY_TEMPLATES")
    if not helpful_reply_templates:
        helpful_reply_templates = DEFAULT_HELPFUL_REPLY_TEMPLATES.copy()

    # Advanced human-like engagement settings
    follow_after_reply = _parse_bool(os.getenv("FOLLOW_AFTER_REPLY"), default=False)
    follow_probability = _parse_float("FOLLOW_PROBABILITY", 0.30)  # 30% chance to follow
    bookmark_probability = _parse_float("BOOKMARK_PROBABILITY", 0.10)  # 10% chance to bookmark
    quote_tweet_probability = _parse_float("QUOTE_TWEET_PROBABILITY", 0.05)  # 5% chance to quote tweet
    post_original_probability = _parse_float("POST_ORIGINAL_PROBABILITY", 0.10)  # 10% chance per cycle

    original_tweet_templates = _split_env("ORIGINAL_TWEET_TEMPLATES")
    if not original_tweet_templates:
        original_tweet_templates = DEFAULT_ORIGINAL_TWEET_TEMPLATES.copy()

    return BotConfig(
        search_topics=search_topics,
        relevant_keywords=relevant_keywords,
        spam_keywords=spam_keywords,
        min_tweet_length=min_tweet_length,
        min_keyword_matches=min_keyword_matches,
        max_replies_per_topic=max_replies_per_topic,
        action_delay_min=action_delay_min,
        action_delay_max=action_delay_max,
        loop_delay_seconds=loop_delay_seconds,
        headless=headless,
        debug=debug,
        x_username=x_username,
        x_password=x_password,
        referral_link=referral_link,
        reply_templates=reply_templates,
        enable_dms=enable_dms,
        dm_templates=dm_templates,
        dm_interest_threshold=dm_interest_threshold,
        dm_question_weight=dm_question_weight,
        video_provider=video_provider,
        video_model=video_model,
        enable_video=enable_video,
        auth_file=auth_file,
        like_before_reply=like_before_reply,
        retweet_probability=retweet_probability,
        link_reply_probability=link_reply_probability,
        helpful_reply_templates=helpful_reply_templates,
        follow_after_reply=follow_after_reply,
        follow_probability=follow_probability,
        bookmark_probability=bookmark_probability,
        quote_tweet_probability=quote_tweet_probability,
        post_original_probability=post_original_probability,
        original_tweet_templates=original_tweet_templates,
    )


class MessageRegistry:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries = self._load()

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return set()
        if isinstance(data, list):
            return {str(item) for item in data if isinstance(item, str)}
        return set()

    def add(self, identifier: str) -> None:
        self._entries.add(identifier)
        self._save()

    def contains(self, identifier: str) -> bool:
        return identifier in self._entries

    def _save(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(sorted(self._entries), handle, indent=2)
        except OSError as exc:
            logging.getLogger(__name__).warning("Failed to persist registry: %s", exc)


class VideoService:
    def __init__(self, config: BotConfig) -> None:
        self.enabled = False
        self.provider = config.video_provider
        self.model = config.video_model
        self._client = None

        if not config.enable_video:
            return

        if self.provider == "replicate":
            token = (os.getenv("REPLICATE_API_TOKEN") or "").strip()
            try:
                import replicate  # type: ignore
            except ImportError:
                logging.getLogger(__name__).warning(
                    "VIDEO_PROVIDER=replicate but 'replicate' package missing. Video features disabled."
                )
                return
            if not token:
                logging.getLogger(__name__).warning(
                    "VIDEO_PROVIDER=replicate but REPLICATE_API_TOKEN missing. Video features disabled."
                )
                return
            self._client = replicate
            self.enabled = True
        elif self.provider:
            logging.getLogger(__name__).warning(
                "VIDEO_PROVIDER=%s is not supported. Video features disabled.", self.provider
            )

    def maybe_generate(self, topic: str, tweet_text: str) -> None:
        if not self.enabled:
            return
        logger = logging.getLogger(__name__)
        logger.info(
            "Video generation requested for topic '%s' using provider '%s'.",
            topic,
            self.provider,
        )
        if self._client is None:
            logger.warning("Video client unavailable. Skipping generation.")
            return
        try:
            _ = topic, tweet_text
        except Exception as exc:  # noqa: BLE001
            logger.warning("Video generation failed: %s", exc)


def is_logged_in(page: Page) -> bool:
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
            if locator.is_visible(timeout=2000):
                return True
        except PlaywrightError:
            continue

    try:
        current_url = page.url
    except PlaywrightError:
        return False
    return "x.com/home" in current_url or "twitter.com/home" in current_url


def automated_login(page: Page, config: BotConfig, logger: logging.Logger) -> bool:
    username = config.x_username
    password = config.x_password
    if not username or not password:
        return False

    logger.info("Attempting automated login with provided credentials.")
    try:
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        page.fill("input[name='text']", username)
        page.keyboard.press("Enter")
        page.wait_for_selector("input[name='password']", timeout=30000)
        page.fill("input[name='password']", password)
        page.keyboard.press("Enter")
        page.wait_for_url("**/home", timeout=60000)
        time.sleep(3)
        if is_logged_in(page):
            logger.info("Automated login succeeded.")
            return True
        logger.error("Automated X login failed to reach authenticated state.")
        return False
    except PlaywrightTimeout:
        logger.error("Automated X login timed out. Please verify credentials or log in manually once.")
        return False
    except PlaywrightError as exc:
        logger.error("Playwright error during automated login: %s", exc)
        return False


def wait_for_manual_login(
    context: BrowserContext,
    page: Page,
    logger: logging.Logger,
    auth_file: str,
    *,
    timeout_seconds: int = 600,
) -> bool:
    logger.info("[INFO] No saved session detected; please complete the login in the opened browser.")
    deadline = time.time() + timeout_seconds
    last_status_log = 0.0
    while time.time() < deadline:
        if is_logged_in(page):
            logger.info("[INFO] Login success detected; waiting before persisting session.")
            time.sleep(6)
            auth_path = ensure_auth_storage_path(auth_file, logger)
            try:
                context.storage_state(path=auth_path)
            except PlaywrightError as exc:
                logger.error("Failed to persist authentication state: %s", exc)
                return False
            logger.info("[INFO] Session saved to %s", auth_path)
            return True
        now = time.time()
        if now - last_status_log > 15:
            logger.info("[INFO] Waiting for manual login... (%d seconds remaining)", int(deadline - now))
            last_status_log = now
        time.sleep(3)
    logger.error("Timed out waiting for manual login. Please rerun and complete login promptly.")
    return False


def ensure_logged_in(
    context: BrowserContext,
    page: Page,
    config: BotConfig,
    logger: logging.Logger,
    *,
    automated_attempt: bool,
    auth_file: str,
) -> bool:
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        logger.warning("Timeout while loading home timeline during login check.")
    except PlaywrightError as exc:
        logger.warning("Error while loading home timeline: %s", exc)

    if is_logged_in(page):
        logger.info("[INFO] Session restored successfully")
        return True

    if automated_attempt and automated_login(page, config, logger):
        logger.info("[INFO] Automated login completed; waiting before saving session.")
        time.sleep(6)
        auth_path = ensure_auth_storage_path(auth_file, logger)
        try:
            context.storage_state(path=auth_path)
        except PlaywrightError as exc:
            logger.error("Failed to persist authentication state after automated login: %s", exc)
            return False
        logger.info("[INFO] Session saved to %s", auth_path)
        return True

    return wait_for_manual_login(context, page, logger, auth_file)


def load_tweets(page: Page, logger: logging.Logger) -> list[Locator]:
    try:
        page.wait_for_selector("article[data-testid='tweet']", timeout=15000)
    except PlaywrightTimeout:
        logger.info("No tweets loaded within 15 seconds.")
        return []
    except PlaywrightError as exc:
        logger.warning("Playwright error while waiting for tweets: %s", exc)
        return []
    try:
        return page.locator("article[data-testid='tweet']").all()
    except PlaywrightError as exc:
        logger.warning("Failed to collect tweet locators: %s", exc)
        return []


def extract_tweet_data(tweet: Locator) -> Optional[dict[str, str]]:
    try:
        text_locator = tweet.locator("div[data-testid='tweetText']")
        text = text_locator.inner_text().strip()
    except PlaywrightError:
        return None

    if not text:
        return None

    tweet_href = ""
    try:
        link = tweet.locator("a[href*='/status/']").first
        tweet_href = (link.get_attribute("href") or "").strip()
    except PlaywrightError:
        tweet_href = ""

    author_handle = ""
    try:
        user_link = tweet.locator("div[data-testid='User-Name'] a").first
        href = user_link.get_attribute("href")
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


def like_tweet(tweet: Locator, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    """Like a tweet to appear more human and build engagement."""
    try:
        like_button = tweet.locator("div[data-testid='like']").first
        # Check if already liked
        if like_button.count() > 0:
            like_button.click()
            time.sleep(random.uniform(0.5, 1.5))
            logger.info("[INFO] Liked tweet.")
            if stats:
                stats.record_action("like")
            return True
    except PlaywrightTimeout:
        logger.debug("Timeout while liking tweet.")
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.debug("Failed to like tweet: %s", exc)
        if stats:
            stats.record_error()
    return False


def retweet_tweet(tweet: Locator, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    """Retweet content to appear more engaged."""
    try:
        retweet_button = tweet.locator("div[data-testid='retweet']").first
        if retweet_button.count() > 0:
            retweet_button.click()
            time.sleep(random.uniform(0.5, 1.0))
            # Click the "Retweet" option in the menu
            page_context = tweet.page
            page_context.locator("div[data-testid='retweetConfirm']").first.click()
            time.sleep(random.uniform(0.5, 1.5))
            logger.info("[INFO] Retweeted content.")
            if stats:
                stats.record_action("retweet")
            return True
    except PlaywrightTimeout:
        logger.debug("Timeout while retweeting.")
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.debug("Failed to retweet: %s", exc)
        if stats:
            stats.record_error()
    return False


def follow_user(page: Page, author_handle: str, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    """Follow a user to build connections and appear more human."""
    if not author_handle:
        return False
    try:
        # Navigate to user profile
        profile_url = f"https://x.com/{author_handle}"
        page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(random.uniform(1.0, 2.0))

        # Look for follow button
        follow_button = page.locator("div[data-testid$='-follow']").first
        if follow_button.count() > 0:
            follow_button.click()
            time.sleep(random.uniform(0.5, 1.5))
            logger.info("[INFO] Followed user @%s", author_handle)
            if stats:
                stats.record_action("follow")
            return True
    except PlaywrightTimeout:
        logger.debug("Timeout while following user @%s", author_handle)
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.debug("Failed to follow user @%s: %s", author_handle, exc)
        if stats:
            stats.record_error()
    return False


def bookmark_tweet(tweet: Locator, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    """Bookmark a tweet to appear more engaged and human-like."""
    try:
        # Click the "more" menu (three dots)
        more_button = tweet.locator("div[data-testid='caret']").first
        if more_button.count() > 0:
            more_button.click()
            time.sleep(random.uniform(0.3, 0.8))

            # Click bookmark option in the menu
            page_context = tweet.page
            bookmark_option = page_context.locator("div[data-testid='Bookmark']").first
            if bookmark_option.count() > 0:
                bookmark_option.click()
                time.sleep(random.uniform(0.5, 1.0))
                logger.info("[INFO] Bookmarked tweet.")
                if stats:
                    stats.record_action("bookmark")
                return True
    except PlaywrightTimeout:
        logger.debug("Timeout while bookmarking tweet.")
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.debug("Failed to bookmark tweet: %s", exc)
        if stats:
            stats.record_error()
    return False


def quote_tweet(page: Page, tweet: Locator, message: str, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    """Quote tweet content with a comment to increase engagement variety."""
    try:
        retweet_button = tweet.locator("div[data-testid='retweet']").first
        if retweet_button.count() > 0:
            retweet_button.click()
            time.sleep(random.uniform(0.5, 1.0))

            # Click "Quote Tweet" option
            quote_option = page.locator("div[data-testid='quoteButton']").first
            if quote_option.count() > 0:
                quote_option.click()
                time.sleep(random.uniform(1.0, 2.0))

                # Type the quote message
                composer = page.locator("div[data-testid^='tweetTextarea_']").first
                composer.wait_for(timeout=10000)
                composer.click()
                page.keyboard.insert_text(message)

                # Post the quote tweet
                page.locator("div[data-testid='tweetButton']").click()
                time.sleep(random.uniform(1.5, 2.5))
                logger.info("[INFO] Quote tweeted successfully.")
                if stats:
                    stats.record_action("quote_tweet")
                return True
    except PlaywrightTimeout:
        logger.debug("Timeout while quote tweeting.")
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.debug("Failed to quote tweet: %s", exc)
        if stats:
            stats.record_error()
    return False


def post_original_tweet(page: Page, message: str, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    """Post an original tweet to build credibility and look like a real account."""
    try:
        # Navigate to home
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(2.0, 3.0))

        # Click compose tweet button
        compose_button = page.locator("a[href='/compose/post']").first
        if compose_button.count() > 0:
            compose_button.click()
        else:
            # Alternative: click the tweet box
            tweet_box = page.locator("div[data-testid='tweetTextarea_0']").first
            tweet_box.click()

        time.sleep(random.uniform(1.0, 2.0))

        # Type the tweet
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=10000)
        composer.click()
        page.keyboard.insert_text(message)

        # Post the tweet
        time.sleep(random.uniform(1.0, 2.0))
        page.locator("div[data-testid='tweetButton']").click()
        time.sleep(random.uniform(2.0, 3.0))

        logger.info("[INFO] Posted original tweet successfully.")
        if stats:
            stats.record_action("original_tweet")
        return True
    except PlaywrightTimeout:
        logger.debug("Timeout while posting original tweet.")
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.debug("Failed to post original tweet: %s", exc)
        if stats:
            stats.record_error()
    return False


def send_reply(page: Page, tweet: Locator, message: str, logger: logging.Logger, stats: Optional['SessionStats'] = None) -> bool:
    try:
        tweet.locator("div[data-testid='reply']").click()
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=10000)
        composer.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(message)
        page.locator("div[data-testid='tweetButtonInline']").click()
        time.sleep(2)
        logger.info("[INFO] Reply posted successfully.")
        if stats:
            stats.record_action("reply")
        return True
    except PlaywrightTimeout:
        logger.warning("Timeout while composing reply.")
        if stats:
            stats.record_error()
    except PlaywrightError as exc:
        logger.warning("Failed to send reply: %s", exc)
        if stats:
            stats.record_error()
    return False


def maybe_send_dm(config: BotConfig, page: Page, tweet_data: dict[str, str], logger: logging.Logger) -> None:
    del page, tweet_data  # Unused placeholders for future DM workflows.

    global _DM_NOTICE_LOGGED

    if not config.enable_dms:
        return
    if not config.dm_templates:
        if not _DM_NOTICE_LOGGED:
            logger.info(
                "DM support enabled but no DM_TEMPLATES configured. Skipping DM attempt."
            )
            _DM_NOTICE_LOGGED = True
        return

    if not _DM_NOTICE_LOGGED:
        logger.info("DM feature enabled, but automated DM workflows are not implemented in this build.")
        _DM_NOTICE_LOGGED = True


def text_focus(text: str, *, max_length: int = 80) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3]}..."


def process_tweets(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    tweets: list[Locator],
    topic: str,
    logger: logging.Logger,
    stats: Optional['SessionStats'] = None,
) -> None:
    replies = 0
    for tweet in tweets:
        try:
            if page.is_closed():
                logger.info("Page closed while processing tweets.")
                return
        except PlaywrightError:
            logger.info("Page unavailable while processing tweets.")
            return

        data = extract_tweet_data(tweet)
        if not data:
            continue

        text = data["text"].strip()
        identifier = data["url"] or data["id"]
        text_lower = text.lower()

        skip_reasons: list[str] = []

        if data["handle"] and config.x_username and data["handle"].lower() == config.x_username.lower():
            skip_reasons.append("self-tweet")

        if "rt @" in text_lower or text_lower.startswith("rt @"):
            skip_reasons.append("retweet")

        matches = sum(1 for kw in config.relevant_keywords if kw in text_lower)
        if config.relevant_keywords and matches < config.min_keyword_matches:
            skip_reasons.append("insufficient-keywords")

        if any(spam in text_lower for spam in config.spam_keywords):
            skip_reasons.append("spam-keyword")

        if len(text) < config.min_tweet_length:
            skip_reasons.append("too-short")

        if registry.contains(identifier):
            skip_reasons.append("already-replied")

        if skip_reasons:
            logger.info(
                "[INFO] Skipping tweet %s from @%s: reason=%s",
                data['id'],
                data['handle'] or 'unknown',
                ",".join(skip_reasons),
            )
            continue

        # Decide whether to retweet instead of replying (helps build credibility)
        if random.random() < config.retweet_probability:
            logger.info("[INFO] Retweeting content from @%s for topic '%s'.", data['handle'] or 'unknown', topic)
            if retweet_tweet(tweet, logger, stats):
                registry.add(identifier)
                replies += 1  # Count retweets toward the limit
                delay = random.randint(config.action_delay_min, config.action_delay_max)
                logger.info("[INFO] Sleeping for %s seconds before next action.", delay)
                time.sleep(delay)
                if replies >= config.max_replies_per_topic:
                    logger.info(
                        "[INFO] Reached MAX_REPLIES_PER_TOPIC=%s for '%s'. Moving to next topic.",
                        config.max_replies_per_topic,
                        topic,
                    )
                    return
                continue
            else:
                logger.debug("Retweet failed, will try to reply instead.")

        # Occasionally bookmark interesting tweets (makes bot look more engaged)
        if random.random() < config.bookmark_probability:
            bookmark_tweet(tweet, logger, stats)

        # Like the tweet before replying (makes bot look more human)
        if config.like_before_reply:
            like_tweet(tweet, logger, stats)

        # Occasionally quote tweet instead of regular reply (adds variety)
        if random.random() < config.quote_tweet_probability:
            # Use helpful template for quote tweets (less promotional)
            template = random.choice(config.helpful_reply_templates)
            quote_message = template.format(
                topic=topic,
                focus=text_focus(data["text"]),
            ).strip()
            if quote_message and quote_tweet(page, tweet, quote_message, logger, stats):
                registry.add(identifier)
                replies += 1
                # Optionally follow the author after quote tweeting
                if config.follow_after_reply and random.random() < config.follow_probability:
                    follow_user(page, data["handle"], logger, stats)
                delay = random.randint(config.action_delay_min, config.action_delay_max)
                logger.info("[INFO] Sleeping for %s seconds before next action.", delay)
                time.sleep(delay)
                if replies >= config.max_replies_per_topic:
                    logger.info(
                        "[INFO] Reached MAX_REPLIES_PER_TOPIC=%s for '%s'. Moving to next topic.",
                        config.max_replies_per_topic,
                        topic,
                    )
                    return
                continue

        # Decide between helpful (no link) and promotional (with link) reply
        use_promotional = random.random() < config.link_reply_probability

        if use_promotional and config.referral_link:
            # Use promotional template with link
            template = random.choice(config.reply_templates)
            message = template.format(
                topic=topic,
                focus=text_focus(data["text"]),
                ref_link=config.referral_link,
            ).strip()
            logger.info("[INFO] Sending promotional reply to @%s for topic '%s'.", data['handle'] or 'unknown', topic)
        else:
            # Use helpful template without link
            template = random.choice(config.helpful_reply_templates)
            message = template.format(
                topic=topic,
                focus=text_focus(data["text"]),
            ).strip()
            logger.info("[INFO] Sending helpful reply to @%s for topic '%s'.", data['handle'] or 'unknown', topic)

        if not message:
            logger.warning("Generated empty reply. Skipping tweet.")
            continue

        if send_reply(page, tweet, message, logger, stats):
            registry.add(identifier)
            replies += 1

            # Follow the author after replying (if enabled and probability triggers)
            if config.follow_after_reply and random.random() < config.follow_probability:
                follow_user(page, data["handle"], logger, stats)

            if use_promotional:
                video_service.maybe_generate(topic, data["text"])
            maybe_send_dm(config, page, data, logger)
            delay = random.randint(config.action_delay_min, config.action_delay_max)
            logger.info("[INFO] Sleeping for %s seconds before next action.", delay)
            time.sleep(delay)
        else:
            logger.warning("Reply attempt failed; not recording tweet as replied.")

        if replies >= config.max_replies_per_topic:
            logger.info(
                "[INFO] Reached MAX_REPLIES_PER_TOPIC=%s for '%s'. Moving to next topic.",
                config.max_replies_per_topic,
                topic,
            )
            return


def handle_topic(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    topic: str,
    logger: logging.Logger,
    stats: Optional['SessionStats'] = None,
) -> None:
    logger.info("[INFO] Topic '%s' - loading search results...", topic)
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        logger.debug("Page loaded, waiting for tweets to render...")
        page.wait_for_timeout(3000)  # Give tweets time to render
    except PlaywrightTimeout:
        logger.warning("Timeout while loading topic '%s'.", topic)
        return
    except PlaywrightError as exc:
        logger.warning("Error while loading topic '%s': %s", topic, exc)
        return

    tweets = load_tweets(page, logger)
    logger.info("[INFO] Loaded %s tweets for topic '%s'.", len(tweets), topic)
    if not tweets:
        logger.warning("No eligible tweets for topic '%s'.", topic)
        return

    process_tweets(config, registry, page, video_service, tweets, topic, logger, stats)


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    logger: logging.Logger,
) -> None:
    logger.info("[INFO] Starting engagement loop with %s topic(s).", len(config.search_topics))

    # Create session statistics tracker
    stats = SessionStats(logger)
    cycle_count = 0

    while True:
        try:
            if page.is_closed():
                logger.info("Browser page closed. Exiting engagement loop.")
                logger.info(stats.get_summary())
                return
        except PlaywrightError:
            logger.info("Browser page unavailable. Exiting engagement loop.")
            logger.info(stats.get_summary())
            return

        cycle_count += 1

        # Occasionally post an original tweet to build credibility (at start of cycle)
        if config.original_tweet_templates and random.random() < config.post_original_probability:
            if config.search_topics:
                # Pick a random topic to tweet about
                topic = random.choice(config.search_topics)
                template = random.choice(config.original_tweet_templates)
                original_message = template.format(topic=topic).strip()
                if original_message:
                    logger.info("[INFO] Attempting to post original tweet about '%s'.", topic)
                    post_original_tweet(page, original_message, logger, stats)
                    # Wait a bit after posting original content
                    delay = random.randint(config.action_delay_min, config.action_delay_max)
                    logger.info("[INFO] Sleeping for %s seconds after original tweet.", delay)
                    time.sleep(delay)

        if config.search_topics:
            for topic in config.search_topics:
                handle_topic(config, registry, page, video_service, topic, logger, stats)
        else:
            logger.info("No search topics configured. Sleeping before next cycle.")

        # Print statistics summary every 5 cycles
        if cycle_count % 5 == 0:
            logger.info(stats.get_summary())

        logger.info("[INFO] Cycle complete. Sleeping for %s seconds.", config.loop_delay_seconds)
        try:
            time.sleep(config.loop_delay_seconds)
        except KeyboardInterrupt:
            logger.info(stats.get_summary())
            raise


def close_resources(
    browser: Optional[Browser],
    context: Optional[BrowserContext],
    logger: logging.Logger,
) -> None:
    try:
        if context:
            context.close()
    except PlaywrightError as exc:
        logger.debug("Error while closing context: %s", exc)
    try:
        if browser:
            browser.close()
    except PlaywrightError as exc:
        logger.debug("Error while closing browser: %s", exc)


def prepare_authenticated_session(
    playwright,
    config: BotConfig,
    logger: logging.Logger,
) -> Optional[tuple[Browser, BrowserContext, Page]]:
    storage_env = (os.getenv("AUTH_FILE") or config.auth_file).strip() or config.auth_file
    auth_path = ensure_auth_storage_path(storage_env, logger)

    try:
        browser = playwright.chromium.launch(
            headless=config.headless,
            args=["--start-maximized", "--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
    except PlaywrightError as exc:
        logger.error("Failed to launch browser: %s", exc)
        return None

    storage_file = auth_path
    context: BrowserContext
    session_loaded = False

    storage_exists = os.path.exists(storage_file)
    if storage_exists:
        logger.info("[INFO] Restoring saved session from %s", storage_file)
        try:
            context = browser.new_context(storage_state=storage_file)
            session_loaded = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("[WARN] auth.json missing or invalid — regenerating login session")
            logger.debug("Storage state recovery error: %s", exc)
            context = browser.new_context()
            session_loaded = False
    else:
        logger.info("[INFO] No session found — creating new context for manual login.")
        context = browser.new_context()

    page = context.new_page()

    if session_loaded:
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        except PlaywrightTimeout:
            logger.warning("Timeout while verifying restored session; prompting login.")
        except (PlaywrightError, TargetClosedError) as exc:
            logger.warning("Error while verifying restored session: %s", exc)
        else:
            if is_logged_in(page):
                logger.info("[INFO] Session restored successfully")
                try:
                    context.storage_state(path=storage_file)
                except PlaywrightError as exc:
                    logger.debug("Unable to refresh storage state: %s", exc)
                return browser, context, page
            logger.warning("Saved session present but user is logged out; manual login required.")

    try:
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        logger.warning("Timeout while opening login page. Proceeding to login checks.")
    except PlaywrightError as exc:
        logger.error("Failed to load login page: %s", exc)

    if not ensure_logged_in(
        context,
        page,
        config,
        logger,
        automated_attempt=True,
        auth_file=storage_file,
    ):
        logger.error("Login process did not complete successfully.")
        close_resources(browser, context, logger)
        return None

    logger.info("[INFO] Authentication complete; proceeding to engagement loop.")
    return browser, context, page


def run_social_agent() -> None:
    load_dotenv()
    config = load_config()

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("social_agent")

    logger.info("Search topics configured: %s", ", ".join(config.search_topics))
    logger.info("HEADLESS=%s, DEBUG=%s", config.headless, config.debug)
    if config.enable_dms:
        logger.info("ENABLE_DMS=true")

    registry = MessageRegistry(MESSAGE_LOG_PATH)
    video_service = VideoService(config)

    max_attempts = 3
    attempt = 0
    while attempt < max_attempts:
        try:
            with sync_playwright() as playwright:
                browser: Optional[Browser] = None
                context: Optional[BrowserContext] = None
                page: Optional[Page] = None

                try:
                    session = prepare_authenticated_session(playwright, config, logger)
                    if not session:
                        logger.error("Unable to establish an authenticated session. Exiting run.")
                        return

                    browser, context, page = session
                    if not page:
                        logger.error("Browser page unavailable. Exiting run.")
                        return

                    logger.info("[INFO] Session ready; entering engagement workflow.")
                    run_engagement_loop(config, registry, page, video_service, logger)
                    return
                finally:
                    close_resources(browser, context, logger)
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user.")
            raise
        except (PlaywrightTimeout, TargetClosedError) as exc:
            attempt += 1
            logger.warning("[WARN] Retrying after connection loss… (%s/%s)", attempt, max_attempts)
            if attempt >= max_attempts:
                logger.error("Maximum retry attempts reached after connection issues: %s", exc)
                break
            time.sleep(5)
            continue
        except PlaywrightError as exc:
            logger.error("Playwright error: %s", exc)
            if config.debug:
                logger.exception("Detailed Playwright exception")
            break
        except Exception as exc:  # noqa: BLE001
            logger.error("Unhandled exception: %s", exc)
            if config.debug:
                logger.exception("Unhandled exception")
            break



if __name__ == "__main__":
    try:
        run_social_agent()
    except KeyboardInterrupt:
        logging.getLogger("social_agent").info("Shutdown requested by user.")
        sys.exit(0)
