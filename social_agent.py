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
) -> bool:
    del auth_file  # Not used with persistent context

    # Ensure we're on a clean login page
    logger.info("[INFO] Preparing clean login page for manual login...")
    try:
        current_url = page.url
        if "login" not in current_url:
            logger.info("[INFO] Navigating to login page...")
            page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
    except PlaywrightError as exc:
        logger.warning("Could not verify login page: %s", exc)

    print("\n" + "="*70)
    print("MANUAL LOGIN REQUIRED")
    print("="*70)
    print("\nA browser window is open showing the X/Twitter login page.")
    print("\nThe script will NOT touch any form fields or buttons.")
    print("You have complete control of the browser.")
    print("\nPlease complete the following steps:")
    print("  1. CLICK 'SIGN IN WITH GOOGLE' BUTTON (bypasses bot detection!)")
    print("     (If you don't have Google linked, use Apple or regular login)")
    print("  2. Complete the Google login / 2FA if prompted")
    print("  3. Wait until you see your Twitter/X home feed")
    print("  4. Come back to this terminal and press ENTER")
    print("\nIMPORTANT NOTES:")
    print("  • The script is completely hands-off - it won't interfere")
    print("  • If you see rate limit errors, wait a few minutes before trying")
    print("  • If you get 'unusual activity' warnings, complete the verification")
    print("  • The browser will stay open - don't close it manually")
    print("  • Take your time - there's no rush!")
    print("  • Your session will be saved AUTOMATICALLY after login")
    print("\nTROUBLESHOOTING:")
    print("  • If automated login keeps interfering, remove X_USERNAME and")
    print("    X_PASSWORD from your .env file, OR set FORCE_MANUAL_LOGIN=true")
    print("\n" + "="*70)
    print("\nWaiting for you to complete login...")
    print("(Press ENTER after you've successfully logged in)")
    print("="*70 + "\n")

    try:
        input()  # Wait for user to press Enter
    except (KeyboardInterrupt, EOFError):
        logger.error("Manual login cancelled by user.")
        return False

    logger.info("[INFO] Verifying login status...")
    time.sleep(2)  # Give page a moment to stabilize

    # Verify they're actually logged in
    max_retries = 3
    for attempt in range(max_retries):
        if is_logged_in(page):
            # Wait a bit for session to stabilize
            logger.info("[INFO] Login verified! Waiting for session to stabilize...")
            time.sleep(3)

            print("\n" + "="*70)
            print("✓ LOGIN SUCCESSFUL!")
            print("="*70)
            print("\nYour session has been saved automatically.")
            print("The browser profile is stored in: ~/.social_agent_codex/browser_session/")
            print("Next time you run this script, you won't need to log in again.")
            print("="*70 + "\n")

            logger.info("[INFO] Manual login completed successfully")
            return True
        else:
            if attempt < max_retries - 1:
                logger.info("[INFO] Login not detected yet, retrying in 2 seconds...")
                time.sleep(2)

    # If we get here, login verification failed
    print("\n" + "!"*70)
    print("WARNING: Login verification failed!")
    print("!"*70)
    print("\nIt looks like you might not be logged in yet.")
    print("Please check the browser and make sure you:")
    print("  - Completed the login successfully")
    print("  - Can see your Twitter/X home feed")
    print("  - Are not stuck on a security check page")
    print("\nOptions:")
    print("  1. Press ENTER to proceed anyway (if you're sure you're logged in)")
    print("  2. Press Ctrl+C to cancel and try again")
    print("!"*70 + "\n")

    try:
        input()
        logger.warning("Proceeding despite login verification failure (user override)")
        return True
    except (KeyboardInterrupt, EOFError):
        logger.error("Login cancelled by user.")
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
    # For manual login, skip all checks and go straight to wait_for_manual_login
    if not automated_attempt:
        logger.info("[INFO] Manual login mode - no automation will be attempted")
        return wait_for_manual_login(context, page, logger, auth_file)

    # Only for automated login: check if already logged in
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        logger.warning("Timeout while loading home timeline during login check.")
    except PlaywrightError as exc:
        logger.warning("Error while loading home timeline: %s", exc)

    if is_logged_in(page):
        logger.info("[INFO] Session restored successfully")
        return True

    # Try automated login
    if config.x_username and config.x_password:
        logger.info("[INFO] Attempting automated login...")
        if automated_login(page, config, logger):
            logger.info("[INFO] Automated login completed! Session will be saved automatically.")
            time.sleep(3)  # Wait for session to stabilize
            logger.info("[INFO] Session persisted to browser profile")
            return True
        else:
            logger.warning("[WARN] Automated login failed. Falling back to manual login.")
            logger.info("[INFO] Navigating to fresh login page for manual login...")
            # Navigate to fresh login page to clear any automation artifacts
            try:
                page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)  # Give page time to fully load
            except (PlaywrightTimeout, PlaywrightError) as exc:
                logger.warning("Error loading fresh login page: %s", exc)

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
        return True
    except PlaywrightTimeout:
        logger.warning("Timeout while composing reply.")
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
        page.goto(url, wait_until="networkidle", timeout=60000)
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


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    logger: logging.Logger,
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

        if config.search_topics:
            for topic in config.search_topics:
                handle_topic(config, registry, page, video_service, topic, logger)
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
    # When using persistent context, browser is None and we only close the context
    # The persistent context handles all cleanup automatically
    try:
        if context:
            context.close()
            logger.debug("Browser context closed")
    except PlaywrightError as exc:
        logger.debug("Error while closing context: %s", exc)

    # Browser is None when using persistent context, only close if it exists
    try:
        if browser:
            browser.close()
            logger.debug("Browser closed")
    except PlaywrightError as exc:
        logger.debug("Error while closing browser: %s", exc)


def prepare_authenticated_session(
    playwright,
    config: BotConfig,
    logger: logging.Logger,
) -> Optional[tuple[Browser, BrowserContext, Page]]:
    # Determine if we need manual login
    user_data_dir = str(Path.home() / ".social_agent_codex/browser_session/")
    session_marker = Path(user_data_dir) / ".session_exists"
    has_credentials = config.x_username and config.x_password
    has_saved_session = session_marker.exists()

    # Check if user wants to force manual login
    force_manual = _parse_bool(os.getenv("FORCE_MANUAL_LOGIN"), default=True)  # Default to True for safety

    # Force non-headless mode if manual login will be required
    # Manual login needed if: no saved session AND (no credentials OR force manual)
    use_headless = config.headless
    if not has_saved_session and (not has_credentials or force_manual):
        use_headless = False
        logger.info("[INFO] Manual login will be required")
        logger.info("[INFO] Launching browser in VISIBLE mode...")

    logger.info(f"[INFO] Browser mode: {'HEADLESS' if use_headless else 'VISIBLE'}")

    # Create user data directory
    try:
        os.makedirs(user_data_dir, exist_ok=True)
    except OSError as exc:
        logger.error("Failed to create user data directory: %s", exc)
        return None

    # Check for imported cookies from regular browser
    storage_state_file = Path(user_data_dir) / "storage_state.json"
    storage_state_arg = str(storage_state_file) if storage_state_file.exists() else None

    if storage_state_arg:
        logger.info("[INFO] Found imported cookies from regular browser!")
        logger.info("[INFO] This will bypass Twitter's bot detection")

    # Launch persistent context - this IS the context, not a browser
    # The persistent context automatically saves cookies/sessions to user_data_dir
    logger.info(f"[INFO] Launching browser context...")
    logger.info(f"[INFO] User data directory: {user_data_dir}")
    logger.info(f"[INFO] Headless: {use_headless}")
    try:
        logger.info("[INFO] Launching Chromium browser...")
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=use_headless,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            storage_state=storage_state_arg,
        )
        logger.info("[INFO] Chromium browser context launched successfully!")
    except PlaywrightError as exc:
        logger.error("Failed to launch browser context: %s", exc)
        logger.exception("Full exception details:")
        return None
    except Exception as exc:
        logger.error("Unexpected error launching browser: %s", exc)
        logger.exception("Full exception details:")
        return None

    # Create a page from the persistent context
    try:
        page = context.new_page()

        # Inject JavaScript to hide automation completely
        page.add_init_script("""
            // Remove webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override plugins to look real
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            // Make chrome object appear real
            window.chrome = {
                runtime: {}
            };

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)

    except PlaywrightError as exc:
        logger.error("Failed to create page: %s", exc)
        context.close()
        return None

    # Check if we already have a valid session
    if has_saved_session:
        logger.info("[INFO] Attempting to restore previous session...")
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            if is_logged_in(page):
                logger.info("[INFO] Session restored successfully!")
                # Return None as browser since we're using persistent context
                return None, context, page
            else:
                logger.warning("[WARN] Previous session expired, need to login again.")
        except (PlaywrightTimeout, PlaywrightError) as exc:
            logger.warning("Error verifying session: %s. Will attempt login.", exc)

    # Navigate to login page
    try:
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)  # Give page time to fully load and settle
    except PlaywrightTimeout:
        logger.warning("Timeout while opening login page. Proceeding to login checks.")
    except PlaywrightError as exc:
        logger.error("Failed to load login page: %s", exc)
        context.close()
        return None

    # Check if user wants to force manual login (via environment variable)
    force_manual = _parse_bool(os.getenv("FORCE_MANUAL_LOGIN"), default=False)

    # Attempt login (automated only if not forced manual and credentials exist)
    auth_file = (os.getenv("AUTH_FILE") or config.auth_file).strip() or config.auth_file
    attempt_automated = not force_manual and has_credentials

    if force_manual:
        logger.info("[INFO] FORCE_MANUAL_LOGIN is enabled - skipping automated login")

    if not ensure_logged_in(
        context,
        page,
        config,
        logger,
        automated_attempt=attempt_automated,
        auth_file=auth_file,
    ):
        logger.error("Login process did not complete successfully.")
        context.close()
        return None

    # Mark that we have a saved session now
    try:
        session_marker.touch()
        logger.info("[INFO] Session marker created at %s", session_marker)
    except OSError as exc:
        logger.debug("Could not create session marker: %s", exc)

    logger.info("[INFO] Authentication complete; proceeding to engagement loop.")
    return None, context, page


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
