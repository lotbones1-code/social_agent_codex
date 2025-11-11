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


def send_reply(page: Page, tweet: Locator, message: str, logger: logging.Logger) -> bool:
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

        # Type message
        logger.debug("Typing original post...")
        composer.click()
        time.sleep(random.uniform(0.3, 0.7))
        page.keyboard.type(message, delay=random.randint(10, 30))
        time.sleep(random.uniform(0.5, 1.5))

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

        # Click post button
        logger.debug("Looking for send button...")
        send_btn = page.locator("button[data-testid='tweetButton']").first
        try:
            send_btn.wait_for(timeout=3000, state="visible")
            logger.debug("Send button found")
        except PlaywrightTimeout:
            logger.warning("Send button not visible for original post")
            return False

        logger.debug("Posting tweet...")
        send_btn.click(force=True)
        time.sleep(3)

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
    Follow a user from their tweet.
    NEW FUNCTION - completely separate from reply code!
    """
    try:
        # Find the Follow button within the tweet
        logger.debug("Looking for Follow button...")

        # Try multiple strategies to find the Follow button
        follow_selectors = [
            # Most common - inside the tweet card
            "div[data-testid='follow']",
            "button[data-testid='follow']",

            # Sometimes in User-Name area
            "div[data-testid='User-Name'] button[data-testid='follow']",
            "div[data-testid='User-Name'] div[data-testid='follow']",

            # Text-based fallbacks
            "button:has-text('Follow'):not(:has-text('Following'))",
            "div[role='button']:has-text('Follow'):not(:has-text('Following'))",

            # Aria label approach
            "button[aria-label*='Follow']",
        ]

        follow_btn = None
        for selector in follow_selectors:
            try:
                btn = tweet.locator(selector).first
                btn.wait_for(timeout=1500, state="visible")

                # Get button text to verify it's "Follow" not "Following"
                try:
                    btn_text = btn.inner_text()
                    logger.debug(f"Found button with selector {selector}, text: '{btn_text}'")

                    # Make sure it's Follow, not Following
                    if "following" in btn_text.lower() and "follow" in btn_text.lower():
                        logger.debug("Button says 'Following' - already following this user")
                        continue

                    if "follow" in btn_text.lower():
                        follow_btn = btn
                        logger.debug(f"✓ Follow button confirmed with selector: {selector}")
                        break
                except Exception:
                    # If we can't get text, try the button anyway
                    follow_btn = btn
                    logger.debug(f"Follow button found (no text check): {selector}")
                    break

            except PlaywrightTimeout:
                continue
            except PlaywrightError:
                continue

        if not follow_btn:
            # Debug: Show what buttons ARE visible in the tweet
            try:
                all_buttons = tweet.locator("button, div[role='button']").all()
                logger.debug(f"DEBUG: Found {len(all_buttons)} buttons/clickables in tweet")
                for i, btn in enumerate(all_buttons[:5]):  # Show first 5
                    try:
                        text = btn.inner_text() or ""
                        testid = btn.get_attribute("data-testid") or "no-testid"
                        aria = btn.get_attribute("aria-label") or "no-aria"
                        logger.debug(f"  Button {i+1}: text='{text[:20]}', testid='{testid}', aria='{aria[:30]}'")
                    except:
                        pass
            except:
                pass

            logger.debug("No Follow button found (already following or profile issue)")
            return False

        logger.debug("Clicking Follow button...")
        follow_btn.click(force=True)
        time.sleep(random.uniform(1.5, 2.5))

        logger.info("[INFO] ✓ Followed user successfully!")
        return True

    except PlaywrightError as exc:
        logger.debug(f"Failed to follow user: {exc}")
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
        "Just discovered an interesting approach to {topic}. The key is focusing on practical implementation over theory. 🚀",
        "Hot take: Most people overcomplicate {topic}. Start simple, iterate fast, measure results. That's it.",
        "3 lessons I learned about {topic} this week:\n1. Start small\n2. Test everything\n3. Double down on what works",
        "If you're working on {topic}, here's what actually moves the needle: consistent execution > perfect strategy.",
        "Quick thought on {topic}: The difference between good and great is often just persistence and attention to detail.",
        "Real talk about {topic}: It's not about having the best tools, it's about using what you have effectively.",
        "The biggest mistake I see with {topic}? Trying to do everything at once. Focus wins every time.",
        "{topic} tip: Measure twice, cut once. Data-driven decisions beat gut feelings 9 times out of 10.",
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
        "AI automation": ["#AI", "#Automation", "#ArtificialIntelligence", "#MachineLearning", "#AITools"],
        "growth hacking": ["#GrowthHacking", "#Growth", "#Marketing", "#Startup", "#ScaleUp"],
        "product launches": ["#ProductLaunch", "#NewProduct", "#Innovation", "#Startup", "#Tech"],
    }

    # Generic tech/business hashtags as fallback
    generic_tags = ["#Tech", "#Business", "#Innovation", "#Productivity", "#Digital"]

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

        template = random.choice(config.reply_templates)
        message = template.format(
            topic=topic,
            focus=text_focus(data["text"]),
            ref_link=config.referral_link or "",
        ).strip()

        if not message:
            logger.warning("Generated empty reply. Skipping tweet.")
            continue

        # NOTE: No hashtags in replies - they look spammy
        # Hashtags only in original posts where they look natural

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

        attempts += 1
        if send_reply(page, tweet, message, logger):
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
            for topic in config.search_topics:
                handle_topic(config, registry, page, video_service, topic, logger)

            # Create 1 original post per cycle (20% chance to keep it natural)
            if random.random() < 0.2:
                selected_topic = random.choice(config.search_topics)
                logger.info("[INFO] 📝 Creating original post about '%s'...", selected_topic)
                post_content = generate_original_post_content(selected_topic)

                # Try to generate an image (50% of posts, SAFE: fails gracefully)
                image_path = None
                if random.random() < 0.5:
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

    try:
        user_data_dir = str(Path.home() / ".social_agent_codex/chrome_profile/")
        os.makedirs(user_data_dir, exist_ok=True)

        # Use Chromium browser with persistent profile
        # Hide automation to pass Google's security checks
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
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
    except PlaywrightError as exc:
        logger.error("Failed to launch Chrome browser: %s", exc)
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
