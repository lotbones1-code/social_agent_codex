#!/usr/bin/env python3
"""Sync Playwright social agent with persistent X session handling."""

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  🚨 CRITICAL WARNING - READ BEFORE MAKING ANY CHANGES 🚨                  ║
# ╠═══════════════════════════════════════════════════════════════════════════╣
# ║                                                                           ║
# ║  This is a PRODUCTION bot generating REAL revenue.                        ║
# ║  NEVER delete or disable existing features without explicit approval.     ║
# ║                                                                           ║
# ║  📋 BEFORE CHANGING CODE: Read FEATURES_MANIFEST.md                       ║
# ║                                                                           ║
# ║  ✅ YOUR JOB: ADD features, NEVER remove them                             ║
# ║  ❌ NEVER DELETE:                                                         ║
# ║     - generate_ai_reply() function (OpenAI integration)                   ║
# ║     - import requests (required for AI replies)                           ║
# ║     - MessageRegistry class (deduplication)                               ║
# ║     - Template system & placeholders                                      ║
# ║     - Authentication/session code                                         ║
# ║     - Tweet filtering pipeline                                            ║
# ║     - Video/DM frameworks                                                 ║
# ║                                                                           ║
# ║  If you think code is "unused" - IT'S NOT. Everything has a purpose.      ║
# ║  If you want to "simplify" - DON'T. Complexity = features = revenue.      ║
# ║                                                                           ║
# ║  Questions? Ask user first. Don't assume you know better.                 ║
# ║                                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

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

import requests  # CRITICAL: DO NOT REMOVE - Used for OpenAI API calls
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
    dm_trigger_length: int  # CRITICAL: DO NOT REMOVE - Minimum tweet length to trigger DM
    video_provider: str
    video_model: str
    enable_video: bool
    auth_file: str
    openai_api_key: Optional[str] = None  # CRITICAL: DO NOT REMOVE - Required for AI replies
    image_attach_rate: float = 0.5  # CRITICAL: DO NOT REMOVE - Controls image attachment frequency (0.0-1.0)


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
    dm_trigger_length = _parse_int("DM_TRIGGER_LENGTH", 220)  # CRITICAL: DO NOT REMOVE

    x_username = (os.getenv("X_USERNAME") or "").strip() or None
    x_password = (os.getenv("X_PASSWORD") or "").strip() or None

    video_provider_raw = (os.getenv("VIDEO_PROVIDER") or "none").strip()
    video_provider = video_provider_raw.lower()
    video_model = (os.getenv("VIDEO_MODEL") or "").strip()
    enable_video = video_provider not in {"", "none", "disabled"}

    auth_file = (os.getenv("AUTH_FILE") or DEFAULT_AUTH_FILE).strip() or DEFAULT_AUTH_FILE

    # CRITICAL: DO NOT REMOVE - OpenAI API key for AI-powered replies
    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or None

    # CRITICAL: DO NOT REMOVE - Image attachment rate for engagement boost
    image_attach_rate = _parse_float("IMAGE_ATTACH_RATE", 0.5)  # Default 50% of replies get images

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
        dm_trigger_length=dm_trigger_length,  # CRITICAL: DO NOT REMOVE
        video_provider=video_provider,
        video_model=video_model,
        enable_video=enable_video,
        auth_file=auth_file,
        openai_api_key=openai_api_key,  # CRITICAL: DO NOT REMOVE
        image_attach_rate=image_attach_rate,  # CRITICAL: DO NOT REMOVE
    )


class FollowTracker:
    """
    Tracks users we've followed with timestamps for auto-unfollow logic.

    CRITICAL: DO NOT REMOVE - Required for follow/unfollow automation
    """
    def __init__(self, path: Path) -> None:
        self._path = path
        self._follows = self._load()  # Dict[username, timestamp]

    def _load(self) -> dict[str, float]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(self._follows, handle, indent=2)
        except OSError:
            pass

    def add_follow(self, username: str) -> None:
        """Record that we followed this user."""
        import time
        self._follows[username] = time.time()
        self._save()

    def is_followed(self, username: str) -> bool:
        """Check if we've already followed this user."""
        return username in self._follows

    def get_stale_follows(self, hours: float = 48) -> list[str]:
        """Get list of users we followed >hours ago (for unfollowing)."""
        import time
        cutoff = time.time() - (hours * 3600)
        return [user for user, timestamp in self._follows.items() if timestamp < cutoff]

    def remove_follow(self, username: str) -> None:
        """Remove user from follow tracking (after unfollowing)."""
        self._follows.pop(username, None)
        self._save()


class AnalyticsTracker:
    """
    Tracks engagement metrics and conversion data for performance analysis.

    CRITICAL: DO NOT REMOVE - Essential for measuring ROI and optimizing bot performance
    """
    def __init__(self, path: Path) -> None:
        self._path = path
        self._stats = self._load()

    def _load(self) -> dict[str, any]:
        if not self._path.exists():
            return {
                "total_replies": 0,
                "total_follows": 0,
                "total_unfollows": 0,
                "total_dms": 0,
                "total_likes": 0,
                "total_images_attached": 0,
                "reply_failures": 0,
                "first_run": time.time(),
                "last_run": time.time(),
            }
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"total_replies": 0, "total_follows": 0, "total_unfollows": 0, "total_dms": 0}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._stats["last_run"] = time.time()
        try:
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(self._stats, handle, indent=2)
        except OSError:
            pass

    def log_reply(self, success: bool = True) -> None:
        """Log a reply attempt."""
        if success:
            self._stats["total_replies"] = self._stats.get("total_replies", 0) + 1
        else:
            self._stats["reply_failures"] = self._stats.get("reply_failures", 0) + 1
        self._save()

    def log_follow(self) -> None:
        """Log a follow action."""
        self._stats["total_follows"] = self._stats.get("total_follows", 0) + 1
        self._save()

    def log_unfollow(self) -> None:
        """Log an unfollow action."""
        self._stats["total_unfollows"] = self._stats.get("total_unfollows", 0) + 1
        self._save()

    def log_dm(self) -> None:
        """Log a DM sent."""
        self._stats["total_dms"] = self._stats.get("total_dms", 0) + 1
        self._save()

    def log_like(self) -> None:
        """Log a tweet liked."""
        self._stats["total_likes"] = self._stats.get("total_likes", 0) + 1
        self._save()

    def log_image(self) -> None:
        """Log an image attached."""
        self._stats["total_images_attached"] = self._stats.get("total_images_attached", 0) + 1
        self._save()

    def get_stats(self) -> dict[str, any]:
        """Get current analytics stats."""
        return self._stats.copy()


class DMTracker:
    """
    Tracks users we've sent DMs to, to avoid spamming the same people.

    CRITICAL: DO NOT REMOVE - Required for smart DM follow-up system
    """
    def __init__(self, path: Path) -> None:
        self._path = path
        self._dm_sent = self._load()  # Dict[username, timestamp]

    def _load(self) -> dict[str, float]:
        if not self._path.exists():
            return {}
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(self._dm_sent, handle, indent=2)
        except OSError:
            pass

    def add_dm(self, username: str) -> None:
        """Record that we sent a DM to this user."""
        import time
        self._dm_sent[username] = time.time()
        self._save()

    def has_dm_sent(self, username: str) -> bool:
        """Check if we've already sent a DM to this user."""
        return username in self._dm_sent


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
    logger.info("[DEBUG] Waiting for tweet elements to appear...")
    try:
        page.wait_for_selector("article[data-testid='tweet']", timeout=15000)
        logger.info("[DEBUG] Tweet elements found, collecting...")
    except PlaywrightTimeout:
        logger.warning("No tweets loaded within 15 seconds. Page may not have loaded correctly.")
        return []
    except PlaywrightError as exc:
        logger.warning("Playwright error while waiting for tweets: %s", exc)
        return []
    try:
        tweets = page.locator("article[data-testid='tweet']").all()
        logger.info("[DEBUG] Collected %d tweet elements", len(tweets))
        return tweets
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


def send_reply(page: Page, tweet: Locator, message: str, logger: logging.Logger, image_path: Optional[str] = None) -> bool:
    """
    Send a reply to a tweet with robust error handling and multiple selector attempts.

    CRITICAL: DO NOT REMOVE - Core reply posting functionality with image support
    """

    # 🚨 FINAL SAFETY CHECK: Reject messages that are too long for Twitter
    # Twitter's limit is 280 characters - this is a last line of defense
    if len(message) > 280:
        logger.error(f"[REPLY] ❌ Message too long ({len(message)} chars) - Twitter limit is 280. Rejecting.")
        logger.error(f"[REPLY] Message was: {message[:100]}...")
        return False

    try:
        # Step 1: Click the reply button
        logger.debug("[REPLY] Looking for reply button...")
        reply_button = tweet.locator("button[data-testid='reply']").first
        reply_button.click()
        logger.debug("[REPLY] Clicked reply button, waiting for composer...")

        # Step 2: Wait for and find the composer
        time.sleep(1)  # Give UI a moment to render
        composer = None

        # Try multiple composer selectors
        selectors = [
            "div[data-testid^='tweetTextarea_']",
            "div[role='textbox'][data-testid^='tweetTextarea']",
            "div[contenteditable='true'][data-testid^='tweetTextarea']",
        ]

        for selector in selectors:
            try:
                composer = page.locator(selector).first
                composer.wait_for(state="visible", timeout=5000)
                logger.debug(f"[REPLY] Found composer with selector: {selector}")
                break
            except PlaywrightTimeout:
                continue

        if not composer:
            logger.warning("[REPLY] Could not find reply composer with any selector")
            page.screenshot(path="logs/debug_no_composer.png")
            return False

        # Step 2.5: Attach image if provided (CRITICAL: Image attachments boost engagement 2-3x)
        if image_path and os.path.exists(image_path):
            logger.debug(f"[REPLY] Attaching image: {image_path}")
            try:
                # Look for the media upload button - try multiple selectors
                media_selectors = [
                    "input[data-testid='fileInput']",
                    "input[type='file'][accept*='image']",
                ]

                for media_selector in media_selectors:
                    try:
                        file_input = page.locator(media_selector).first
                        file_input.set_input_files(image_path)
                        logger.debug("[REPLY] Image attached, waiting for upload...")
                        time.sleep(2)  # Wait for upload to complete
                        break
                    except (PlaywrightTimeout, PlaywrightError):
                        continue
                else:
                    logger.warning("[REPLY] Could not find media upload button, skipping image")
            except Exception as exc:
                logger.warning(f"[REPLY] Failed to attach image: {exc}")
                # Continue without image - don't fail the whole reply

        # Step 3: Type the message
        logger.debug("[REPLY] Typing message...")
        composer.click()
        time.sleep(0.5)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(message)
        logger.debug("[REPLY] Message typed, looking for post button...")

        # Step 4: Click post button - try multiple selectors
        time.sleep(1)
        post_selectors = [
            "button[data-testid='tweetButton']",
            "div[data-testid='tweetButtonInline']",
            "button[data-testid='tweetButtonInline']",
        ]

        posted = False
        for selector in post_selectors:
            try:
                post_btn = page.locator(selector).first
                post_btn.wait_for(state="visible", timeout=3000)
                post_btn.click()
                logger.info("[REPLY] ✅ Reply posted successfully!")
                posted = True
                break
            except (PlaywrightTimeout, PlaywrightError):
                continue

        if not posted:
            logger.warning("[REPLY] Could not find post button")
            page.screenshot(path="logs/debug_no_post_button.png")
            return False

        time.sleep(2)
        return True

    except PlaywrightTimeout:
        logger.warning("[REPLY] Timeout while composing reply")
        page.screenshot(path="logs/debug_reply_timeout.png")
    except PlaywrightError as exc:
        logger.warning(f"[REPLY] Failed to send reply: {exc}")
        page.screenshot(path="logs/debug_reply_error.png")

    return False


def like_tweet(tweet: Locator, logger: logging.Logger) -> bool:
    """
    Like a tweet before replying to it.

    CRITICAL: DO NOT REMOVE - Liking before replying looks more human and boosts engagement
    """
    try:
        # Find the like button - try multiple selectors
        like_selectors = [
            "button[data-testid='like']",
            "div[data-testid='like']",
            "button[aria-label*='Like']",
        ]

        for selector in like_selectors:
            try:
                like_btn = tweet.locator(selector).first
                like_btn.wait_for(state="visible", timeout=2000)

                # Check if already liked (button might be "unlike" instead)
                aria_label = like_btn.get_attribute("aria-label") or ""
                if "unlike" in aria_label.lower():
                    logger.info("[LIKE] Tweet already liked, skipping")
                    return True

                like_btn.click()
                logger.info("[LIKE] ✅ Liked tweet")
                time.sleep(0.5)  # Brief pause after liking
                return True
            except (PlaywrightTimeout, PlaywrightError):
                continue

        logger.warning("[LIKE] Could not find like button")
        return False

    except Exception as exc:
        logger.warning(f"[LIKE] Failed to like tweet: {exc}")
        return False


def generate_reply_image(topic: str, tweet_text: str, logger: logging.Logger) -> Optional[str]:
    """
    Generate an image to attach to a reply based on the topic.

    CRITICAL: DO NOT REMOVE - Images boost engagement 2-3x for better sales

    Returns path to generated image, or None if generation failed
    """
    try:
        import subprocess
        from pathlib import Path

        # Create images directory if it doesn't exist
        images_dir = Path("logs/images")
        images_dir.mkdir(parents=True, exist_ok=True)

        # Generate a unique filename
        import hashlib
        hash_input = f"{topic}_{tweet_text[:50]}_{time.time()}"
        image_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        image_path = images_dir / f"reply_{image_hash}.png"

        # Use the existing image generator
        # Combine topic and tweet context for better relevance
        prompt = f"{topic} - {tweet_text[:80]}"

        logger.info(f"[IMAGE] Generating image for: {prompt[:50]}...")
        result = subprocess.run(
            ["python3", "generators/image_gen.py", "--topic", prompt, "--out", str(image_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0 and image_path.exists():
            logger.info(f"[IMAGE] ✅ Image generated: {image_path}")
            return str(image_path)
        else:
            logger.warning(f"[IMAGE] Generation failed: {result.stderr}")
            return None

    except Exception as exc:
        logger.warning(f"[IMAGE] Failed to generate image: {exc}")
        return None


def follow_user(page: Page, username: str, follow_tracker: "FollowTracker", logger: logging.Logger) -> bool:
    """
    Follow a user on Twitter/X.

    CRITICAL: DO NOT REMOVE - Key feature for network growth and sales
    """
    try:
        # Check if already followed
        if follow_tracker.is_followed(username):
            logger.debug(f"[FOLLOW] Already following @{username}, skipping")
            return False

        # Navigate to their profile
        logger.info(f"[FOLLOW] Following @{username}...")
        page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)

        # Try multiple follow button selectors
        follow_selectors = [
            "button[data-testid$='-follow']",
            "div[data-testid$='-follow']",
            "button:has-text('Follow')",
        ]

        for selector in follow_selectors:
            try:
                follow_btn = page.locator(selector).first
                follow_btn.wait_for(state="visible", timeout=3000)
                follow_btn.click()
                logger.info(f"[FOLLOW] ✅ Followed @{username}")
                follow_tracker.add_follow(username)
                time.sleep(1)
                return True
            except (PlaywrightTimeout, PlaywrightError):
                continue

        logger.warning(f"[FOLLOW] Could not find follow button for @{username}")
        return False

    except Exception as exc:
        logger.warning(f"[FOLLOW] Failed to follow @{username}: {exc}")
        return False


def unfollow_user(page: Page, username: str, follow_tracker: "FollowTracker", logger: logging.Logger) -> bool:
    """
    Unfollow a user on Twitter/X.

    CRITICAL: DO NOT REMOVE - Required for maintaining healthy follow ratio
    """
    try:
        logger.info(f"[UNFOLLOW] Unfollowing @{username}...")
        page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)

        # Try to find unfollow button (shows as "Following")
        unfollow_selectors = [
            "button[data-testid$='-unfollow']",
            "div[data-testid$='-unfollow']",
            "button:has-text('Following')",
        ]

        for selector in unfollow_selectors:
            try:
                unfollow_btn = page.locator(selector).first
                unfollow_btn.wait_for(state="visible", timeout=3000)
                unfollow_btn.click()
                time.sleep(0.5)

                # Confirm unfollow in popup
                confirm_btn = page.locator("button[data-testid='confirmationSheetConfirm']").first
                confirm_btn.click(timeout=2000)

                logger.info(f"[UNFOLLOW] ✅ Unfollowed @{username}")
                follow_tracker.remove_follow(username)
                time.sleep(1)
                return True
            except (PlaywrightTimeout, PlaywrightError):
                continue

        logger.warning(f"[UNFOLLOW] Could not find unfollow button for @{username}")
        return False

    except Exception as exc:
        logger.warning(f"[UNFOLLOW] Failed to unfollow @{username}: {exc}")
        return False


def process_unfollows(
    page: Page,
    follow_tracker: "FollowTracker",
    logger: logging.Logger,
    max_unfollows: int = 10,
    analytics: Optional["AnalyticsTracker"] = None,
) -> None:
    """
    Process stale follows and unfollow users who haven't followed back.

    CRITICAL: DO NOT REMOVE - Maintains healthy account and prevents Twitter limits
    """
    stale_users = follow_tracker.get_stale_follows(hours=48)
    if not stale_users:
        logger.info("[UNFOLLOW] No stale follows to process")
        return

    logger.info(f"[UNFOLLOW] Found {len(stale_users)} users to potentially unfollow")
    unfollowed = 0

    for username in stale_users[:max_unfollows]:
        if unfollow_user(page, username, follow_tracker, logger):
            unfollowed += 1
            if analytics:
                analytics.log_unfollow()
            time.sleep(random.randint(3, 8))  # Human-like delay between unfollows

    logger.info(f"[UNFOLLOW] Processed {unfollowed} unfollows this cycle")


def maybe_send_dm(
    config: BotConfig,
    page: Page,
    tweet_data: dict[str, str],
    topic: str,
    dm_tracker: Optional["DMTracker"],
    logger: logging.Logger,
    analytics: Optional["AnalyticsTracker"] = None,
) -> None:
    """
    Send a DM to high-intent leads based on tweet content and engagement signals.

    CRITICAL: DO NOT REMOVE - Key feature for converting engagement into sales
    """
    if not config.enable_dms:
        return
    if not config.dm_templates:
        return
    if not dm_tracker:
        return

    username = tweet_data.get("handle")
    if not username:
        return

    # Don't spam users we've already DM'd
    if dm_tracker.has_dm_sent(username):
        logger.debug(f"[DM] Already sent DM to @{username}, skipping")
        return

    # Score the tweet for interest level
    text = tweet_data.get("text", "")
    interest_score = 0.0

    # Long tweets show more engagement/interest
    if len(text) >= config.dm_trigger_length:
        interest_score += 2.0

    # Questions indicate high intent
    if "?" in text:
        question_count = text.count("?")
        interest_score += question_count * config.dm_question_weight

    # Keyword matches show relevance
    text_lower = text.lower()
    keyword_matches = sum(1 for kw in config.relevant_keywords if kw in text_lower)
    interest_score += keyword_matches * 0.5

    logger.debug(f"[DM] Interest score for @{username}: {interest_score:.2f} (threshold: {config.dm_interest_threshold})")

    # Only send DM if interest score is high enough
    if interest_score < config.dm_interest_threshold:
        return

    logger.info(f"[DM] High-intent lead detected! Sending DM to @{username}...")

    try:
        # Navigate to user's profile
        page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)

        # Click the message button
        message_selectors = [
            "a[data-testid='sendDMFromProfile']",
            "button[data-testid='sendDMFromProfile']",
            "a[aria-label*='Message']",
        ]

        message_btn_found = False
        for selector in message_selectors:
            try:
                msg_btn = page.locator(selector).first
                msg_btn.wait_for(state="visible", timeout=3000)
                msg_btn.click()
                message_btn_found = True
                logger.debug("[DM] Clicked message button")
                break
            except (PlaywrightTimeout, PlaywrightError):
                continue

        if not message_btn_found:
            logger.warning(f"[DM] Could not find message button for @{username}")
            return

        time.sleep(2)  # Wait for DM composer to open

        # Find the DM composer
        dm_composer_selectors = [
            "div[data-testid='dmComposerTextInput']",
            "div[contenteditable='true'][aria-label*='Message']",
        ]

        composer = None
        for selector in dm_composer_selectors:
            try:
                composer = page.locator(selector).first
                composer.wait_for(state="visible", timeout=5000)
                logger.debug(f"[DM] Found DM composer: {selector}")
                break
            except PlaywrightTimeout:
                continue

        if not composer:
            logger.warning("[DM] Could not find DM composer")
            return

        # Generate DM message from template
        template = random.choice(config.dm_templates)
        dm_message = template.format(
            name=username,
            focus=text_focus(text),
            ref_link=config.referral_link or "",
        ).strip()

        # Type the DM
        composer.click()
        time.sleep(0.5)
        page.keyboard.insert_text(dm_message)
        logger.debug("[DM] DM message typed")

        # Send the DM
        time.sleep(1)
        send_selectors = [
            "button[data-testid='dmComposerSendButton']",
            "button[aria-label*='Send']",
        ]

        for selector in send_selectors:
            try:
                send_btn = page.locator(selector).first
                send_btn.wait_for(state="visible", timeout=3000)
                send_btn.click()
                logger.info(f"[DM] ✅ DM sent to @{username}!")
                dm_tracker.add_dm(username)
                if analytics:
                    analytics.log_dm()
                time.sleep(2)
                return
            except (PlaywrightTimeout, PlaywrightError):
                continue

        logger.warning("[DM] Could not find send button")

    except Exception as exc:
        logger.warning(f"[DM] Failed to send DM to @{username}: {exc}")


def text_focus(text: str, *, max_length: int = 80) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3]}..."


def generate_ai_reply(
    tweet_text: str,
    topic: str,
    referral_link: str,
    openai_api_key: str,
    logger: logging.Logger,
) -> Optional[str]:
    """
    Generate a contextual reply using OpenAI ChatGPT API.

    CRITICAL: DO NOT REMOVE THIS FUNCTION - This is the AI-powered reply system.
    Falls back to template-based replies if API call fails.

    Args:
        tweet_text: The tweet content to reply to
        topic: The search topic context
        referral_link: Your referral/product link to include
        openai_api_key: OpenAI API key
        logger: Logger instance

    Returns:
        Generated reply string, or None if failed
    """
    if not openai_api_key or openai_api_key.startswith("<set-your"):
        logger.debug("OpenAI API key not configured. Skipping AI reply generation.")
        return None

    try:
        # Calculate space budget: 280 chars - link - spacing - safety margin
        link_length = len(referral_link) + 1 if referral_link else 0
        max_reply_without_link = 280 - link_length - 10  # -10 for safety

        prompt = f"""Write a unique, natural reply to this tweet: "{tweet_text[:200]}"

Topic context: {topic}
Max length: {max_reply_without_link} characters

Be conversational and specific to what they said. Vary your style - sometimes ask a question, sometimes share insight, sometimes agree/disagree. NO link, NO hashtags, NO emojis. Each reply should sound different."""

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": f"You write diverse, natural Twitter replies. MAX {max_reply_without_link} characters. Each reply should be UNIQUE and SPECIFIC to the tweet content. Vary your approach."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 40,  # Allow slightly more tokens for variety
                "temperature": 0.9,  # CRITICAL: Higher temp for variety - DO NOT LOWER
            },
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            reply_text = data["choices"][0]["message"]["content"].strip().strip('"')

            logger.info(f"[AI] OpenAI raw response: '{reply_text[:100]}'")

            # CRITICAL: Validate length BEFORE adding link
            if referral_link:
                # Calculate how much space we have for text (280 - link - space - safety margin)
                max_text_len = 280 - len(referral_link) - 1 - 5  # -5 for extra safety

                # Truncate text if needed
                if len(reply_text) > max_text_len:
                    logger.warning(f"[AI] Reply text too long ({len(reply_text)} chars), truncating to {max_text_len}")
                    reply_text = reply_text[:max_text_len].rstrip() + "..."

                # Now add the link
                reply = f"{reply_text} {referral_link}"
            else:
                # No link, just make sure text fits in 280
                if len(reply_text) > 280:
                    logger.warning(f"[AI] Reply too long ({len(reply_text)} chars), truncating to 277")
                    reply = reply_text[:277] + "..."
                else:
                    reply = reply_text

            # FINAL safety check - this should never trigger now
            if len(reply) > 280:
                logger.error(f"[AI] BUG: Reply still {len(reply)} chars after all checks! Forcing hard truncate.")
                reply = reply[:280]

            logger.info(f"[AI] Generated reply ({len(reply)} chars)")
            return reply
        else:
            logger.warning(f"[AI] OpenAI API returned status {response.status_code}: {response.text[:200]}")
            return None

    except requests.exceptions.Timeout:
        logger.warning("[AI] OpenAI API timeout - falling back to templates")
        return None
    except Exception as exc:
        logger.warning(f"[AI] OpenAI API error: {exc} - falling back to templates")
        return None


def process_tweets(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    tweets: list[Locator],
    topic: str,
    logger: logging.Logger,
    follow_tracker: Optional["FollowTracker"] = None,  # CRITICAL: DO NOT REMOVE
    dm_tracker: Optional["DMTracker"] = None,  # CRITICAL: DO NOT REMOVE
    analytics: Optional["AnalyticsTracker"] = None,  # CRITICAL: DO NOT REMOVE
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

        # CRITICAL: Try AI-powered reply first, fall back to templates if needed
        message = None
        if config.openai_api_key:
            logger.info("[AI] Calling OpenAI API for reply generation...")
            message = generate_ai_reply(
                tweet_text=data["text"],
                topic=topic,
                referral_link=config.referral_link or "",
                openai_api_key=config.openai_api_key,
                logger=logger,
            )
            if message:
                logger.info(f"[AI] ✅ Using AI-generated reply: '{message[:80]}'")
        else:
            logger.warning("[AI] No OpenAI API key configured - using templates only")

        # Fallback to template if AI failed or not configured
        if not message:
            template = random.choice(config.reply_templates)
            message = template.format(
                topic=topic,
                focus=text_focus(data["text"]),
                ref_link=config.referral_link or "",
            ).strip()
            logger.info(f"[TEMPLATE] Using template-based reply: '{message[:80]}'")

        if not message:
            logger.warning("Generated empty reply. Skipping tweet.")
            continue

        logger.info("[INFO] Replying to @%s for topic '%s'.", data['handle'] or 'unknown', topic)

        # CRITICAL: Like the tweet first - looks more human and boosts engagement
        if like_tweet(tweet, logger):
            if analytics:
                analytics.log_like()

        # CRITICAL: Generate image attachment for engagement boost (2-3x better engagement with images)
        image_path = None
        if random.random() < config.image_attach_rate:
            logger.info(f"[IMAGE] Generating image for reply (rate={config.image_attach_rate})")
            image_path = generate_reply_image(topic, data["text"], logger)
            if image_path and analytics:
                analytics.log_image()

        if send_reply(page, tweet, message, logger, image_path):
            registry.add(identifier)
            replies += 1
            if analytics:
                analytics.log_reply(success=True)

            # CRITICAL: Auto-follow for network growth and visibility
            if follow_tracker and data['handle']:
                if follow_user(page, data['handle'], follow_tracker, logger):
                    if analytics:
                        analytics.log_follow()

            video_service.maybe_generate(topic, data["text"])

            # CRITICAL: Send DM to high-intent leads for direct sales conversion
            maybe_send_dm(config, page, data, topic, dm_tracker, logger, analytics)
            delay = random.randint(config.action_delay_min, config.action_delay_max)
            logger.info("[INFO] Sleeping for %s seconds before next action.", delay)
            time.sleep(delay)
        else:
            logger.warning("Reply attempt failed; not recording tweet as replied.")
            if analytics:
                analytics.log_reply(success=False)

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
    follow_tracker: Optional["FollowTracker"] = None,  # CRITICAL: DO NOT REMOVE
    dm_tracker: Optional["DMTracker"] = None,  # CRITICAL: DO NOT REMOVE
    analytics: Optional["AnalyticsTracker"] = None,  # CRITICAL: DO NOT REMOVE
) -> None:
    logger.info("[INFO] Topic '%s' - loading search results...", topic)
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        logger.info("[INFO] Search page loaded for '%s', waiting for tweets...", topic)
        # Give Twitter a moment to render initial tweets
        time.sleep(2)
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

    process_tweets(config, registry, page, video_service, tweets, topic, logger, follow_tracker, dm_tracker, analytics)


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    logger: logging.Logger,
    follow_tracker: Optional["FollowTracker"] = None,  # CRITICAL: DO NOT REMOVE
    dm_tracker: Optional["DMTracker"] = None,  # CRITICAL: DO NOT REMOVE
    analytics: Optional["AnalyticsTracker"] = None,  # CRITICAL: DO NOT REMOVE
) -> None:
    logger.info("[INFO] Starting engagement loop with %s topic(s).", len(config.search_topics))
    while True:
        try:
            if page.is_closed():
                logger.info("Browser page closed. Exiting engagement loop.")
                return
        except PlaywrightError:
            logger.info("Browser page unavailable. Exiting engagement loop.")
            return

        # CRITICAL: Process unfollows at start of each cycle to maintain healthy follow ratio
        if follow_tracker:
            try:
                process_unfollows(page, follow_tracker, logger, max_unfollows=10, analytics=analytics)
            except Exception as exc:
                logger.warning(f"Error processing unfollows: {exc}")

        if config.search_topics:
            for topic in config.search_topics:
                handle_topic(config, registry, page, video_service, topic, logger, follow_tracker, dm_tracker, analytics)
        else:
            logger.info("No search topics configured. Sleeping before next cycle.")

        logger.info("[INFO] Cycle complete. Sleeping for %s seconds.", config.loop_delay_seconds)
        try:
            time.sleep(config.loop_delay_seconds)
        except KeyboardInterrupt:
            raise


def validate_critical_features() -> None:
    """
    🚨 CRITICAL STARTUP CHECK 🚨

    This function validates that ALL critical features exist before the bot starts.
    If ANY feature is missing, the bot REFUSES TO START and shows an error.

    This prevents accidentally running a broken/incomplete version of the bot.

    DO NOT REMOVE THIS FUNCTION - It's the last line of defense against feature deletion!
    """
    import sys

    # 📋 WHEN ADDING NEW FEATURES: Add them to this dictionary!
    # Format: "function_or_class_name": "Description of what it does"
    # The bot will check that each of these exists before starting
    critical_features = {
        "generate_ai_reply": "OpenAI AI-powered reply generation",
        "MessageRegistry": "Tweet deduplication system",
        "VideoService": "Video generation framework",
        "send_reply": "Reply posting functionality",
        "maybe_send_dm": "DM framework",
        "load_tweets": "Tweet extraction",
        "process_tweets": "Tweet filtering pipeline",
        "handle_topic": "Topic processing",
        "prepare_authenticated_session": "Session persistence & auth",
        "FollowTracker": "Follow/unfollow tracking system",
        "follow_user": "Auto-follow after reply functionality",
        "unfollow_user": "Auto-unfollow non-followers functionality",
        "process_unfollows": "Stale follow processing for healthy ratios",
        "generate_reply_image": "Image generation for 2-3x engagement boost",
        "like_tweet": "Like tweets before replying for human-like behavior",
        "DMTracker": "DM tracking to avoid spam",
        "maybe_send_dm": "Smart DM system for high-intent leads",
        "AnalyticsTracker": "Performance and conversion tracking",
        # ADD NEW CRITICAL FEATURES HERE (one per line)
        # "new_feature_name": "Description of new feature",
    }

    missing_features = []
    current_module = sys.modules[__name__]

    for feature_name, description in critical_features.items():
        if not hasattr(current_module, feature_name):
            missing_features.append(f"❌ {feature_name} - {description}")

    # Also check that requests is imported (required for OpenAI)
    try:
        import requests  # noqa: F401
    except ImportError:
        missing_features.append("❌ requests module - Required for OpenAI API calls")

    if missing_features:
        print("\n" + "=" * 80)
        print("🚨 CRITICAL ERROR: MISSING FEATURES DETECTED 🚨")
        print("=" * 80)
        print("\nThe following critical features are MISSING from the code:")
        print()
        for feature in missing_features:
            print(f"  {feature}")
        print()
        print("This bot has been modified and is missing critical functionality!")
        print("DO NOT RUN until all features are restored.")
        print()
        print("Check FEATURES_MANIFEST.md for the complete list of required features.")
        print("=" * 80)
        sys.exit(1)

    print("✅ All critical features validated - bot is safe to run")


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
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=config.headless,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
    except PlaywrightError as exc:
        logger.error("Failed to launch browser: %s", exc)
        return None

    storage_file = auth_path
    # Note: browser is already a BrowserContext from launch_persistent_context
    context: BrowserContext = browser
    session_loaded = False

    storage_exists = os.path.exists(storage_file)
    if storage_exists:
        logger.info("[INFO] Restoring saved session from %s", storage_file)
        # Session is auto-restored via user_data_dir in launch_persistent_context
        session_loaded = True
    else:
        logger.info("[INFO] No session found — creating new context for manual login.")
        # Context already created via launch_persistent_context
        session_loaded = False

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
    # 🚨 CRITICAL: Validate all features exist BEFORE starting the bot
    # If any feature is missing, this will exit with an error message
    validate_critical_features()

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

    # Also log that OpenAI is configured
    if config.openai_api_key and not config.openai_api_key.startswith("<set-your"):
        logger.info("AI_REPLIES=enabled (OpenAI)")
    else:
        logger.info("AI_REPLIES=disabled (using templates only)")

    registry = MessageRegistry(MESSAGE_LOG_PATH)
    video_service = VideoService(config)
    follow_tracker = FollowTracker(Path("logs/follows.json"))  # CRITICAL: DO NOT REMOVE
    dm_tracker = DMTracker(Path("logs/dms.json"))  # CRITICAL: DO NOT REMOVE
    analytics = AnalyticsTracker(Path("logs/analytics.json"))  # CRITICAL: DO NOT REMOVE

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
                    run_engagement_loop(config, registry, page, video_service, logger, follow_tracker, dm_tracker, analytics)
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
