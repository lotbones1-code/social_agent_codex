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
import requests

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
    openai_api_key: Optional[str]
    use_ai_replies: bool
    enable_image_generation: bool
    image_generation_chance: float
    huggingface_api_key: Optional[str]


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

    openai_api_key = (os.getenv("OPENAI_API_KEY") or "").strip() or None
    use_ai_replies = openai_api_key is not None

    enable_image_generation = _parse_bool(os.getenv("ENABLE_IMAGE_GENERATION"), default=False)
    image_generation_chance = _parse_float("IMAGE_GENERATION_CHANCE", 0.3)  # 30% of replies get images

    huggingface_api_key = (os.getenv("HUGGING_FACE_API_KEY") or "").strip() or None

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
        use_ai_replies=use_ai_replies,
        enable_image_generation=enable_image_generation,
        image_generation_chance=image_generation_chance,
        huggingface_api_key=huggingface_api_key,
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


class ConversionTracker:
    """Track sales metrics and conversion analytics."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict:
        if not self._path.exists():
            return {
                "total_replies": 0,
                "ai_replies": 0,
                "template_replies": 0,
                "total_dms": 0,
                "high_intent_leads": 0,
                "lead_scores": [],
                "videos_generated": 0,
                "images_generated": 0,
                "sessions": [],
            }
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
                # Backward compatibility: add images_generated if missing
                if "images_generated" not in data:
                    data["images_generated"] = 0
                return data
        except (OSError, json.JSONDecodeError):
            return {
                "total_replies": 0,
                "ai_replies": 0,
                "template_replies": 0,
                "total_dms": 0,
                "high_intent_leads": 0,
                "lead_scores": [],
                "videos_generated": 0,
                "images_generated": 0,
                "sessions": [],
            }

    def _save(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2)
        except OSError as exc:
            logging.getLogger(__name__).warning("Failed to persist conversion tracker: %s", exc)

    def log_reply(self, *, ai_powered: bool = False) -> None:
        self._data["total_replies"] += 1
        if ai_powered:
            self._data["ai_replies"] += 1
        else:
            self._data["template_replies"] += 1
        self._save()

    def log_dm(self) -> None:
        self._data["total_dms"] += 1
        self._save()

    def log_lead_score(self, score: float, *, high_intent: bool = False) -> None:
        self._data["lead_scores"].append(score)
        if high_intent:
            self._data["high_intent_leads"] += 1
        # Keep only last 1000 scores to prevent file bloat
        if len(self._data["lead_scores"]) > 1000:
            self._data["lead_scores"] = self._data["lead_scores"][-1000:]
        self._save()

    def log_video(self) -> None:
        self._data["videos_generated"] += 1
        self._save()

    def log_image(self) -> None:
        self._data["images_generated"] += 1
        self._save()

    def log_session_start(self) -> None:
        import datetime
        self._data["sessions"].append({
            "started_at": datetime.datetime.now().isoformat(),
            "replies": 0,
            "dms": 0,
        })
        # Keep only last 100 sessions
        if len(self._data["sessions"]) > 100:
            self._data["sessions"] = self._data["sessions"][-100:]
        self._save()

    def get_stats(self) -> dict:
        avg_score = 0.0
        if self._data["lead_scores"]:
            avg_score = sum(self._data["lead_scores"]) / len(self._data["lead_scores"])

        return {
            "total_replies": self._data["total_replies"],
            "ai_replies": self._data["ai_replies"],
            "template_replies": self._data["template_replies"],
            "total_dms": self._data["total_dms"],
            "high_intent_leads": self._data["high_intent_leads"],
            "videos_generated": self._data["videos_generated"],
            "images_generated": self._data.get("images_generated", 0),
            "avg_lead_score": round(avg_score, 2),
            "total_sessions": len(self._data["sessions"]),
        }


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

    def maybe_generate(self, topic: str, tweet_text: str) -> Optional[str]:
        """Generate video content and return video URL if successful."""
        if not self.enabled:
            return None
        logger = logging.getLogger(__name__)
        logger.info(
            "Video generation requested for topic '%s' using provider '%s'.",
            topic,
            self.provider,
        )
        if self._client is None:
            logger.warning("Video client unavailable. Skipping generation.")
            return None

        try:
            if self.provider == "replicate":
                # Build a prompt for video generation
                prompt = f"Create a short video about {topic}: {tweet_text[:100]}"
                logger.info("Generating video with Replicate: %s", self.model)

                output = self._client.run(
                    self.model,
                    input={"prompt": prompt}
                )

                # Extract video URL from output
                if isinstance(output, str):
                    video_url = output
                elif isinstance(output, list) and len(output) > 0:
                    video_url = output[0]
                elif isinstance(output, dict) and "video" in output:
                    video_url = output["video"]
                else:
                    logger.warning("Unexpected Replicate output format: %s", type(output))
                    return None

                logger.info("Video generated successfully: %s", video_url)
                return video_url

        except Exception as exc:  # noqa: BLE001
            logger.warning("Video generation failed: %s", exc)
            return None


def generate_image_with_ai(
    topic: str,
    tweet_text: str,
    config: BotConfig,
    logger: logging.Logger,
) -> Optional[str]:
    """Generate an eye-catching image using FREE Hugging Face API."""
    if not config.enable_image_generation or not config.huggingface_api_key:
        return None

    # Random chance to generate image (don't do it every time - too much)
    if random.random() > config.image_generation_chance:
        logger.info("Skipping image generation (chance roll)")
        return None

    try:
        # Create a compelling image prompt
        prompt = f"Professional marketing image: {topic}, modern style, high quality, business focused"

        logger.info("Generating AI image with Hugging Face (FREE)...")

        # Use Hugging Face's free inference API
        hf_url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"

        headers = {"Authorization": f"Bearer {config.huggingface_api_key}"}

        response = requests.post(
            hf_url,
            headers=headers,
            json={"inputs": prompt},
            timeout=30,
        )

        if response.status_code == 200:
            # Save image locally
            image_path = Path("logs/generated_images")
            image_path.mkdir(parents=True, exist_ok=True)

            image_file = image_path / f"img_{int(time.time())}.png"
            with open(image_file, "wb") as f:
                f.write(response.content)

            logger.info("Image generated successfully: %s", image_file)
            return str(image_file)
        else:
            logger.warning("Image generation failed: %d", response.status_code)
            return None

    except Exception as exc:  # noqa: BLE001
        logger.warning("Image generation error: %s", exc)
        return None


def generate_ai_reply(
    config: BotConfig,
    tweet_text: str,
    topic: str,
    author_handle: str,
    logger: logging.Logger,
) -> Optional[str]:
    """Generate an intelligent, sales-focused reply using OpenAI GPT-4."""
    if not config.use_ai_replies or not config.openai_api_key:
        return None

    try:
        # Build the sales-focused system prompt
        system_prompt = f"""You are a successful entrepreneur and expert in {topic}. Your goal is to provide genuine value while subtly driving interest in your solution.

TONE: Conversational, authentic, helpful - like a peer sharing hard-won insights
STYLE: Short (under 280 chars), punchy, human
GOAL: Build trust and curiosity that leads to clicks

Key principles:
- Lead with value or insight
- Reference specific aspects of their tweet
- Natural mention of your resource/link
- No hard selling - intrigue over pressure
- Sound like a real person, not a marketer"""

        user_prompt = f"""Tweet from @{author_handle}:
"{tweet_text}"

Write a reply that:
1. Acknowledges their specific point about {topic}
2. Shares a brief relevant insight or experience
3. Naturally mentions this resource: {config.referral_link}

Keep it under 280 characters. Make it feel like advice from a peer, not a sales pitch."""

        # Call OpenAI API
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.openai_api_key}",
        }

        payload = {
            "model": "gpt-4o-mini",  # Fast and cost-effective
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.85,  # Creative but not random
            "max_tokens": 100,
        }

        logger.info("Calling OpenAI API for AI-powered reply...")
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=15,
        )

        if response.status_code == 200:
            data = response.json()
            message = data["choices"][0]["message"]["content"].strip()
            logger.info("OpenAI generated reply successfully (length: %d chars)", len(message))
            return message
        else:
            logger.warning(
                "OpenAI API returned status %d: %s",
                response.status_code,
                response.text[:200],
            )
            return None

    except requests.exceptions.Timeout:
        logger.warning("OpenAI API request timed out")
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning("OpenAI API request failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error generating AI reply: %s", exc)
        return None


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


def send_reply(
    page: Page,
    tweet: Locator,
    message: str,
    logger: logging.Logger,
    image_path: Optional[str] = None,
) -> bool:
    try:
        tweet.locator("div[data-testid='reply']").click()
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        composer.wait_for(timeout=10000)
        composer.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.insert_text(message)

        # If we have an image, attach it!
        if image_path and Path(image_path).exists():
            try:
                logger.info("Attaching image to reply: %s", image_path)
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files(image_path)
                time.sleep(2)  # Wait for image to upload
                logger.info("Image attached successfully!")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to attach image: %s", exc)

        page.locator("div[data-testid='tweetButtonInline']").click()
        time.sleep(2)
        logger.info("[INFO] Reply posted successfully.")
        return True
    except PlaywrightTimeout:
        logger.warning("Timeout while composing reply.")
    except PlaywrightError as exc:
        logger.warning("Failed to send reply: %s", exc)
    return False


def calculate_lead_score(tweet_text: str, config: BotConfig) -> float:
    """Calculate lead quality score based on tweet content and engagement signals."""
    score = 0.0
    text_lower = tweet_text.lower()

    # High-intent keywords (strong buying signals)
    high_intent_keywords = [
        "looking for", "need help", "recommendations", "best tool", "what do you use",
        "how do i", "struggling with", "trying to", "anyone know", "budget for",
        "pay for", "subscribe", "worth it", "testimonial", "review"
    ]
    for keyword in high_intent_keywords:
        if keyword in text_lower:
            score += 2.0

    # Question words indicate active problem-solving (good leads)
    question_words = ["?", "how", "what", "why", "when", "where", "which", "who"]
    for word in question_words:
        if word in text_lower:
            score += config.dm_question_weight

    # Length indicates thoughtfulness (quality lead)
    dm_trigger_length = _parse_int("DM_TRIGGER_LENGTH", 220)
    if len(tweet_text) >= dm_trigger_length:
        score += 1.5

    # Specific topic relevance
    for keyword in config.relevant_keywords:
        if keyword in text_lower:
            score += 0.5

    return score


def send_dm(
    page: Page,
    handle: str,
    message: str,
    logger: logging.Logger,
) -> bool:
    """Send a direct message to a user."""
    try:
        # Navigate to DM compose
        dm_url = f"https://x.com/messages/compose?recipient_id={handle}"
        logger.info("Opening DM composer for @%s", handle)
        page.goto(dm_url, wait_until="domcontentloaded", timeout=30000)

        # Wait for DM textarea
        dm_textarea = page.locator("div[data-testid='dmComposerTextInput']").first
        dm_textarea.wait_for(timeout=10000)
        dm_textarea.click()

        # Type message
        page.keyboard.insert_text(message)
        time.sleep(1)

        # Send button
        send_button = page.locator("div[data-testid='dmComposerSendButton']").first
        send_button.click()

        time.sleep(2)
        logger.info("DM sent successfully to @%s", handle)
        return True

    except PlaywrightTimeout:
        logger.warning("Timeout while sending DM to @%s", handle)
        return False
    except PlaywrightError as exc:
        logger.warning("Failed to send DM to @%s: %s", handle, exc)
        return False


def maybe_send_dm(
    config: BotConfig,
    page: Page,
    tweet_data: dict[str, str],
    logger: logging.Logger,
    tracker: Optional["ConversionTracker"] = None,
) -> None:
    """Send a follow-up DM to high-intent leads."""
    if not config.enable_dms:
        return

    if not config.dm_templates:
        global _DM_NOTICE_LOGGED
        if not _DM_NOTICE_LOGGED:
            logger.info(
                "DM support enabled but no DM_TEMPLATES configured. Skipping DM attempt."
            )
            _DM_NOTICE_LOGGED = True
        return

    # Calculate lead score
    lead_score = calculate_lead_score(tweet_data["text"], config)
    logger.info(
        "Lead score for @%s: %.2f (threshold: %.2f)",
        tweet_data["handle"],
        lead_score,
        config.dm_interest_threshold,
    )

    # Only DM high-quality leads
    if lead_score < config.dm_interest_threshold:
        logger.info("Lead score below threshold. Skipping DM.")
        return

    # Select a DM template
    template = random.choice(config.dm_templates)
    message = template.format(
        name=tweet_data["handle"],
        focus=text_focus(tweet_data["text"]),
        ref_link=config.referral_link or "",
    ).strip()

    if not message:
        logger.warning("Generated empty DM. Skipping.")
        return

    logger.info("High-quality lead detected! Sending follow-up DM to @%s", tweet_data["handle"])

    # Add delay before DM (human-like behavior)
    dm_delay = random.randint(30, 90)
    logger.info("Waiting %d seconds before sending DM (anti-spam)...", dm_delay)
    time.sleep(dm_delay)

    if send_dm(page, tweet_data["handle"], message, logger):
        if tracker:
            tracker.log_dm()
            logger.info("DM tracked in analytics")


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
    tracker: Optional["ConversionTracker"] = None,
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

        # Try AI-powered reply first, fall back to templates
        message = None
        used_ai = False

        if config.use_ai_replies:
            ai_message = generate_ai_reply(
                config,
                data["text"],
                topic,
                data["handle"] or "user",
                logger,
            )
            if ai_message:
                message = ai_message
                used_ai = True
                logger.info("Using AI-generated reply (OpenAI)")
            else:
                logger.info("AI reply failed, falling back to template")

        # Fallback to template-based reply
        if not message:
            template = random.choice(config.reply_templates)
            message = template.format(
                topic=topic,
                focus=text_focus(data["text"]),
                ref_link=config.referral_link or "",
            ).strip()
            used_ai = False

        if not message:
            logger.warning("Generated empty reply. Skipping tweet.")
            continue

        logger.info("[INFO] Replying to @%s for topic '%s'.", data['handle'] or 'unknown', topic)

        # Generate AI image for visual engagement
        image_path = generate_image_with_ai(topic, data["text"], config, logger)

        if send_reply(page, tweet, message, logger, image_path):
            registry.add(identifier)
            replies += 1

            # Track the successful reply
            if tracker:
                tracker.log_reply(ai_powered=used_ai)

            # Track image if generated
            if image_path and tracker:
                tracker.log_image()
                logger.info("Image generated and posted!")

            # Calculate and track lead score
            lead_score = calculate_lead_score(data["text"], config)
            if tracker:
                tracker.log_lead_score(
                    lead_score,
                    high_intent=(lead_score >= config.dm_interest_threshold)
                )

            # Generate video if enabled
            video_url = video_service.maybe_generate(topic, data["text"])
            if video_url and tracker:
                tracker.log_video()

            # Send DM to high-intent leads
            maybe_send_dm(config, page, data, logger, tracker)

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
    tracker: Optional["ConversionTracker"] = None,
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

    process_tweets(config, registry, page, video_service, tweets, topic, logger, tracker)


def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    logger: logging.Logger,
    tracker: Optional["ConversionTracker"] = None,
) -> None:
    logger.info("[INFO] Starting engagement loop with %s topic(s).", len(config.search_topics))

    # Log session start
    if tracker:
        tracker.log_session_start()

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
                handle_topic(config, registry, page, video_service, topic, logger, tracker)
        else:
            logger.info("No search topics configured. Sleeping before next cycle.")

        # Log stats after each cycle
        if tracker:
            stats = tracker.get_stats()
            logger.info(
                "[ANALYTICS] Session Stats - Replies: %d (AI: %d, Template: %d) | DMs: %d | "
                "High-Intent Leads: %d | Avg Lead Score: %.2f | Images: %d | Videos: %d",
                stats["total_replies"],
                stats["ai_replies"],
                stats["template_replies"],
                stats["total_dms"],
                stats["high_intent_leads"],
                stats["avg_lead_score"],
                stats["images_generated"],
                stats["videos_generated"],
            )

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
        browser = playwright.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
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
    if config.use_ai_replies:
        logger.info("AI_REPLIES=enabled (OpenAI)")

    registry = MessageRegistry(MESSAGE_LOG_PATH)
    video_service = VideoService(config)
    tracker = ConversionTracker(Path("logs/analytics.json"))

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
                    run_engagement_loop(config, registry, page, video_service, logger, tracker)
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
