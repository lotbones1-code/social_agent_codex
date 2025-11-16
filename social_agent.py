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
    # OpenAI settings
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    enable_ai_replies: bool = False
    ai_reply_rate: float = 0.3
    # Product/sales settings for AI replies
    product_name: str = "Social Agent Codex Bot"
    product_short_pitch: str = "An AI-powered X engagement bot that auto-replies to relevant tweets."
    product_cta: str = "DM me 'BOT' and I'll send you the link + setup guide."
    reply_tone: str = "casual"


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

    # OpenAI settings
    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or None
    openai_model = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
    enable_ai_replies = _parse_bool(os.getenv("ENABLE_AI_REPLIES"), default=False)
    ai_reply_rate = _parse_float("AI_REPLY_RATE", 0.3)

    # Product/sales settings
    product_name = (os.getenv("PRODUCT_NAME") or "Social Agent Codex Bot").strip()
    product_short_pitch = (os.getenv("PRODUCT_SHORT_PITCH") or "An AI-powered X engagement bot that auto-replies to relevant tweets.").strip()
    product_cta = (os.getenv("PRODUCT_CTA") or "DM me 'BOT' and I'll send you the link + setup guide.").strip()
    reply_tone = (os.getenv("REPLY_TONE") or "casual").strip()

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
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        enable_ai_replies=enable_ai_replies,
        ai_reply_rate=ai_reply_rate,
        product_name=product_name,
        product_short_pitch=product_short_pitch,
        product_cta=product_cta,
        reply_tone=reply_tone,
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
        # Check if reply button exists first (skip ads/promoted tweets)
        logger.info("[DEBUG] Looking for reply button...")
        reply_button = tweet.locator("div[data-testid='reply']")

        # Wait for button to be visible with short timeout
        if not reply_button.is_visible(timeout=3000):
            logger.warning("Reply button not visible - skipping (likely ad/promoted tweet)")
            return False

        # Click reply button
        logger.info("[DEBUG] Clicking reply button...")
        reply_button.click(timeout=5000)
        time.sleep(2)  # Give modal time to open

        # Wait for composer to appear
        logger.info("[DEBUG] Waiting for composer...")
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=15000, state="visible")

        logger.info("[DEBUG] Typing message...")
        composer.click()
        time.sleep(0.5)

        # Type message directly
        composer.fill(message)
        time.sleep(1.5)

        # Click post button - try both selectors
        logger.info("[DEBUG] Clicking post button...")
        try:
            post_button = page.locator("div[data-testid='tweetButton']").first
            if post_button.is_visible(timeout=2000):
                post_button.click(timeout=5000)
            else:
                raise PlaywrightTimeout("tweetButton not visible")
        except (PlaywrightTimeout, PlaywrightError):
            post_button = page.locator("div[data-testid='tweetButtonInline']").first
            post_button.click(timeout=5000)

        time.sleep(4)  # Give it time to post
        logger.info("[INFO] Reply posted successfully.")
        return True
    except PlaywrightTimeout as exc:
        logger.warning("Timeout while composing reply: %s", str(exc)[:100])
    except PlaywrightError as exc:
        logger.warning("Failed to send reply: %s", str(exc)[:100])
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


def build_reply_messages(tweet_text: str, topic: str, handle: str, config: BotConfig) -> list[dict]:
    """Build ChatGPT messages for AI-powered reply generation."""
    system_prompt = f"""You are a human social media growth operator writing replies on X (Twitter).

Product you are softly promoting:
- Name: {config.product_name}
- What it does: {config.product_short_pitch}
- How to get it: {config.product_cta}

Your goals, in this order:
1. First, add real value to the conversation so the author and readers see you as sharp and helpful.
2. Second, sometimes (not always) weave in a soft, natural plug for the product.

Style rules:
- Write like a real person on X, not like a corporate blog or an AI.
- Tone: {config.reply_tone} (interpret this as the general vibe, e.g. "casual" = relaxed, friendly, direct).
- Keep replies short and punchy: ideally 1–3 sentences.
- Avoid generic filler like "great point" or "this is interesting" unless you immediately follow with something specific and useful.
- Never mention that you are an AI, a bot, or a language model. Always speak as "I".
- Use emojis only when they genuinely fit the vibe. Do NOT spam emojis.
- Do not overuse hashtags. Only use a hashtag if it feels natural and is directly relevant.

Promotion behavior:
- Roughly 70% of replies should be pure value with **no promotion**.
- Roughly 30% of replies can include a **soft plug** at the end, for example:
  - "btw, I got tired of doing this manually so I built {config.product_name} to handle it → {config.product_cta}"
  - "I've been automating this with {config.product_name} and it's been a game changer ({config.product_cta})."
- The plug should never be the whole reply. It should come **after** you've added real value.

General behavior:
- Always base your reply on the tweet content and topic you are given.
- If the tweet is low quality, still be polite or neutral; don't be rude or hostile.
- Do NOT argue with people unless the topic clearly invites debate and it still feels on-brand.
""".strip()

    user_content = f"""Tweet text:
\"\"\"{tweet_text}\"\"\"

Topic: {topic}
Author handle: @{handle}

Write a reply that follows the system instructions. Do NOT include explanations, just the reply text I should post on X.""".strip()

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
