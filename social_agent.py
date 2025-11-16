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
    dm_trigger_length: int
    video_provider: str
    video_model: str
    enable_video: bool
    auth_file: str
    # OpenAI settings
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    enable_ai_replies: bool = False
    ai_reply_rate: float = 0.3
    # Product/sales settings for AI replies
    product_name: str = "Social Agent Codex Bot"
    product_short_pitch: str = "An AI-powered X engagement bot that auto-replies to relevant tweets."
    product_cta: str = "DM me '5223' and I'll send you the link + setup guide."
    dm_access_code: str = "5223"
    reply_tone: str = "casual"
    growth_goal: str = "sales_and_followers"
    # Original posts settings
    enable_original_posts: bool = False
    original_post_interval_minutes: int = 90
    # Auto-follow settings
    enable_auto_follow: bool = False
    max_auto_follows_per_cycle: int = 10
    # DM settings (extended)
    max_dms_per_cycle: int = 5
    # Hashtags for original posts
    primary_hashtags: list[str] = None
    secondary_hashtags: list[str] = None


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
    dm_trigger_length = _parse_int("DM_TRIGGER_LENGTH", 220)

    x_username = (os.getenv("X_USERNAME") or "").strip() or None
    x_password = (os.getenv("X_PASSWORD") or "").strip() or None

    video_provider_raw = (os.getenv("VIDEO_PROVIDER") or "none").strip()
    video_provider = video_provider_raw.lower()
    video_model = (os.getenv("VIDEO_MODEL") or "").strip()
    enable_video = video_provider not in {"", "none", "disabled"}

    auth_file = (os.getenv("AUTH_FILE") or DEFAULT_AUTH_FILE).strip() or DEFAULT_AUTH_FILE

    # OpenAI settings
    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or None
    openai_model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    enable_ai_replies = _parse_bool(os.getenv("ENABLE_AI_REPLIES"), default=False)
    ai_reply_rate = _parse_float("AI_REPLY_RATE", 0.3)

    # Product/sales settings
    product_name = (os.getenv("PRODUCT_NAME") or "Social Agent Codex Bot").strip()
    product_short_pitch = (os.getenv("PRODUCT_SHORT_PITCH") or "An AI-powered X engagement bot that auto-replies to relevant tweets.").strip()
    product_cta = (os.getenv("PRODUCT_CTA") or "DM me '5223' and I'll send you the link + setup guide.").strip()
    dm_access_code = (os.getenv("DM_ACCESS_CODE") or "5223").strip()
    reply_tone = (os.getenv("REPLY_TONE") or "casual").strip()
    growth_goal = (os.getenv("GROWTH_GOAL") or "sales_and_followers").strip()

    # Original posts settings
    enable_original_posts = _parse_bool(os.getenv("ENABLE_ORIGINAL_POSTS"), default=False)
    original_post_interval_minutes = _parse_int("ORIGINAL_POST_INTERVAL_MINUTES", 90)

    # Auto-follow settings
    enable_auto_follow = _parse_bool(os.getenv("ENABLE_AUTO_FOLLOW"), default=False)
    max_auto_follows_per_cycle = _parse_int("MAX_AUTO_FOLLOWS_PER_CYCLE", 10)

    # Extended DM settings
    max_dms_per_cycle = _parse_int("MAX_DMS_PER_CYCLE", 5)

    # Hashtags for original posts
    primary_hashtags = _split_env("PRIMARY_HASHTAGS")
    secondary_hashtags = _split_env("SECONDARY_HASHTAGS")

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
        dm_trigger_length=dm_trigger_length,
        video_provider=video_provider,
        video_model=video_model,
        enable_video=enable_video,
        auth_file=auth_file,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        enable_ai_replies=enable_ai_replies,
        ai_reply_rate=ai_reply_rate,
        product_name=product_name,
        product_short_pitch=product_short_pitch,
        product_cta=product_cta,
        dm_access_code=dm_access_code,
        reply_tone=reply_tone,
        growth_goal=growth_goal,
        enable_original_posts=enable_original_posts,
        original_post_interval_minutes=original_post_interval_minutes,
        enable_auto_follow=enable_auto_follow,
        max_auto_follows_per_cycle=max_auto_follows_per_cycle,
        max_dms_per_cycle=max_dms_per_cycle,
        primary_hashtags=primary_hashtags,
        secondary_hashtags=secondary_hashtags,
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
        # Scroll tweet into view first
        logger.info("[DEBUG] Scrolling tweet into view...")
        tweet.scroll_into_view_if_needed(timeout=5000)
        time.sleep(0.5)

        # Hover over tweet to reveal action buttons
        logger.info("[DEBUG] Hovering over tweet...")
        tweet.hover()
        time.sleep(0.3)

        # Try multiple possible selectors for reply button
        logger.info("[DEBUG] Looking for reply button...")
        reply_button = None

        # Try different selectors
        selectors = [
            "div[data-testid='reply']",
            "button[data-testid='reply']",
            "[aria-label*='Reply']",
            "[aria-label*='reply']",
        ]

        for selector in selectors:
            try:
                btn = tweet.locator(selector).first
                if btn.count() > 0:
                    reply_button = btn
                    logger.info(f"[DEBUG] Found reply button with selector: {selector}")
                    break
            except:
                continue

        if not reply_button:
            logger.warning("Reply button not found with any selector - skipping tweet")
            return False

        # Click reply button
        logger.info("[DEBUG] Clicking reply button...")
        reply_button.click(timeout=5000)
        time.sleep(2)  # Give modal time to open

        # Wait for composer to appear
        logger.info("[DEBUG] Waiting for composer...")
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=15000, state="visible")

        logger.info("[DEBUG] Clicking composer...")
        composer.click()
        time.sleep(1)

        # Type message using keyboard (works better for contenteditable divs)
        logger.info("[DEBUG] Typing message with keyboard...")
        page.keyboard.type(message, delay=10)  # Faster typing: 10ms instead of 30ms
        time.sleep(1.5)

        logger.info(f"[DEBUG] Message typed: {message[:50]}...")

        # Click post button - try multiple selectors
        logger.info("[DEBUG] Clicking post button...")
        post_button = None

        post_selectors = [
            "button[data-testid='tweetButton']",
            "div[data-testid='tweetButton']",
            "button[data-testid='tweetButtonInline']",
            "div[data-testid='tweetButtonInline']",
            "[aria-label*='Post']",
            "[aria-label*='Reply']",
        ]

        for selector in post_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=1000):
                    post_button = btn
                    logger.info(f"[DEBUG] Found post button with selector: {selector}")
                    break
            except:
                continue

        if post_button:
            try:
                post_button.click(timeout=5000)
                time.sleep(4)
                logger.info("[INFO] Reply posted successfully.")
                return True
            except:
                logger.info("[DEBUG] Click failed, trying keyboard shortcut...")

        # Fallback: use keyboard shortcut (Cmd+Enter or Ctrl+Enter)
        logger.info("[DEBUG] Using keyboard shortcut to post...")
        try:
            # Detect if Mac
            is_mac = page.evaluate("() => navigator.platform.includes('Mac')")
            if is_mac:
                page.keyboard.press("Meta+Enter")
            else:
                page.keyboard.press("Control+Enter")
            time.sleep(4)
            logger.info("[INFO] Reply posted successfully via keyboard shortcut.")
            return True
        except Exception as e:
            logger.warning(f"Keyboard shortcut failed: {str(e)[:50]}")

        return False
    except PlaywrightTimeout as exc:
        logger.warning("Timeout while composing reply: %s", str(exc)[:100])
    except PlaywrightError as exc:
        logger.warning("Failed to send reply: %s", str(exc)[:100])
    return False


def maybe_send_dm(config: BotConfig, page: Page, tweet_data: dict[str, str], logger: logging.Logger, dm_count: dict) -> None:
    """Send a personalized DM using ChatGPT if the tweet meets interest criteria."""
    if not config.enable_dms:
        return

    # Check if we've hit the DM limit for this cycle
    if dm_count.get("count", 0) >= config.max_dms_per_cycle:
        return

    if not config.openai_api_key:
        logger.info("[DM] Skipped - OpenAI API key not configured")
        return

    # Calculate interest score (from original DM logic)
    tweet_text = tweet_data.get("text", "")
    text_lower = tweet_text.lower()

    # Base interest from keyword matches
    keyword_matches = sum(1 for kw in config.relevant_keywords if kw in text_lower)

    # Add weight for questions
    question_indicators = ["?", "how to", "how do", "what is", "where can", "any tips", "help me"]
    has_question = any(q in text_lower for q in question_indicators)
    question_bonus = config.dm_question_weight if has_question else 0

    # Add weight for longer tweets (more engagement signals)
    length_bonus = min(len(tweet_text) / config.dm_trigger_length, 1.0) if config.dm_trigger_length > 0 else 0

    interest_score = keyword_matches + question_bonus + length_bonus

    if interest_score < config.dm_interest_threshold:
        logger.info("[DM] Interest score %.2f < threshold %.2f - skipping", interest_score, config.dm_interest_threshold)
        return

    handle = tweet_data.get("handle", "")
    if not handle:
        return

    logger.info("[DM] Interest score %.2f - generating DM for @%s", interest_score, handle)

    # Generate personalized DM using ChatGPT
    messages = build_dm_messages(tweet_text, handle, config)
    dm_text = generate_ai_content(messages, config, logger, max_tokens=300)

    if not dm_text:
        logger.warning("[DM] Failed to generate DM content")
        return

    logger.info("[DM] Generated DM for @%s: %s", handle, dm_text[:80])

    # Send the DM via Twitter UI
    try:
        # Navigate to DM compose URL
        dm_url = f"https://x.com/messages/compose?recipient_id={handle}"
        page.goto(dm_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Find the message input box
        message_selectors = [
            "div[data-testid='dmComposerTextInput']",
            "div[aria-label='Message']",
            "div[contenteditable='true'][data-testid*='message']",
        ]

        message_box = None
        for selector in message_selectors:
            try:
                box = page.locator(selector).first
                if box.count() > 0 and box.is_visible(timeout=3000):
                    message_box = box
                    break
            except:
                continue

        if not message_box:
            logger.warning("[DM] Could not find message input box")
            return

        # Click and type DM
        message_box.click()
        time.sleep(1)
        page.keyboard.type(dm_text, delay=15)
        time.sleep(2)

        # Click send button
        send_selectors = [
            "button[data-testid='dmComposerSendButton']",
            "div[data-testid='dmComposerSendButton']",
            "[aria-label*='Send']",
        ]

        for selector in send_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    time.sleep(2)
                    logger.info("[DM] Successfully sent DM to @%s", handle)
                    dm_count["count"] = dm_count.get("count", 0) + 1
                    return
            except:
                continue

        logger.warning("[DM] Could not find send button")

    except PlaywrightError as exc:
        logger.warning("[DM] Failed to send DM to @%s: %s", handle, str(exc)[:100])


def build_reply_messages(tweet_text: str, topic: str, handle: str, config: BotConfig) -> list[dict]:
    """Build ChatGPT messages for AI-powered reply generation with better sales prompts."""
    system_prompt = f"""You are a human X (Twitter) growth operator.

Product you are softly promoting:
- Name: {config.product_name}
- What it does: {config.product_short_pitch}
- How to get it: {config.product_cta}
- DM access code: {config.dm_access_code}

Goals (in this order):
1. Add **real value** to the conversation so the author and readers see you as sharp, useful, and not a bot.
2. Build trust and curiosity around you and your product.
3. Sometimes (not always) create **soft sales opportunities** and drive DMs or clicks.

Style rules:
- Tone: {config.reply_tone}, confident, like a young entrepreneur who actually does this in real life.
- Reply as a **real person**, never mention being an AI or bot.
- Use **normal punctuation**. Avoid starting or ending most replies with "—" or "...".
- No weird repetitive patterns: don't structure every reply the same way, don't always end with the same phrase.
- 1–3 sentences max. Short, punchy, specific.
- If you use emojis, keep it to 0–2 per reply and only when they naturally fit.
- Avoid fake generic phrases like "great point" or "this is so interesting" unless followed by a specific insight.

Promotion behavior:
- ~70% of replies: pure value, no pitch.
- ~30% of replies: soft plug at the **end**, for example:
  - "I've been automating this with {config.product_name} and it's been insane for growth."
  - "If you want my exact setup, DM me '{config.dm_access_code}' and I'll send it."
- The plug should **never** be the whole reply. Always give value first.

General behavior:
- Always anchor the reply on the actual tweet content and topic.
- Focus on specific, tactical ideas: a step, a framework, an angle, not vague motivation.
- Don't be hostile or cringe; direct is fine, but not toxic.
""".strip()

    user_content = f"""Tweet text:
\"\"\"{tweet_text}\"\"\"

Topic: {topic}
Author handle: @{handle}

Write ONE reply that follows the system instructions.
Output ONLY the reply text that should be posted on X, nothing else.""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def build_original_post_messages(config: BotConfig, topic: str) -> list[dict]:
    """Build ChatGPT messages for generating original tweets."""
    primary_tags = ", ".join(config.primary_hashtags) if config.primary_hashtags else "ai, automation, growth, sidehustle"
    secondary_tags = ", ".join(config.secondary_hashtags) if config.secondary_hashtags else "buildinpublic, xgrowth, content"

    system_prompt = f"""You are a content creator on X (Twitter) focused on {config.growth_goal}.
You want to grow followers AND sell {config.product_name}.

Product:
- What it does: {config.product_short_pitch}
- CTA: {config.product_cta}
- DM access code: {config.dm_access_code}

Style rules:
- Tone: {config.reply_tone}, confident, slightly opinionated, not cringe.
- Write **one original tweet**, not a thread.
- Use a strong hook in the first line that would make someone stop scrolling.
- Teach a quick insight, framework, or punchy take related to: {topic}.
- At most 1 subtle mention of your product in the middle or at the end.
- Use 2–4 relevant hashtags at the **end** of the tweet, not in the middle of sentences.
- Prefer hashtags from:
  - Primary: {primary_tags}
  - Secondary: {secondary_tags}
- Do NOT use the exact same hashtags every time; rotate and mix them.

Format:
- No intro text, no explanations.
- Just output the tweet exactly as it should appear on X.""".strip()

    user_content = f"""Generate one tweet about topic: {topic}.
Make it optimized for engagement AND aligned with selling {config.product_name}.
Remember to add hashtags at the end only.""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def build_dm_messages(tweet_text: str, handle: str, config: BotConfig) -> list[dict]:
    """Build ChatGPT messages for generating personalized DMs."""
    system_prompt = f"""You are writing a DM on X (Twitter) to someone who looks like a good fit for {config.product_name}.

Product:
- What it does: {config.product_short_pitch}
- CTA: {config.product_cta}
- DM access code: {config.dm_access_code}

Goals:
1. Be respectful and non-spammy.
2. Show you actually read their tweet.
3. Make a short, clear offer that feels personal, not like a mass blast.

Style:
- 2–4 short lines.
- No fake hype. Sound like a real builder talking to another builder.
- No "hey [name]" + generic pitch. Reference something specific they said.
- You can mention:
  - "If you DM me '{config.dm_access_code}', I'll send you the full breakdown / setup."

You are NOT allowed to mention being an AI or a bot.""".strip()

    user_content = f"""Their tweet:
\"\"\"{tweet_text}\"\"\"

Their handle: @{handle}

Write a short DM that follows the system instructions.
Output ONLY the DM content, with line breaks where appropriate.""".strip()

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def generate_ai_reply(config: BotConfig, tweet_text: str, topic: str, handle: str, logger: logging.Logger) -> Optional[str]:
    """Generate an AI-powered reply using OpenAI ChatGPT API."""
    if not config.enable_ai_replies:
        return None

    if not config.openai_api_key:
        logger.warning("AI replies enabled but OPENAI_API_KEY not configured. Falling back to templates.")
        return None

    try:
        import json as json_lib
        import urllib.request

        messages = build_reply_messages(tweet_text, topic, handle, config)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.openai_api_key}",
        }

        data = {
            "model": config.openai_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 280,
        }

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json_lib.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json_lib.loads(response.read().decode("utf-8"))
            reply_text = result["choices"][0]["message"]["content"].strip()
            logger.info("[AI] Generated reply using %s", config.openai_model)
            return reply_text

    except Exception as exc:  # noqa: BLE001
        logger.warning("AI reply generation failed: %s. Falling back to templates.", exc)
        return None


def text_focus(text: str, *, max_length: int = 50) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    # Truncate without adding "..." to avoid repetitive formatting
    return cleaned[:max_length].rstrip()


def generate_ai_content(messages: list[dict], config: BotConfig, logger: logging.Logger, *, max_tokens: int = 280) -> Optional[str]:
    """General helper to call ChatGPT API with given messages."""
    if not config.openai_api_key:
        return None

    try:
        import json as json_lib
        import urllib.request

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.openai_api_key}",
        }

        data = {
            "model": config.openai_model,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": max_tokens,
        }

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json_lib.dumps(data).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json_lib.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()
            return content

    except Exception as exc:  # noqa: BLE001
        logger.warning("AI content generation failed: %s", exc)
        return None


def maybe_post_original_tweet(config: BotConfig, page: Page, logger: logging.Logger, last_post_time: dict) -> None:
    """Post an original tweet if enough time has passed since last post."""
    if not config.enable_original_posts:
        return

    if not config.openai_api_key:
        logger.info("[ORIGINAL POST] Skipped - OpenAI API key not configured")
        return

    # Check if enough time has passed
    now = time.time()
    interval_seconds = config.original_post_interval_minutes * 60
    time_since_last = now - last_post_time.get("timestamp", 0)

    if time_since_last < interval_seconds:
        return

    # Pick a random topic for the post
    if not config.search_topics:
        return

    topic = random.choice(config.search_topics)
    logger.info("[ORIGINAL POST] Generating tweet about: %s", topic)

    # Generate tweet using ChatGPT
    messages = build_original_post_messages(config, topic)
    tweet_text = generate_ai_content(messages, config, logger, max_tokens=280)

    if not tweet_text:
        logger.warning("[ORIGINAL POST] Failed to generate tweet content")
        return

    logger.info("[ORIGINAL POST] Generated: %s", tweet_text[:100])

    # Post the tweet
    try:
        # Go to home to access compose button
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Click compose button
        compose_selectors = [
            "a[href='/compose/post']",
            "a[aria-label='Post']",
            "a[data-testid='SideNav_NewTweet_Button']",
        ]

        compose_clicked = False
        for selector in compose_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    compose_clicked = True
                    logger.info("[ORIGINAL POST] Clicked compose button")
                    break
            except:
                continue

        if not compose_clicked:
            logger.warning("[ORIGINAL POST] Could not find compose button")
            return

        time.sleep(2)

        # Find composer and type tweet
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=15000, state="visible")
        composer.click()
        time.sleep(1)

        # Type the tweet
        page.keyboard.type(tweet_text, delay=10)
        time.sleep(2)

        # Click post button
        post_selectors = [
            "button[data-testid='tweetButton']",
            "div[data-testid='tweetButton']",
            "[aria-label*='Post']",
        ]

        for selector in post_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    time.sleep(3)
                    logger.info("[ORIGINAL POST] Tweet posted successfully")
                    last_post_time["timestamp"] = now
                    return
            except:
                continue

        # Fallback to keyboard shortcut
        is_mac = page.evaluate("() => navigator.platform.includes('Mac')")
        if is_mac:
            page.keyboard.press("Meta+Enter")
        else:
            page.keyboard.press("Control+Enter")
        time.sleep(3)
        logger.info("[ORIGINAL POST] Tweet posted via keyboard shortcut")
        last_post_time["timestamp"] = now

    except PlaywrightError as exc:
        logger.warning("[ORIGINAL POST] Failed to post tweet: %s", str(exc)[:100])


def maybe_follow_author(page: Page, tweet_data: dict[str, str], config: BotConfig, logger: logging.Logger, follow_count: dict) -> None:
    """Follow the author of a tweet we replied to."""
    if not config.enable_auto_follow:
        return

    # Check if we've hit the follow limit for this cycle
    if follow_count.get("count", 0) >= config.max_auto_follows_per_cycle:
        return

    handle = tweet_data.get("handle", "")
    if not handle:
        return

    logger.info("[AUTO-FOLLOW] Attempting to follow @%s", handle)

    try:
        # Navigate to user's profile
        profile_url = f"https://x.com/{handle}"
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Try to find and click follow button
        follow_selectors = [
            "div[data-testid$='-follow']",
            "button[data-testid$='-follow']",
            "[aria-label*='Follow @']",
            "[aria-label='Follow']",
        ]

        for selector in follow_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=2000):
                    btn_text = btn.inner_text().strip().lower()
                    # Only click if it says "follow" (not "following")
                    if "follow" in btn_text and "following" not in btn_text:
                        btn.click(timeout=5000)
                        time.sleep(2)
                        logger.info("[AUTO-FOLLOW] Successfully followed @%s", handle)
                        follow_count["count"] = follow_count.get("count", 0) + 1
                        return
                    else:
                        logger.info("[AUTO-FOLLOW] Already following @%s", handle)
                        return
            except:
                continue

        logger.info("[AUTO-FOLLOW] Could not find follow button for @%s", handle)

    except PlaywrightError as exc:
        logger.warning("[AUTO-FOLLOW] Failed to follow @%s: %s", handle, str(exc)[:100])


def process_tweets(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    tweets: list[Locator],
    topic: str,
    logger: logging.Logger,
    follow_count: dict,
    dm_count: dict,
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

        # Try AI-powered reply first if enabled, otherwise use templates
        message = None
        if config.enable_ai_replies and config.openai_api_key:
            # Use AI reply with probability based on ai_reply_rate
            use_ai = random.random() < config.ai_reply_rate
            if use_ai:
                message = generate_ai_reply(config, data["text"], topic, data["handle"] or "unknown", logger)

        # Fallback to template-based reply if AI didn't generate one
        if not message:
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

            # Try to follow the author after successful reply
            maybe_follow_author(page, data, config, logger, follow_count)

            # Try to send DM if interest score is high enough
            maybe_send_dm(config, page, data, logger, dm_count)

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
    follow_count: dict,
    dm_count: dict,
) -> None:
    logger.info("[INFO] Topic '%s' - loading search results...", topic)
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)  # Give tweets time to render
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

    process_tweets(config, registry, page, video_service, tweets, topic, logger, follow_count, dm_count)


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    logger: logging.Logger,
) -> None:
    logger.info("[INFO] Starting engagement loop with %s topic(s).", len(config.search_topics))

    # State tracking for new growth features
    last_post_time = {"timestamp": 0}  # Track when we last posted an original tweet
    follow_count = {"count": 0}  # Track follows this cycle
    dm_count = {"count": 0}  # Track DMs this cycle

    while True:
        try:
            if page.is_closed():
                logger.info("Browser page closed. Exiting engagement loop.")
                return
        except PlaywrightError:
            logger.info("Browser page unavailable. Exiting engagement loop.")
            return

        # Reset counters at the start of each cycle
        follow_count["count"] = 0
        dm_count["count"] = 0

        # Try to post an original tweet if enough time has passed
        maybe_post_original_tweet(config, page, logger, last_post_time)

        # Process search topics
        if config.search_topics:
            for topic in config.search_topics:
                handle_topic(config, registry, page, video_service, topic, logger, follow_count, dm_count)
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
        browser = playwright.chromium.launch(
            headless=config.headless,
            args=["--start-maximized", "--no-sandbox"],
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
    load_dotenv(override=True)  # Force override existing env vars
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
