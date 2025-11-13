#!/usr/bin/env python3
"""Sync Playwright social agent with persistent X session handling."""

from __future__ import annotations

import argparse
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

# Optional: For AI image generation (safe import with fallback)
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

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

# CRITICAL FIX: Load .env BEFORE checking USE_NEW_CONFIG
# This ensures environment variables are available at import time
load_dotenv()

# FEATURE ADD: Political Mode (conditional import - no breaking changes)
# Only imported if USE_NEW_CONFIG=true in .env
# To revert: set USE_NEW_CONFIG=false or remove these imports
_political_mode_available = False
_political_composer = None
_political_config = None

try:
    use_new_config = os.getenv("USE_NEW_CONFIG", "false").lower() == "true"
    if use_new_config:
        from app.config_loader import get_config
        from app.media.image_adapter import ImageAdapter
        from app.media.video_adapter import VideoAdapter
        from app.engagement.politics_reply import PoliticalReplyGenerator
        from app.reply.compose import ReplyComposer

        # Initialize political mode components
        _political_config = get_config()
        _image_adapter = ImageAdapter()
        _video_adapter = VideoAdapter()
        _politics_gen = PoliticalReplyGenerator(_political_config)
        _political_composer = ReplyComposer(_political_config, _image_adapter, _video_adapter, _politics_gen)
        _political_mode_available = True

        logging.getLogger(__name__).info("[political-mode] Political mode ENABLED (USE_NEW_CONFIG=true)")
    else:
        logging.getLogger(__name__).info("[political-mode] Political mode DISABLED (USE_NEW_CONFIG=false) - using gambling mode")
except ImportError as e:
    logging.getLogger(__name__).warning(f"[political-mode] Could not load political mode modules: {e}")
    logging.getLogger(__name__).info("[political-mode] Falling back to gambling mode")
except Exception as e:
    logging.getLogger(__name__).error(f"[political-mode] Error initializing political mode: {e}")
    logging.getLogger(__name__).info("[political-mode] Falling back to gambling mode")

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


def send_reply(page: Page, tweet: Locator, message: str, logger: logging.Logger, media_path: Optional[str] = None) -> bool:
    try:
        logger.debug("Scrolling tweet into view...")
        tweet.scroll_into_view_if_needed()
        time.sleep(0.5)

        logger.debug("Looking for reply button...")

        # Try multiple selectors for the reply button
        reply_selectors = [
            "div[data-testid='reply']",
            "button[data-testid='reply']",
            "[aria-label*='Reply']",
            "[data-testid='reply'] button",
        ]

        reply_btn = None
        for selector in reply_selectors:
            try:
                btn = tweet.locator(selector).first
                btn.wait_for(timeout=1000, state="visible")
                reply_btn = btn
                logger.debug(f"Reply button found with selector: {selector}")
                break
            except PlaywrightTimeout:
                continue

        if not reply_btn:
            logger.warning("Reply button not found with any selector!")
            # Take screenshot for debugging
            try:
                page.screenshot(path="/tmp/tweet_debug.png")
                logger.debug("Screenshot saved to /tmp/tweet_debug.png")
            except Exception:
                pass
            return False

        logger.debug("Clicking reply button...")
        # Force click to bypass any overlays
        reply_btn.click(force=True, timeout=5000)
        logger.debug("Reply button clicked, waiting for composer...")
        time.sleep(3)  # Give modal time to fully open

        # Try multiple possible selectors for the composer
        logger.debug("Looking for composer...")
        try:
            composer = page.locator("div[data-testid='tweetTextarea_0']").first
            composer.wait_for(timeout=5000, state="visible")
            logger.debug("Found composer with tweetTextarea_0")
        except PlaywrightTimeout:
            logger.debug("Trying alternative composer selector...")
            try:
                composer = page.locator("div[contenteditable='true'][role='textbox']").first
                composer.wait_for(timeout=5000, state="visible")
                logger.debug("Found composer with contenteditable selector")
            except PlaywrightTimeout:
                logger.warning("Composer never appeared after clicking reply!")
                return False

        logger.debug("Clicking into composer and typing message...")
        composer.click()
        time.sleep(random.uniform(0.3, 0.7))

        logger.debug("Typing message into composer...")
        # Type with human-like delays for more natural behavior
        page.keyboard.type(message, delay=random.randint(10, 30))
        time.sleep(random.uniform(0.5, 1.5))

        # Upload media if provided (FEATURE ADD: Political mode image support)
        if media_path and os.path.exists(media_path):
            try:
                logger.debug(f"[media] Uploading media to reply: {media_path}")
                # Find the image upload input
                file_input = page.locator("input[data-testid='fileInput']").first
                if file_input:
                    file_input.set_input_files(media_path)
                    logger.debug("[media] Media uploaded successfully to reply")
                    time.sleep(2)  # Wait for media to process
                else:
                    logger.debug("[media] Media upload input not found, posting without media")
            except Exception as exc:
                logger.debug(f"[media] Media upload failed (posting text-only): {exc}")
                # Continue without media - don't fail the whole reply

        logger.debug("Looking for Reply/Post button...")

        # Wait a moment for button to be ready
        time.sleep(1)

        # Try multiple selectors for the reply post button (not save draft!)
        # IMPORTANT: Look for specific Reply button text to avoid Save button
        post_selectors = [
            "button[data-testid='tweetButton']:has-text('Reply')",  # Reply button with exact text
            "button[data-testid='tweetButton']:has-text('Post')",   # Or Post text
            "button[data-testid='tweetButton']",  # Fallback to main button
            "button:has-text('Reply')",
        ]

        send_btn = None
        for selector in post_selectors:
            try:
                btn = page.locator(selector).first
                btn.wait_for(timeout=3000, state="visible")

                # Make sure button is enabled (not disabled due to long message)
                is_disabled = btn.get_attribute("disabled")
                if is_disabled:
                    logger.debug(f"Button found but disabled with selector: {selector}, trying next...")
                    continue

                # Check button text to confirm it's not Save
                button_text = btn.inner_text()
                logger.debug(f"Found button with text: '{button_text}' using selector: {selector}")

                if "save" in button_text.lower():
                    logger.debug("This is a Save button, skipping...")
                    continue

                send_btn = btn
                logger.debug(f"✓ Post button confirmed with selector: {selector}")
                break
            except PlaywrightTimeout:
                logger.debug(f"Timeout waiting for selector: {selector}")
                continue
            except PlaywrightError as e:
                logger.debug(f"Error with selector {selector}: {e}")
                continue

        if not send_btn:
            logger.warning("Post button not found or all buttons disabled!")
            # Debug: show what buttons ARE visible
            try:
                all_buttons = page.locator("button").all()
                logger.debug(f"DEBUG: Found {len(all_buttons)} total buttons on page")
                for i, btn in enumerate(all_buttons[:10]):  # Show first 10
                    try:
                        text = btn.inner_text()
                        testid = btn.get_attribute("data-testid") or "no-testid"
                        logger.debug(f"  Button {i+1}: text='{text}', testid='{testid}'")
                    except:
                        pass
            except:
                pass
            return False

        logger.debug("Clicking post button NOW...")
        try:
            send_btn.click(timeout=3000)
            logger.debug("✓ Click successful!")
        except PlaywrightError as e:
            logger.warning(f"Normal click failed: {e}, trying force click...")
            send_btn.click(force=True)
            logger.debug("✓ Force click successful!")

        time.sleep(3)  # Wait for reply to post

        # Check for automation warning (CRITICAL - must cooldown if detected)
        if check_automation_warning(page, logger):
            raise Exception("AUTOMATION_WARNING_DETECTED")

        # Check for error messages (rate limits, etc)
        try:
            error_selectors = [
                "text=/rate limit/i",
                "text=/try again later/i",
                "text=/something went wrong/i",
            ]
            for error_sel in error_selectors:
                if page.locator(error_sel).count() > 0:
                    logger.warning("Detected error message on page - reply may have failed")
                    return False
        except Exception:
            pass  # Ignore errors while checking for errors

        logger.info("[INFO] Reply posted successfully.")
        return True
    except PlaywrightTimeout as exc:
        logger.warning("Timeout during reply: %s", exc)
    except PlaywrightError as exc:
        logger.warning("Failed to send reply: %s", exc)
    return False


def create_original_post(page: Page, message: str, logger: logging.Logger, image_path: Optional[str] = None) -> bool:
    """
    Create an original tweet/post (not a reply).
    NEW FUNCTION - doesn't touch reply code!
    Optionally includes an image if image_path is provided.
    """
    try:
        logger.debug("Looking for Post/Tweet button...")

        # Try to find the main post button
        post_btn_selectors = [
            "a[href='/compose/tweet']",
            "a[data-testid='SideNav_NewTweet_Button']",
            "[aria-label='Post']",
            "button:has-text('Post')",
        ]

        post_btn = None
        for selector in post_btn_selectors:
            try:
                btn = page.locator(selector).first
                btn.wait_for(timeout=2000, state="visible")
                post_btn = btn
                logger.debug(f"Post button found with selector: {selector}")
                break
            except PlaywrightTimeout:
                continue

        if not post_btn:
            logger.warning("Post button not found - cannot create original post")
            return False

        logger.debug("Clicking post button...")
        post_btn.click(force=True)
        time.sleep(random.uniform(1, 2))

        # Wait for composer
        logger.debug("Looking for composer...")
        try:
            composer = page.locator("div[data-testid='tweetTextarea_0']").first
            composer.wait_for(timeout=5000, state="visible")
            logger.debug("Found composer")
        except PlaywrightTimeout:
            logger.warning("Composer didn't appear for original post")
            return False

        # Type message (slower, more human-like)
        logger.debug("Typing original post...")
        composer.click()
        time.sleep(random.uniform(0.5, 1.2))
        page.keyboard.type(message, delay=random.randint(50, 120))  # Much slower typing
        time.sleep(random.uniform(2, 4))  # Longer pause after typing

        # Upload image if provided (SAFE: fails gracefully if it doesn't work)
        if image_path and os.path.exists(image_path):
            try:
                logger.debug(f"Uploading image: {image_path}")

                # Find the image upload input
                file_input = page.locator("input[data-testid='fileInput']").first
                if file_input:
                    file_input.set_input_files(image_path)
                    logger.debug("Image uploaded successfully")
                    time.sleep(2)  # Wait for image to process
                else:
                    logger.debug("Image upload input not found, posting without image")
            except Exception as exc:
                logger.debug(f"Image upload failed (posting text-only): {exc}")
                # Continue without image - don't fail the whole post

        # Wait a moment for Post button to become enabled
        time.sleep(2)

        # Click post button (make sure it's "Post" not "Save")
        logger.debug("Looking for Post button...")

        post_selectors = [
            "button[data-testid='tweetButton']:has-text('Post')",
            "button[data-testid='tweetButton']",
        ]

        send_btn = None
        for selector in post_selectors:
            try:
                btn = page.locator(selector).first
                btn.wait_for(timeout=2000, state="visible")

                # Verify button text to avoid clicking "Save"
                btn_text = btn.inner_text()
                logger.debug(f"Found button with text: '{btn_text}'")

                # Check if button is disabled
                is_disabled = btn.is_disabled()
                if is_disabled:
                    logger.debug(f"Button is disabled: '{btn_text}'")
                    continue

                if "save" in btn_text.lower():
                    logger.debug("This is a Save button, skipping...")
                    continue

                if "post" in btn_text.lower():
                    send_btn = btn
                    logger.debug(f"✓ Post button found and enabled: '{btn_text}'")
                    break
            except PlaywrightTimeout:
                continue
            except Exception as e:
                logger.debug(f"Error checking button: {e}")
                continue

        if not send_btn:
            logger.warning("Post button not found or disabled (only Save button available - message may be too long or have an issue)")
            return False

        logger.debug("Clicking Post button...")
        send_btn.click(force=True)
        time.sleep(3)

        # Check for automation warning (CRITICAL - must cooldown if detected)
        if check_automation_warning(page, logger):
            raise Exception("AUTOMATION_WARNING_DETECTED")

        # Check for errors
        try:
            error_selectors = [
                "text=/rate limit/i",
                "text=/try again later/i",
                "text=/something went wrong/i",
            ]
            for error_sel in error_selectors:
                if page.locator(error_sel).count() > 0:
                    logger.warning("Detected error message on page - original post may have failed")
                    return False
        except Exception:
            pass

        logger.info("[INFO] ✅ Original post created successfully!")

        # Close modal
        try:
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass

        return True

    except PlaywrightTimeout as exc:
        logger.warning("Timeout during original post: %s", exc)
    except PlaywrightError as exc:
        logger.warning("Failed to create original post: %s", exc)
    return False


def follow_user(page: Page, tweet: Locator, logger: logging.Logger) -> bool:
    """
    Follow a user by visiting their profile.
    NEW FUNCTION - completely separate from reply code!
    """
    try:
        # Extract username from the tweet
        logger.debug("Extracting username from tweet...")
        username_link = tweet.locator("a[href^='/'][href*='status']").first
        href = username_link.get_attribute("href", timeout=2000)

        if not href:
            logger.debug("Could not extract username from tweet")
            return False

        # Extract username from href like "/username/status/123456"
        username = href.split('/')[1] if '/' in href else None
        if not username or username == "status":
            logger.debug("Invalid username extracted")
            return False

        logger.debug(f"Extracted username: @{username}")

        # Save current URL to return later
        current_url = page.url

        # Navigate to user's profile
        profile_url = f"https://x.com/{username}"
        logger.debug(f"Navigating to profile: {profile_url}")
        page.goto(profile_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)  # Let profile load

        # Find Follow button on profile page
        logger.debug("Looking for Follow button on profile...")

        follow_selectors = [
            "div[data-testid='follow']",
            "button[data-testid='follow']",
            "div[aria-label*='Follow @']",
            "button:has-text('Follow'):not(:has-text('Following'))",
            "div[role='button']:has-text('Follow'):not(:has-text('Following'))",
        ]

        follow_btn = None
        for selector in follow_selectors:
            try:
                btn = page.locator(selector).first
                btn.wait_for(timeout=2000, state="visible")

                # Check button text to ensure it's "Follow" not "Following"
                btn_text = btn.inner_text() or ""
                logger.debug(f"Found button: '{btn_text}' with selector: {selector}")

                if "following" in btn_text.lower():
                    logger.debug("Already following this user")
                    page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
                    return False

                if "follow" in btn_text.lower():
                    follow_btn = btn
                    logger.debug(f"✓ Follow button found: {selector}")
                    break

            except PlaywrightTimeout:
                continue
            except PlaywrightError:
                continue

        if not follow_btn:
            logger.debug("No Follow button found on profile")
            page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
            return False

        # Click Follow button
        logger.debug("Clicking Follow button...")
        follow_btn.click(force=True)
        time.sleep(random.uniform(2, 3))

        logger.info("[INFO] ✓ Followed user successfully!")

        # Navigate back to search results
        logger.debug("Returning to search results...")
        page.goto(current_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(1)

        return True

    except PlaywrightError as exc:
        logger.debug(f"Failed to follow user: {exc}")
        try:
            # Try to get back to where we were
            page.go_back(wait_until="domcontentloaded", timeout=10000)
        except:
            pass
        return False


def retweet_post(page: Page, tweet: Locator, logger: logging.Logger) -> bool:
    """
    Retweet a post to increase account activity and engagement.
    NEW FUNCTION - safe, won't break anything!
    """
    try:
        logger.debug("Looking for retweet button...")

        # Find retweet button
        retweet_selectors = [
            "button[data-testid='retweet']",
            "div[data-testid='retweet']",
            "[aria-label*='Repost']",
        ]

        retweet_btn = None
        for selector in retweet_selectors:
            try:
                btn = tweet.locator(selector).first
                btn.wait_for(timeout=1000, state="visible")
                retweet_btn = btn
                break
            except PlaywrightTimeout:
                continue

        if not retweet_btn:
            logger.debug("Retweet button not found")
            return False

        # Click retweet button
        retweet_btn.click()
        time.sleep(random.uniform(0.5, 1))

        # Click "Repost" in the menu that appears
        try:
            confirm_btn = page.locator("div[data-testid='retweetConfirm']").first
            confirm_btn.wait_for(timeout=2000, state="visible")
            confirm_btn.click()
            time.sleep(random.uniform(1, 2))

            logger.info("[INFO] 🔁 Retweeted successfully!")
            return True
        except PlaywrightTimeout:
            logger.debug("Retweet confirm button not found")
            return False

    except PlaywrightError as exc:
        logger.debug(f"Failed to retweet: {exc}")
        return False


def generate_simple_image(topic: str, output_path: str, logger: logging.Logger) -> bool:
    """
    Generate a simple quote/text image for social media.
    SAFE: Falls back gracefully if PIL not available.
    NEW FUNCTION - doesn't touch any existing code!
    """
    try:
        if not PIL_AVAILABLE:
            logger.debug("PIL not available - skipping image generation")
            return False

        # Create image with gradient background
        width, height = 1200, 630  # Twitter optimal size

        # Create base image
        img = Image.new('RGB', (width, height), color='#1DA1F2')  # Twitter blue
        draw = ImageDraw.Draw(img)

        # Try to load a font, fallback to default if not available
        try:
            # Try common font locations
            font_paths = [
                "/System/Library/Fonts/Helvetica.ttc",  # Mac
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
                "C:\\Windows\\Fonts\\arial.ttf",  # Windows
            ]
            font = None
            for font_path in font_paths:
                if os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, 60)
                    break
            if not font:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        # Generate quote text
        quotes = [
            f"Building something amazing with {topic}",
            f"Leveling up my {topic} game",
            f"{topic} insights from the trenches",
            f"Shipping {topic} solutions daily",
            f"Exploring the future of {topic}",
        ]
        quote_text = random.choice(quotes)

        # Add text to image (centered)
        # Use textbbox instead of textsize for newer PIL versions
        try:
            bbox = draw.textbbox((0, 0), quote_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            # Fallback for older PIL versions
            text_width, text_height = draw.textsize(quote_text, font=font)

        x = (width - text_width) // 2
        y = (height - text_height) // 2

        # Add shadow for better readability
        draw.text((x + 3, y + 3), quote_text, font=font, fill='#00000080')  # Shadow
        draw.text((x, y), quote_text, font=font, fill='white')  # Main text

        # Save image
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, 'PNG', optimize=True)

        logger.debug(f"Generated image: {output_path}")
        return True

    except Exception as exc:
        logger.debug(f"Image generation failed (non-critical): {exc}")
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


def text_focus(text: str, *, max_length: int = 40) -> str:
    """Extract focus text from tweet, keeping it short to fit in reply templates."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned

    # Try to break at a sentence or phrase boundary
    truncated = cleaned[:max_length - 3]

    # Look for natural break points (sentence end, comma, etc)
    for break_char in ['.', '!', '?', ',', ';', '-']:
        last_break = truncated.rfind(break_char)
        if last_break > max_length // 2:  # Only use if it's not too early
            return truncated[:last_break + 1].strip()

    # Look for last complete word
    last_space = truncated.rfind(' ')
    if last_space > max_length // 2:
        return truncated[:last_space].strip() + "..."

    return truncated + "..."


def generate_original_post_content(topic: str) -> str:
    """Generate content for an original post about a topic."""
    post_templates = [
        "Been running {topic} sessions all week and honestly the difference is night and day when you find a platform that doesn't ghost you on withdrawals 💰",
        "Hot take on {topic}: Most sites overcomplicate it with sketchy terms. Found one that's actually transparent with their odds and bonuses hit different 🎯",
        "3 things that changed my {topic} game:\n1. Instant crypto deposits\n2. Provably fair games\n3. Rakeback that actually pays",
        "If you're serious about {topic}, stop settling for platforms that take forever to cash out. Time is money fr 🚀",
        "Real talk about {topic}: Been burned by too many sites with hidden fees. Now I only play where the payouts are instant and support is real 💯",
        "The biggest mistake I made with {topic}? Not checking if withdrawals were actually fast. Learned that the hard way 😅",
        "Finally found a platform for {topic} that doesn't pull shady stuff with bonuses. Game changer honestly 🔥",
        "{topic} tip: Always check if they're provably fair. Trust but verify, your wallet will thank you later 💸",
    ]

    template = random.choice(post_templates)
    content = template.format(topic=topic)

    # Add hashtags (70% chance)
    if random.random() < 0.7:
        hashtags = generate_hashtags(topic, max_hashtags=2)
        if len(content) + len(hashtags) + 1 <= 280:
            content = content + " " + hashtags

    return content


def generate_hashtags(topic: str, max_hashtags: int = 2) -> str:
    """Generate relevant hashtags based on topic."""
    # Topic-specific hashtag mapping
    hashtag_map = {
        "crypto gambling": ["#CryptoGambling", "#CryptoCasino", "#Bitcoin", "#Crypto", "#BTC"],
        "sports betting": ["#SportsBetting", "#Betting", "#Crypto", "#Gambling", "#Sportsbook"],
        "online slots": ["#OnlineSlots", "#Slots", "#CasinoGames", "#Gambling", "#Jackpot"],
        "casino games": ["#CasinoGames", "#OnlineCasino", "#Gambling", "#Crypto", "#Casino"],
        "poker": ["#Poker", "#CryptoPoker", "#OnlinePoker", "#Gambling", "#PokerLife"],
        "blackjack": ["#Blackjack", "#Casino", "#CardGames", "#Gambling", "#CryptoGambling"],
        "roulette": ["#Roulette", "#Casino", "#Gambling", "#OnlineCasino", "#CryptoGambling"],
        "dice games": ["#DiceGames", "#CryptoDice", "#Gambling", "#OnlineCasino", "#Crypto"],
        "crypto casino": ["#CryptoCasino", "#Crypto", "#Gambling", "#Bitcoin", "#OnlineGambling"],
        "stake alternatives": ["#CryptoCasino", "#OnlineGambling", "#Crypto", "#Gambling", "#Bitcoin"],
    }

    # Generic gambling/crypto hashtags as fallback
    generic_tags = ["#Crypto", "#Gambling", "#Bitcoin", "#OnlineCasino", "#CryptoCasino"]

    # Get topic-specific tags or use generic
    topic_lower = topic.lower()
    available_tags = []
    for key, tags in hashtag_map.items():
        if key.lower() in topic_lower or topic_lower in key.lower():
            available_tags = tags
            break

    if not available_tags:
        available_tags = generic_tags

    # Randomly select hashtags
    selected = random.sample(available_tags, min(max_hashtags, len(available_tags)))
    return " ".join(selected)


def check_automation_warning(page: Page, logger: logging.Logger) -> bool:
    """
    Check if Twitter is showing the automation warning.
    Returns True if warning detected, False otherwise.
    """
    try:
        automation_selectors = [
            "text=/looks like it might be automated/i",
            "text=/looks automated/i",
            "text=/automated/i",
            "text=/protect our users from spam/i",
        ]
        for selector in automation_selectors:
            if page.locator(selector).count() > 0:
                logger.error("🚨 AUTOMATION WARNING DETECTED - Twitter flagged this action!")
                return True
        return False
    except Exception:
        return False


def human_like_browsing(page: Page, logger: logging.Logger) -> None:
    """
    Simulate human browsing behavior: scroll, pause, occasionally like tweets.
    Makes the bot look like a real person browsing Twitter.
    """
    try:
        # Random scroll (70% chance)
        if random.random() < 0.7:
            scroll_amount = random.randint(300, 800)
            page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            logger.debug(f"📜 Scrolled {scroll_amount}px")
            time.sleep(random.uniform(1, 3))

        # Pause to "read" (50% chance)
        if random.random() < 0.5:
            pause = random.uniform(2, 6)
            logger.debug(f"👀 Reading for {pause:.1f}s")
            time.sleep(pause)

        # Randomly like a visible tweet (20% chance)
        if random.random() < 0.2:
            try:
                like_buttons = page.locator("button[data-testid='like']").all()
                if like_buttons:
                    # Pick a random like button from visible tweets
                    btn = random.choice(like_buttons[:5])  # Only from first 5 visible
                    if btn.is_visible():
                        btn.click()
                        logger.info("[INFO] ❤️ Liked a tweet (human-like behavior)")
                        time.sleep(random.uniform(0.5, 1.5))
            except Exception:
                pass  # Silent fail, not critical
    except Exception as exc:
        logger.debug(f"Browsing simulation error (non-critical): {exc}")


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
    attempts = 0
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

        # Bot/spam account detection
        handle = data["handle"] or ""
        if handle:
            # Check for excessive numbers in handle (common bot pattern)
            num_digits = sum(c.isdigit() for c in handle)
            if len(handle) > 0 and num_digits / len(handle) > 0.4:
                skip_reasons.append("bot-like-handle")

            # Check for very long random-looking handles
            if len(handle) > 20:
                skip_reasons.append("suspicious-handle-length")

        # Check for low-quality tweet patterns
        if text.count('http') > 3:  # Too many links
            skip_reasons.append("excessive-links")

        if skip_reasons:
            logger.info(
                "[INFO] Skipping tweet %s from @%s: reason=%s",
                data['id'],
                data['handle'] or 'unknown',
                ",".join(skip_reasons),
            )
            continue

        # FEATURE ADD: Conditional Reply Generation (political mode vs gambling mode)
        # If political mode enabled, use new composer; otherwise use old templates
        # To revert: set USE_NEW_CONFIG=false
        media_path_for_reply = None  # For potential image attachment

        if _political_mode_available and _political_composer:
            # NEW PATH: Political mode reply composer
            logger.debug("[political-mode] Using political reply composer")
            try:
                reply_result = _political_composer.compose_reply(
                    tweet_text=data["text"],
                    tweet_author=data["handle"] or "unknown",
                    topic=topic,
                    dry_run=False  # Actually generate media
                )

                if not reply_result['should_post']:
                    logger.info("[INFO] Political composer blocked tweet (safety check)")
                    continue

                message = reply_result['text']
                media_path_for_reply = reply_result.get('media_path')

            except Exception as exc:
                logger.error(f"[political-mode] Composer failed: {exc}, falling back to gambling templates")
                # Fall back to old method on error
                template = random.choice(config.reply_templates)
                message = template.format(
                    topic=topic,
                    focus=text_focus(data["text"]),
                    ref_link=config.referral_link or "",
                ).strip()
        else:
            # OLD PATH: Gambling mode templates (existing behavior)
            logger.debug("[gambling-mode] Using gambling reply templates")
            template = random.choice(config.reply_templates)
            message = template.format(
                topic=topic,
                focus=text_focus(data["text"]),
                ref_link=config.referral_link or "",
            ).strip()

        if not message:
            logger.warning("Generated empty reply. Skipping tweet.")
            continue

        # NOTE: No hashtags in replies in gambling mode - they look spammy
        # In political mode, hashtags handled by composer

        # Twitter/X has a 280 character limit
        if len(message) > 280:
            logger.warning("Message too long (%d chars), truncating to 280...", len(message))
            # Keep the referral link if present
            ref_link = config.referral_link or ""
            if ref_link and ref_link in message:
                # Truncate the text part but keep the link
                available_chars = 280 - len(ref_link) - 4  # -4 for "... "
                message_without_link = message.replace(ref_link, "").strip()
                if len(message_without_link) > available_chars:
                    message = message_without_link[:available_chars].strip() + "... " + ref_link
            else:
                message = message[:277] + "..."

        logger.info("[INFO] Replying to @%s for topic '%s'.", data['handle'] or 'unknown', topic)
        logger.debug("Generated message (%d chars): %s", len(message), message)
        if media_path_for_reply:
            logger.debug("[media] Reply will include media: %s", media_path_for_reply)

        attempts += 1
        if send_reply(page, tweet, message, logger, media_path=media_path_for_reply):
            registry.add(identifier)
            replies += 1
            success_rate = (replies / attempts) * 100
            logger.info("[INFO] ✓ Success! Stats: %d/%d replies (%.1f%% success rate)", replies, attempts, success_rate)
            video_service.maybe_generate(topic, data["text"])
            maybe_send_dm(config, page, data, logger)

            # Follow user occasionally (30% chance) to grow followers
            if random.random() < 0.3:
                logger.info("[INFO] 👥 Attempting to follow @%s...", data['handle'] or 'unknown')
                if follow_user(page, tweet, logger):
                    logger.info("[INFO] Successfully followed!")
                    time.sleep(random.uniform(2, 4))  # Extra delay after following
                else:
                    logger.debug("Follow skipped (already following or unavailable)")

            # Occasionally retweet to show support (15% chance - builds engagement)
            if random.random() < 0.15:
                logger.info("[INFO] 🔁 Attempting to retweet...")
                if retweet_post(page, tweet, logger):
                    time.sleep(random.uniform(1, 3))
                else:
                    logger.debug("Retweet skipped")

            # More human-like timing: occasionally take longer breaks (10% chance)
            if random.random() < 0.1:
                delay = random.randint(config.action_delay_max * 2, config.action_delay_max * 3)
                logger.info("[INFO] Taking a longer break to appear more natural (%s seconds)...", delay)
            else:
                delay = random.randint(config.action_delay_min, config.action_delay_max)
                logger.info("[INFO] Sleeping for %s seconds before next action.", delay)
            time.sleep(delay)
        else:
            success_rate = (replies / attempts) * 100
            logger.warning("✗ Reply attempt failed. Stats: %d/%d replies (%.1f%% success rate)", replies, attempts, success_rate)

        if replies >= config.max_replies_per_topic:
            logger.info(
                "[INFO] Reached MAX_REPLIES_PER_TOPIC=%s for '%s'. Moving to next topic.",
                config.max_replies_per_topic,
                topic,
            )
            logger.info("[INFO] Final stats for '%s': %d successful replies from %d attempts (%.1f%% success)",
                       topic, replies, attempts, (replies / attempts * 100) if attempts > 0 else 0)
            return


def get_trending_topics(page: Page, logger: logging.Logger) -> list[str]:
    """
    Get trending/controversial topics from Twitter's trending section.
    NEW FUNCTION - helps bot engage with viral content!
    """
    trending_topics = []
    try:
        # Go to explore page to see trending
        page.goto("https://x.com/explore/tabs/trending", wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)

        # Find trending topic elements
        trend_selectors = [
            "div[data-testid='trend']",
            "[data-testid='trend'] span",
        ]

        for selector in trend_selectors:
            try:
                trends = page.locator(selector).all()[:5]  # Get top 5
                for trend in trends:
                    text = trend.inner_text()
                    if text and len(text) > 2 and len(text) < 50:
                        trending_topics.append(text)
                        logger.debug(f"Found trending: {text}")
                if trending_topics:
                    break
            except:
                continue

        logger.info(f"[INFO] 🔥 Found {len(trending_topics)} trending topics")
        return trending_topics[:3]  # Return top 3
    except Exception as exc:
        logger.debug(f"Could not fetch trending topics: {exc}")
        return []


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
        logger.info("[INFO] Search page loaded for topic '%s'", topic)
    except PlaywrightTimeout:
        logger.warning("Timeout while loading topic '%s'.", topic)
        return
    except PlaywrightError as exc:
        logger.warning("Error while loading topic '%s': %s", topic, exc)
        return

    # Simulate human browsing before engaging (scroll, pause, maybe like)
    logger.debug("Simulating human browsing behavior...")
    human_like_browsing(page, logger)

    tweets = load_tweets(page, logger)
    logger.info("[INFO] Loaded %s tweets for topic '%s'.", len(tweets), topic)
    if not tweets:
        logger.warning("No eligible tweets for topic '%s'.", topic)
        return

    # Another brief browsing moment before starting to reply
    if random.random() < 0.5:
        human_like_browsing(page, logger)

    process_tweets(config, registry, page, video_service, tweets, topic, logger)


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    logger: logging.Logger,
) -> None:
    # FEATURE ADD: Override search topics when political mode is enabled
    if _political_mode_available and _political_config:
        active_mode = _political_config.get_active_mode()
        political_topics = _political_config.get_topics_for_mode(active_mode)

        if political_topics:
            logger.info("=" * 60)
            logger.info("[political-mode] ✅ POLITICAL MODE ACTIVE - Mode: %s", active_mode)
            logger.info("[political-mode] Overriding search topics with political topics")
            logger.info("[political-mode] OLD topics: %s", config.search_topics[:3])
            config.search_topics = political_topics
            logger.info("[political-mode] NEW topics: %s", config.search_topics[:3])
            logger.info("=" * 60)
        else:
            logger.warning("[political-mode] No political topics configured, using default topics")
    else:
        logger.info("[gambling-mode] Using gambling mode topics")

    logger.info("[INFO] Starting engagement loop with %s topic(s).", len(config.search_topics))
    logger.info("[INFO] Topics: %s", ", ".join(config.search_topics[:5]))

    cycle_count = 0
    while True:
        cycle_count += 1
        logger.info("[INFO] 🔄 Starting cycle #%d", cycle_count)

        try:
            if page.is_closed():
                logger.warning("⚠️ Browser page closed. Exiting engagement loop.")
                return
        except PlaywrightError as exc:
            logger.warning("⚠️ Browser page unavailable: %s. Exiting engagement loop.", exc)
            return

        if config.search_topics:
            # Create original posts to build presence (100% - always post with images!)
            if True:  # Always post to show features working
                # Random delay before posting (10-30 seconds - human-like)
                delay = random.randint(10, 30)
                logger.info("[INFO] 😴 Taking a %d second break before posting...", delay)
                time.sleep(delay)

                selected_topic = random.choice(config.search_topics)
                logger.info("[INFO] 📝 Creating original post about '%s'...", selected_topic)
                post_content = generate_original_post_content(selected_topic)

                # Always generate an image (100% to show it's working!)
                image_path = None
                if True:  # Always include image
                    image_dir = Path.home() / ".social_agent_codex" / "generated_images"
                    image_dir.mkdir(parents=True, exist_ok=True)
                    image_path = str(image_dir / f"post_{int(time.time())}.png")

                    logger.info("[INFO] 🎨 Generating AI image...")
                    if generate_simple_image(selected_topic, image_path, logger):
                        logger.info("[INFO] ✓ Image generated!")
                    else:
                        logger.debug("Image generation skipped or failed (posting text-only)")
                        image_path = None  # Post without image

                if create_original_post(page, post_content, logger, image_path):
                    logger.info("[INFO] ✅ Original post created%s! Taking a short break...",
                               " with image" if image_path else "")
                    time.sleep(random.randint(30, 60))

                    # Clean up image file after posting
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                            logger.debug("Cleaned up generated image")
                        except Exception:
                            pass
                else:
                    logger.warning("Failed to create original post, continuing...")

            # Now engage with topics (reply to tweets and follow users)
            try:
                # Get trending/controversial topics to engage with (every 3rd cycle)
                all_topics = list(config.search_topics)
                if cycle_count % 3 == 0:
                    logger.info("[INFO] 🔥 Fetching trending topics to join the conversation...")
                    trending = get_trending_topics(page, logger)
                    if trending:
                        all_topics.extend(trending)
                        logger.info(f"[INFO] Added {len(trending)} trending topics to engage with!")

                for i, topic in enumerate(all_topics):
                    handle_topic(config, registry, page, video_service, topic, logger)

                    # Between topics, simulate casual browsing (not after last topic)
                    if i < len(all_topics) - 1:
                        # Random delay between topics (30-90 seconds - human-like)
                        delay = random.randint(30, 90)
                        logger.info("[INFO] 😴 Taking a %d second break between topics...", delay)
                        time.sleep(delay)

                        # Scroll and browse a bit
                        if random.random() < 0.6:
                            human_like_browsing(page, logger)
            except Exception as e:
                if "AUTOMATION_WARNING_DETECTED" in str(e):
                    logger.error("🚨🚨🚨 AUTOMATION WARNING DETECTED 🚨🚨🚨")
                    logger.error("Twitter flagged this activity as automated!")
                    logger.error("Entering 30 MINUTE COOLDOWN to let account settle...")
                    time.sleep(1800)  # 30 minutes = 1800 seconds
                    logger.info("✅ 30 minute cooldown complete - will try again next cycle")
                else:
                    # Some other error - log it but continue
                    logger.error(f"Error during topic handling: {e}")
        else:
            logger.info("No search topics configured. Sleeping before next cycle.")

        logger.info("[INFO] Cycle #%d complete. Sleeping for %s seconds.", cycle_count, config.loop_delay_seconds)
        try:
            time.sleep(config.loop_delay_seconds)
            logger.info("[INFO] ⏰ Sleep finished! Restarting engagement cycle...")
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

    user_data_dir = str(Path.home() / ".social_agent_codex/chrome_profile/")
    os.makedirs(user_data_dir, exist_ok=True)

    # Try Chrome first (to avoid Google detection), fall back to Chromium if not available
    context = None
    try:
        # Use actual Chrome browser with persistent profile
        # Hide automation to pass Google's security checks
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",  # Use real Chrome to avoid Google blocking
            headless=config.headless,
            args=[
                "--start-maximized",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # Hide automation from Google
                "--disable-dev-shm-usage",
            ],
        )
        browser = None  # persistent context doesn't have a browser object
        logger.info("[INFO] Launched Chrome browser with persistent profile at %s", user_data_dir)
    except PlaywrightError as chrome_error:
        logger.warning("Chrome not available (%s), trying Chromium...", chrome_error)
        try:
            # Fallback to Chromium if Chrome isn't installed
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=config.headless,
                args=[
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            browser = None
            logger.info("[INFO] Launched Chromium browser with persistent profile at %s", user_data_dir)
        except PlaywrightError as chromium_error:
            logger.error("Failed to launch browser: Chrome error: %s, Chromium error: %s", chrome_error, chromium_error)
            return None

    storage_file = auth_path
    page = context.new_page()

    # Hide webdriver property to make browser look real to Google
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)

    # Check if already logged in
    try:
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        logger.warning("Timeout while loading X.com")
    except (PlaywrightError, TargetClosedError) as exc:
        logger.warning("Error while loading X.com: %s", exc)

    if is_logged_in(page):
        logger.info("[INFO] Already logged in - session persisted from Chrome profile!")
        return browser, context, page

    # Not logged in - go to login page and wait for manual login
    logger.info("[INFO] Not logged in yet - opening login page for manual login")
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


def run_dry_run_test() -> None:
    """
    --dry-run mode: Test political reply composer without posting or touching auth/login.
    Simulates reply generation against hardcoded sample tweets.
    """
    # load_dotenv() already called at module level (line 43)

    # Check if political mode is enabled
    use_new_config = os.getenv("USE_NEW_CONFIG", "false").lower() == "true"

    if not use_new_config:
        print("❌ Dry run requires USE_NEW_CONFIG=true in .env")
        print("   Political mode is currently disabled.")
        sys.exit(1)

    print("🧪 DRY RUN MODE: Testing political reply composer\n")
    print("=" * 60)

    try:
        from app.config_loader import get_config
        from app.reply.compose import ReplyComposer
        from app.media.image_adapter import ImageAdapter
        from app.media.video_adapter import VideoAdapter
        from app.engagement.politics_reply import PoliticalReplyGenerator

        config = get_config()
        print(f"✓ Config loaded: {len(config.config.get('modes', []))} modes")
        print(f"  Promo frequency: {config.config.get('promo_frequency', 0.0)*100:.0f}%")
        print(f"  Media probability: {config.config.get('media_probability', 0.0)*100:.0f}%\n")

        # Initialize composer
        image_adapter = ImageAdapter()
        video_adapter = VideoAdapter()
        politics_gen = PoliticalReplyGenerator(config)
        composer = ReplyComposer(config, image_adapter, video_adapter, politics_gen)

        print(f"✓ Image generation: {'ENABLED' if image_adapter.enabled else 'DISABLED (PIL not available)'}")
        print(f"✓ Video generation: {'ENABLED' if video_adapter.enabled else 'DISABLED (no API key)'}\n")

        # Test cases
        test_tweets = [
            {
                "text": "The new infrastructure bill is completely unnecessary. Government spending is out of control.",
                "author": "test_user_1",
                "topic": "politics"
            },
            {
                "text": "AI is going to replace most jobs in the next 5 years. Nobody is prepared for this.",
                "author": "test_user_2",
                "topic": "tech"
            },
            {
                "text": "Breaking: Fed announces new interest rate policy affecting millions",
                "author": "test_user_3",
                "topic": "economics"
            }
        ]

        print("=" * 60)
        print("TESTING REPLY GENERATION:\n")

        for i, tweet in enumerate(test_tweets, 1):
            print(f"\n--- Test {i}/3: {tweet['topic'].upper()} ---")
            print(f"Tweet: \"{tweet['text'][:70]}...\"")
            print(f"Author: @{tweet['author']}\n")

            result = composer.compose_reply(
                tweet_text=tweet['text'],
                tweet_author=tweet['author'],
                topic=tweet['topic'],
                dry_run=False  # Generate media for testing
            )

            if result['should_post']:
                print(f"✓ Reply: \"{result['text']}\"")
                print(f"  Length: {len(result['text'])} chars")
                if result.get('media_path'):
                    print(f"  Media: {result['media_path']} (would be attached)")
                else:
                    print(f"  Media: None (text-only)")

                # Check for link
                gumroad_link = config.config.get('promo_links', {}).get('gumroad', '')
                if gumroad_link and gumroad_link in result['text']:
                    print(f"  Promo: ✓ Gumroad link included")
                else:
                    print(f"  Promo: None")
            else:
                print(f"✗ Reply BLOCKED (safety check)")

        # Test link frequency (simulate 20 replies)
        print("\n" + "=" * 60)
        print("TESTING PROMO LINK FREQUENCY (20 samples):\n")

        sample_tweet = test_tweets[0]
        link_count = 0
        media_count = 0

        for _ in range(20):
            result = composer.compose_reply(
                tweet_text=sample_tweet['text'],
                tweet_author=sample_tweet['author'],
                topic=sample_tweet['topic'],
                dry_run=True  # Don't actually generate media 20 times
            )

            if result['should_post']:
                gumroad_link = config.config.get('promo_links', {}).get('gumroad', '')
                if gumroad_link and gumroad_link in result['text']:
                    link_count += 1
                if result.get('media_path'):
                    media_count += 1

        link_percent = (link_count / 20) * 100
        media_percent = (media_count / 20) * 100
        expected_link = config.config.get('promo_frequency', 0.25) * 100
        expected_media = config.config.get('media_probability', 0.25) * 100

        print(f"Promo links: {link_count}/20 ({link_percent:.0f}%) - Expected: ~{expected_link:.0f}%")
        print(f"Media generated: {media_count}/20 ({media_percent:.0f}%) - Expected: ~{expected_media:.0f}%")

        # Validate
        if abs(link_percent - expected_link) <= 15:  # ±15% tolerance
            print("✓ Link frequency within acceptable range")
        else:
            print("⚠ Link frequency outside expected range")

        if abs(media_percent - expected_media) <= 15:  # ±15% tolerance
            print("✓ Media frequency within acceptable range")
        else:
            print("⚠ Media frequency outside expected range")

        print("\n" + "=" * 60)
        print("✓ DRY RUN COMPLETE - No posts made, no login required")
        print("  To run the bot: python social_agent.py (without --dry-run)")

    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Political mode modules may not be available")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error during dry run: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def run_social_agent() -> None:
    # load_dotenv() already called at module level (line 43)
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
    parser = argparse.ArgumentParser(
        description="Social engagement bot with political mode support"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test reply composer without posting or requiring login (requires USE_NEW_CONFIG=true)"
    )
    args = parser.parse_args()

    try:
        if args.dry_run:
            run_dry_run_test()
        else:
            run_social_agent()
    except KeyboardInterrupt:
        logging.getLogger("social_agent").info("Shutdown requested by user.")
        sys.exit(0)
