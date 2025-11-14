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
DEFAULT_SEARCH_TOPICS = ["AI automation"]
MESSAGE_LOG_PATH = Path("logs/replied.json")
MESSAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
FOLLOW_TRACKER_PATH = Path("logs/follows.json")
FOLLOW_TRACKER_PATH.parent.mkdir(parents=True, exist_ok=True)
_DM_NOTICE_LOGGED = False


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
    # Follow/Unfollow settings
    enable_auto_follow: bool
    enable_auto_unfollow: bool
    max_follows_per_hour: int
    max_unfollows_per_hour: int
    unfollow_after_hours: int
    follow_delay_min: int
    follow_delay_max: int
    max_daily_follows: int
    max_daily_unfollows: int
    target_follow_ratio: float
    min_follower_count_to_follow: int
    max_following_count_to_follow: int


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
    load_dotenv()  # Load environment variables from .env file
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

    # Follow/Unfollow settings
    enable_auto_follow = _parse_bool(os.getenv("ENABLE_AUTO_FOLLOW"), default=False)
    enable_auto_unfollow = _parse_bool(os.getenv("ENABLE_AUTO_UNFOLLOW"), default=False)
    max_follows_per_hour = _parse_int("MAX_FOLLOWS_PER_HOUR", 5)
    max_unfollows_per_hour = _parse_int("MAX_UNFOLLOWS_PER_HOUR", 10)
    unfollow_after_hours = _parse_int("UNFOLLOW_AFTER_HOURS", 24)
    follow_delay_min = _parse_int("FOLLOW_DELAY_MIN_SECONDS", 30)
    follow_delay_max = _parse_int("FOLLOW_DELAY_MAX_SECONDS", 90)
    max_daily_follows = _parse_int("MAX_DAILY_FOLLOWS", 50)
    max_daily_unfollows = _parse_int("MAX_DAILY_UNFOLLOWS", 100)
    target_follow_ratio = _parse_float("TARGET_FOLLOW_RATIO", 1.2)
    min_follower_count_to_follow = _parse_int("MIN_FOLLOWER_COUNT_TO_FOLLOW", 10)
    max_following_count_to_follow = _parse_int("MAX_FOLLOWING_COUNT_TO_FOLLOW", 10000)

    if follow_delay_max < follow_delay_min:
        logging.getLogger(__name__).warning(
            "FOLLOW_DELAY_MAX_SECONDS < FOLLOW_DELAY_MIN_SECONDS. Aligning maximum to minimum."
        )
        follow_delay_max = follow_delay_min

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
        enable_auto_follow=enable_auto_follow,
        enable_auto_unfollow=enable_auto_unfollow,
        max_follows_per_hour=max_follows_per_hour,
        max_unfollows_per_hour=max_unfollows_per_hour,
        unfollow_after_hours=unfollow_after_hours,
        follow_delay_min=follow_delay_min,
        follow_delay_max=follow_delay_max,
        max_daily_follows=max_daily_follows,
        max_daily_unfollows=max_daily_unfollows,
        target_follow_ratio=target_follow_ratio,
        min_follower_count_to_follow=min_follower_count_to_follow,
        max_following_count_to_follow=max_following_count_to_follow,
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


class FollowTracker:
    """Tracks follows, unfollows, and follow-backs with timestamps."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {
                "following": {},  # {handle: {"followed_at": timestamp, "followed_back": bool}}
                "daily_stats": {},  # {date: {"follows": count, "unfollows": count}}
                "hourly_stats": {},  # {hour_key: {"follows": count, "unfollows": count}}
            }
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                # Ensure all keys exist
                if "following" not in data:
                    data["following"] = {}
                if "daily_stats" not in data:
                    data["daily_stats"] = {}
                if "hourly_stats" not in data:
                    data["hourly_stats"] = {}
                return data
        except (OSError, json.JSONDecodeError):
            return {
                "following": {},
                "daily_stats": {},
                "hourly_stats": {},
            }

    def _save(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2)
        except OSError as exc:
            logging.getLogger(__name__).warning("Failed to persist follow tracker: %s", exc)

    def add_follow(self, handle: str) -> None:
        """Record that we followed a user."""
        now = time.time()
        self._data["following"][handle] = {
            "followed_at": now,
            "followed_back": False,
        }

        # Update daily stats
        date_key = time.strftime("%Y-%m-%d", time.localtime(now))
        if date_key not in self._data["daily_stats"]:
            self._data["daily_stats"][date_key] = {"follows": 0, "unfollows": 0}
        self._data["daily_stats"][date_key]["follows"] += 1

        # Update hourly stats
        hour_key = time.strftime("%Y-%m-%d-%H", time.localtime(now))
        if hour_key not in self._data["hourly_stats"]:
            self._data["hourly_stats"][hour_key] = {"follows": 0, "unfollows": 0}
        self._data["hourly_stats"][hour_key]["follows"] += 1

        self._save()

    def add_unfollow(self, handle: str) -> None:
        """Record that we unfollowed a user."""
        if handle in self._data["following"]:
            del self._data["following"][handle]

        now = time.time()

        # Update daily stats
        date_key = time.strftime("%Y-%m-%d", time.localtime(now))
        if date_key not in self._data["daily_stats"]:
            self._data["daily_stats"][date_key] = {"follows": 0, "unfollows": 0}
        self._data["daily_stats"][date_key]["unfollows"] += 1

        # Update hourly stats
        hour_key = time.strftime("%Y-%m-%d-%H", time.localtime(now))
        if hour_key not in self._data["hourly_stats"]:
            self._data["hourly_stats"][hour_key] = {"follows": 0, "unfollows": 0}
        self._data["hourly_stats"][hour_key]["unfollows"] += 1

        self._save()

    def mark_followed_back(self, handle: str) -> None:
        """Mark that a user followed us back."""
        if handle in self._data["following"]:
            self._data["following"][handle]["followed_back"] = True
            self._save()

    def is_following(self, handle: str) -> bool:
        """Check if we're currently following a user."""
        return handle in self._data["following"]

    def get_users_to_unfollow(self, hours_threshold: int) -> list[str]:
        """Get list of users who haven't followed back within the threshold."""
        now = time.time()
        threshold_seconds = hours_threshold * 3600
        users_to_unfollow = []

        for handle, info in self._data["following"].items():
            if info["followed_back"]:
                continue

            time_since_follow = now - info["followed_at"]
            if time_since_follow >= threshold_seconds:
                users_to_unfollow.append(handle)

        return users_to_unfollow

    def get_follows_today(self) -> int:
        """Get number of follows performed today."""
        date_key = time.strftime("%Y-%m-%d")
        return self._data["daily_stats"].get(date_key, {}).get("follows", 0)

    def get_unfollows_today(self) -> int:
        """Get number of unfollows performed today."""
        date_key = time.strftime("%Y-%m-%d")
        return self._data["daily_stats"].get(date_key, {}).get("unfollows", 0)

    def get_follows_this_hour(self) -> int:
        """Get number of follows performed this hour."""
        hour_key = time.strftime("%Y-%m-%d-%H")
        return self._data["hourly_stats"].get(hour_key, {}).get("follows", 0)

    def get_unfollows_this_hour(self) -> int:
        """Get number of unfollows performed this hour."""
        hour_key = time.strftime("%Y-%m-%d-%H")
        return self._data["hourly_stats"].get(hour_key, {}).get("unfollows", 0)

    def cleanup_old_stats(self, days_to_keep: int = 30) -> None:
        """Remove stats older than specified days."""
        cutoff = time.time() - (days_to_keep * 86400)
        cutoff_date = time.strftime("%Y-%m-%d", time.localtime(cutoff))

        # Clean daily stats
        keys_to_remove = [k for k in self._data["daily_stats"].keys() if k < cutoff_date]
        for key in keys_to_remove:
            del self._data["daily_stats"][key]

        # Clean hourly stats
        cutoff_hour = time.strftime("%Y-%m-%d-%H", time.localtime(cutoff))
        keys_to_remove = [k for k in self._data["hourly_stats"].keys() if k < cutoff_hour]
        for key in keys_to_remove:
            del self._data["hourly_stats"][key]

        if keys_to_remove:
            self._save()


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


def send_reply(page: Page, tweet: Locator, message: str, logger: logging.Logger) -> bool:
    try:
        # Scroll tweet into view first
        tweet.scroll_into_view_if_needed()
        time.sleep(random.uniform(0.5, 1.0))

        tweet.locator("div[data-testid='reply']").click(timeout=60000)  # 60 second timeout
        time.sleep(random.uniform(1.5, 3.0))  # Human-like delay after clicking reply

        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=60000)  # Increased timeout to 60 seconds

        time.sleep(random.uniform(0.5, 1.5))  # Pause before clicking
        composer.click(timeout=60000)  # 60 second timeout

        time.sleep(random.uniform(0.3, 0.8))  # Pause before typing
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")

        # Type message with slight delay to look more human
        page.keyboard.insert_text(message)
        time.sleep(random.uniform(1.0, 2.5))  # Pause before clicking tweet

        page.locator("div[data-testid='tweetButtonInline']").click(timeout=60000)
        time.sleep(random.uniform(2.5, 4.0))  # Wait for tweet to post

        logger.info("[INFO] Reply posted successfully.")
        return True
    except PlaywrightTimeout as exc:
        logger.warning("Timeout while composing reply: %s", exc)
    except PlaywrightError as exc:
        logger.warning("Failed to send reply: %s", exc)
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


def get_account_stats(page: Page, logger: logging.Logger) -> Optional[dict[str, int]]:
    """Get current follower and following counts."""
    try:
        # Navigate to profile to get stats
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Try to find profile link and click it
        profile_link = page.locator("a[aria-label='Profile']").first
        if not profile_link.is_visible():
            logger.warning("Profile link not visible")
            return None

        profile_link.click()
        time.sleep(3)

        # Extract follower/following counts
        followers = 0
        following = 0

        # Look for links containing "followers" and "following"
        stats_links = page.locator("a[href*='/verified_followers'], a[href*='/followers'], a[href*='/following']").all()

        for link in stats_links:
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()

                if "following" in href.lower():
                    # Extract number from text like "123 Following"
                    parts = text.split()
                    if parts:
                        following = int(parts[0].replace(",", ""))
                elif "followers" in href.lower():
                    # Extract number from text like "456 Followers"
                    parts = text.split()
                    if parts:
                        followers = int(parts[0].replace(",", ""))
            except (ValueError, IndexError, PlaywrightError):
                continue

        return {"followers": followers, "following": following}
    except PlaywrightError as exc:
        logger.warning("Failed to get account stats: %s", exc)
        return None


def follow_user(page: Page, handle: str, logger: logging.Logger) -> bool:
    """Follow a user by their handle."""
    try:
        # Navigate to user's profile
        url = f"https://x.com/{handle}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Look for the Follow button
        follow_button = page.locator("div[data-testid*='follow']").first
        if not follow_button.is_visible(timeout=5000):
            logger.warning("Follow button not found for @%s", handle)
            return False

        button_text = follow_button.inner_text().strip().lower()
        if "following" in button_text or "unfollow" in button_text:
            logger.info("Already following @%s", handle)
            return False

        follow_button.click()
        time.sleep(2)
        logger.info("Successfully followed @%s", handle)
        return True
    except PlaywrightTimeout:
        logger.warning("Timeout while trying to follow @%s", handle)
    except PlaywrightError as exc:
        logger.warning("Failed to follow @%s: %s", handle, exc)
    return False


def unfollow_user(page: Page, handle: str, logger: logging.Logger) -> bool:
    """Unfollow a user by their handle."""
    try:
        # Navigate to user's profile
        url = f"https://x.com/{handle}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Look for the Following button
        following_button = page.locator("div[data-testid*='follow']").first
        if not following_button.is_visible(timeout=5000):
            logger.warning("Following button not found for @%s", handle)
            return False

        button_text = following_button.inner_text().strip().lower()
        if "follow" in button_text and "following" not in button_text:
            logger.info("Not following @%s, skipping unfollow", handle)
            return False

        following_button.click()
        time.sleep(1)

        # Confirm unfollow in the dialog
        try:
            unfollow_confirm = page.locator("div[data-testid='confirmationSheetConfirm']").first
            if unfollow_confirm.is_visible(timeout=3000):
                unfollow_confirm.click()
                time.sleep(2)
                logger.info("Successfully unfollowed @%s", handle)
                return True
        except PlaywrightTimeout:
            logger.warning("Unfollow confirmation dialog not found for @%s", handle)
            return False

    except PlaywrightTimeout:
        logger.warning("Timeout while trying to unfollow @%s", handle)
    except PlaywrightError as exc:
        logger.warning("Failed to unfollow @%s: %s", handle, exc)
    return False


def check_if_following_back(page: Page, handle: str, logger: logging.Logger) -> bool:
    """Check if a user is following us back."""
    try:
        # Navigate to user's profile
        url = f"https://x.com/{handle}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Look for "Follows you" indicator
        follows_you_locator = page.locator("span:has-text('Follows you')")
        if follows_you_locator.is_visible(timeout=3000):
            logger.info("@%s is following back", handle)
            return True

        logger.info("@%s is not following back", handle)
        return False
    except PlaywrightTimeout:
        logger.debug("Timeout checking if @%s follows back", handle)
    except PlaywrightError as exc:
        logger.debug("Failed to check if @%s follows back: %s", handle, exc)
    return False


def extract_handles_from_tweets(tweets: list[Locator], logger: logging.Logger) -> list[str]:
    """Extract unique user handles from a list of tweet locators."""
    handles = []
    seen = set()

    for tweet in tweets:
        try:
            user_link = tweet.locator("div[data-testid='User-Name'] a").first
            href = user_link.get_attribute("href")
            if href:
                handle = href.rstrip("/").split("/")[-1]
                if handle and handle not in seen:
                    handles.append(handle)
                    seen.add(handle)
        except PlaywrightError:
            continue

    return handles


def should_follow_user(
    page: Page,
    handle: str,
    config: BotConfig,
    logger: logging.Logger,
) -> bool:
    """Determine if we should follow a user based on their profile."""
    try:
        # Navigate to user's profile
        url = f"https://x.com/{handle}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Check if already following
        follow_button = page.locator("div[data-testid*='follow']").first
        if follow_button.is_visible(timeout=3000):
            button_text = follow_button.inner_text().strip().lower()
            if "following" in button_text or "unfollow" in button_text:
                logger.debug("Already following @%s", handle)
                return False

        # Extract follower/following counts from profile
        stats_links = page.locator("a[href*='/verified_followers'], a[href*='/followers'], a[href*='/following']").all()

        followers = 0
        following = 0

        for link in stats_links:
            try:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()

                if "following" in href.lower():
                    parts = text.split()
                    if parts:
                        following = int(parts[0].replace(",", ""))
                elif "followers" in href.lower():
                    parts = text.split()
                    if parts:
                        followers = int(parts[0].replace(",", ""))
            except (ValueError, IndexError, PlaywrightError):
                continue

        # Apply follower count filters
        if followers < config.min_follower_count_to_follow:
            logger.debug("@%s has too few followers (%d)", handle, followers)
            return False

        if following > config.max_following_count_to_follow:
            logger.debug("@%s is following too many (%d)", handle, following)
            return False

        # Check if account seems spammy (following way more than followers)
        if followers > 0 and following / followers > 10:
            logger.debug("@%s has suspicious follow ratio", handle)
            return False

        logger.info("@%s passed follow criteria (followers: %d, following: %d)", handle, followers, following)
        return True

    except PlaywrightTimeout:
        logger.debug("Timeout while checking @%s profile", handle)
    except PlaywrightError as exc:
        logger.debug("Failed to check @%s profile: %s", handle, exc)
    return False


def process_tweets(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    tweets: list[Locator],
    topic: str,
    logger: logging.Logger,
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

        template = random.choice(config.reply_templates)
        message = template.format(
            topic=topic,
            focus=text_focus(data["text"]),
            ref_link=config.referral_link or "",
        ).strip()

        if not message:
            logger.warning("Generated empty reply. Skipping tweet.")
            continue

        logger.info("[INFO] Replying to @%s for topic '%s'.", data['handle'] or 'unknown', topic)

        if send_reply(page, tweet, message, logger):
            registry.add(identifier)
            replies += 1
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
) -> None:
    logger.info("[INFO] Topic '%s' - loading search results...", topic)
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3.0, 5.0))  # Wait for dynamic content to load
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

    process_tweets(config, registry, page, video_service, tweets, topic, logger)


def run_unfollow_cycle(
    config: BotConfig,
    follow_tracker: FollowTracker,
    page: Page,
    logger: logging.Logger,
) -> None:
    """Unfollow users who haven't followed back within the threshold."""
    if not config.enable_auto_unfollow:
        return

    logger.info("[INFO] Starting unfollow cycle...")

    # Check limits
    unfollows_today = follow_tracker.get_unfollows_today()
    unfollows_this_hour = follow_tracker.get_unfollows_this_hour()

    if unfollows_today >= config.max_daily_unfollows:
        logger.info("Reached daily unfollow limit (%d/%d)", unfollows_today, config.max_daily_unfollows)
        return

    if unfollows_this_hour >= config.max_unfollows_per_hour:
        logger.info("Reached hourly unfollow limit (%d/%d)", unfollows_this_hour, config.max_unfollows_per_hour)
        return

    # Get users to unfollow
    users_to_unfollow = follow_tracker.get_users_to_unfollow(config.unfollow_after_hours)

    if not users_to_unfollow:
        logger.info("No users to unfollow at this time")
        return

    logger.info("Found %d users to potentially unfollow", len(users_to_unfollow))

    unfollowed_count = 0
    for handle in users_to_unfollow:
        # Check if we've hit limits
        if follow_tracker.get_unfollows_today() >= config.max_daily_unfollows:
            logger.info("Reached daily unfollow limit during cycle")
            break

        if follow_tracker.get_unfollows_this_hour() >= config.max_unfollows_per_hour:
            logger.info("Reached hourly unfollow limit during cycle")
            break

        # Check page status
        try:
            if page.is_closed():
                logger.info("Page closed during unfollow cycle")
                return
        except PlaywrightError:
            logger.info("Page unavailable during unfollow cycle")
            return

        # Double-check if they followed back before unfollowing
        if check_if_following_back(page, handle, logger):
            logger.info("@%s followed back, marking and skipping unfollow", handle)
            follow_tracker.mark_followed_back(handle)
            continue

        # Unfollow the user
        if unfollow_user(page, handle, logger):
            follow_tracker.add_unfollow(handle)
            unfollowed_count += 1

            # Random delay to look more human
            delay = random.randint(config.follow_delay_min, config.follow_delay_max)
            logger.info("Sleeping for %d seconds before next unfollow", delay)
            time.sleep(delay)

    logger.info("Unfollow cycle complete. Unfollowed %d users", unfollowed_count)


def run_follow_cycle(
    config: BotConfig,
    follow_tracker: FollowTracker,
    page: Page,
    topic: str,
    logger: logging.Logger,
) -> None:
    """Follow relevant users from search results."""
    if not config.enable_auto_follow:
        return

    logger.info("[INFO] Starting follow cycle for topic '%s'...", topic)

    # Check limits
    follows_today = follow_tracker.get_follows_today()
    follows_this_hour = follow_tracker.get_follows_this_hour()

    if follows_today >= config.max_daily_follows:
        logger.info("Reached daily follow limit (%d/%d)", follows_today, config.max_daily_follows)
        return

    if follows_this_hour >= config.max_follows_per_hour:
        logger.info("Reached hourly follow limit (%d/%d)", follows_this_hour, config.max_follows_per_hour)
        return

    # Check account health - don't follow if ratio is too high
    stats = get_account_stats(page, logger)
    if stats:
        followers = stats.get("followers", 0)
        following = stats.get("following", 0)

        if followers > 0:
            current_ratio = following / followers
            if current_ratio > config.target_follow_ratio:
                logger.info(
                    "Current follow ratio (%.2f) exceeds target (%.2f). Skipping follows.",
                    current_ratio,
                    config.target_follow_ratio,
                )
                return

        logger.info("Account stats - Followers: %d, Following: %d", followers, following)

    # Load tweets from topic search
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(random.uniform(3.0, 5.0))  # Wait for dynamic content to load
    except PlaywrightTimeout:
        logger.warning("Timeout while loading topic '%s' for follow cycle", topic)
        return
    except PlaywrightError as exc:
        logger.warning("Error while loading topic '%s' for follow cycle: %s", topic, exc)
        return

    tweets = load_tweets(page, logger)
    if not tweets:
        logger.info("No tweets found for follow cycle")
        return

    # Extract handles from tweets
    handles = extract_handles_from_tweets(tweets, logger)
    logger.info("Found %d unique handles in search results", len(handles))

    followed_count = 0
    for handle in handles:
        # Check if we've hit limits
        if follow_tracker.get_follows_today() >= config.max_daily_follows:
            logger.info("Reached daily follow limit during cycle")
            break

        if follow_tracker.get_follows_this_hour() >= config.max_follows_per_hour:
            logger.info("Reached hourly follow limit during cycle")
            break

        # Check page status
        try:
            if page.is_closed():
                logger.info("Page closed during follow cycle")
                return
        except PlaywrightError:
            logger.info("Page unavailable during follow cycle")
            return

        # Skip if already following
        if follow_tracker.is_following(handle):
            logger.debug("Already tracking @%s, skipping", handle)
            continue

        # Skip our own account
        if config.x_username and handle.lower() == config.x_username.lower():
            continue

        # Check if user meets criteria
        if not should_follow_user(page, handle, config, logger):
            continue

        # Follow the user
        if follow_user(page, handle, logger):
            follow_tracker.add_follow(handle)
            followed_count += 1

            # Random delay to look more human
            delay = random.randint(config.follow_delay_min, config.follow_delay_max)
            logger.info("Sleeping for %d seconds before next follow", delay)
            time.sleep(delay)

    logger.info("Follow cycle complete. Followed %d users", followed_count)


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    follow_tracker: FollowTracker,
    logger: logging.Logger,
) -> None:
    logger.info("[INFO] Starting engagement loop with %s topic(s).", len(config.search_topics))

    # Log follow/unfollow settings
    if config.enable_auto_follow:
        logger.info("[INFO] Auto-follow enabled (max %d/hour, %d/day)", config.max_follows_per_hour, config.max_daily_follows)
    if config.enable_auto_unfollow:
        logger.info("[INFO] Auto-unfollow enabled (unfollow after %d hours, max %d/hour, %d/day)",
                   config.unfollow_after_hours, config.max_unfollows_per_hour, config.max_daily_unfollows)

    cycle_count = 0
    while True:
        try:
            if page.is_closed():
                logger.info("Browser page closed. Exiting engagement loop.")
                return
        except PlaywrightError:
            logger.info("Browser page unavailable. Exiting engagement loop.")
            return

        cycle_count += 1
        logger.info("[INFO] Starting cycle #%d", cycle_count)

        # Run unfollow cycle first (to make room for new follows)
        if config.enable_auto_unfollow:
            try:
                run_unfollow_cycle(config, follow_tracker, page, logger)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error during unfollow cycle: %s", exc)
                if config.debug:
                    logger.exception("Unfollow cycle exception")

        # Cleanup old stats periodically (every 10 cycles)
        if cycle_count % 10 == 0:
            follow_tracker.cleanup_old_stats()

        # Process topics for engagement and follows
        if config.search_topics:
            for topic in config.search_topics:
                # Handle engagement (replies)
                handle_topic(config, registry, page, video_service, topic, logger)

                # Run follow cycle for this topic
                if config.enable_auto_follow:
                    try:
                        run_follow_cycle(config, follow_tracker, page, topic, logger)
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Error during follow cycle for topic '%s': %s", topic, exc)
                        if config.debug:
                            logger.exception("Follow cycle exception")
        else:
            logger.info("No search topics configured. Sleeping before next cycle.")

        logger.info("[INFO] Cycle complete. Sleeping for %s seconds.", config.loop_delay_seconds)
        try:
            time.sleep(config.loop_delay_seconds)
        except KeyboardInterrupt:
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
        user_data_dir = str(Path.home() / ".social_agent_codex/browser_session/")
        os.makedirs(user_data_dir, exist_ok=True)
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=config.headless,
            channel="chrome",
            args=["--start-maximized", "--no-sandbox"],
        )
    except PlaywrightError as exc:
        logger.error("Failed to launch browser: %s", exc)
        return None

    storage_file = auth_path
    session_loaded = False

    storage_exists = os.path.exists(storage_file)
    if storage_exists:
        logger.info("[INFO] Saved session file exists at %s (persistent context already includes session data)", storage_file)
        session_loaded = True
    else:
        logger.info("[INFO] No session found — creating new context for manual login.")

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
                return context, context, page
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
        close_resources(context, context, logger)
        return None

    logger.info("[INFO] Authentication complete; proceeding to engagement loop.")
    return context, context, page


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
    follow_tracker = FollowTracker(FOLLOW_TRACKER_PATH)

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
                    run_engagement_loop(config, registry, page, video_service, follow_tracker, logger)
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
