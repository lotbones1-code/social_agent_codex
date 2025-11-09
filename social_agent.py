#!/usr/bin/env python3
"""Ultra-human modular social agent for X interactions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv

try:
    import openai
except ImportError as exc:  # pragma: no cover - handled at runtime
    openai = None  # type: ignore[assignment]
    _OPENAI_IMPORT_ERROR: Optional[Exception] = exc
else:
    _OPENAI_IMPORT_ERROR = None
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright
try:
    from replicate import Client as ReplicateClient
except ImportError as exc:  # pragma: no cover - handled at runtime
    ReplicateClient = None  # type: ignore[assignment]
    _REPLICATE_IMPORT_ERROR: Optional[Exception] = exc
else:
    _REPLICATE_IMPORT_ERROR = None

from configurator import (
    DEFAULT_DM_TEMPLATES,
    DEFAULT_REPLY_TEMPLATES,
    TEMPLATE_DELIMITER,
    ensure_env_file,
    parse_delimited_list,
    update_env,
)

# ---------------------------------------------------------------------------
# Environment bootstrapping
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent
ENV_PATH = ensure_env_file(ROOT_DIR)
load_dotenv(ENV_PATH)


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DelayConfig:
    """Configures randomized delays between visible actions."""

    min_seconds: int = 60
    max_seconds: int = 600

    def next_delay(self) -> int:
        return random.randint(self.min_seconds, self.max_seconds)


@dataclass(slots=True)
class MediaConfig:
    """Holds configuration for AI-generated media."""

    image_provider: str
    video_provider: str
    image_model: str
    video_model: str
    image_size: str
    video_duration: int


@dataclass(slots=True)
class HashtagConfig:
    """Configuration for sourcing trending hashtag data."""

    trending_url: Optional[str]
    fallback_hashtags: Dict[str, List[str]]
    refresh_interval_minutes: int = 45


@dataclass(slots=True)
class BotConfig:
    """Bot wide settings loaded from environment variables."""

    debug_enabled: bool
    profile_dir: Path
    search_topics: List[str]
    relevant_keywords: List[str]
    spam_keywords: List[str]
    referral_link: str
    max_replies_per_topic: int
    min_tweet_length: int
    min_keyword_matches: int
    dm_enabled: bool
    dm_trigger_length: int
    dm_question_weight: float
    dm_interest_threshold: float
    message_registry_path: Path
    delay_config: DelayConfig
    media_config: MediaConfig
    hashtag_config: HashtagConfig

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

        referral_link = os.getenv("REFERRAL_LINK", "").strip()
        max_replies_per_topic = int(os.getenv("MAX_REPLIES_PER_TOPIC", "5"))
        min_tweet_length = int(os.getenv("MIN_TWEET_LENGTH", "50"))
        min_keyword_matches = int(os.getenv("MIN_KEYWORD_MATCHES", "1"))
        dm_enabled = os.getenv("ENABLE_DMS", "true").strip().lower() not in {"", "0", "false", "off"}
        dm_trigger_length = int(os.getenv("DM_TRIGGER_LENGTH", "160"))
        dm_question_weight = float(os.getenv("DM_QUESTION_WEIGHT", "0.8"))
        dm_interest_threshold = float(os.getenv("DM_INTEREST_THRESHOLD", "3.0"))

        registry_path = Path(os.getenv("MESSAGE_REGISTRY_PATH", ROOT_DIR / "logs" / "messaged_users.json"))
        registry_path.parent.mkdir(parents=True, exist_ok=True)

        delay_config = DelayConfig(
            min_seconds=int(os.getenv("ACTION_DELAY_MIN_SECONDS", "60")),
            max_seconds=int(os.getenv("ACTION_DELAY_MAX_SECONDS", "600")),
        )

        media_config = MediaConfig(
            image_provider=os.getenv("IMAGE_PROVIDER", "openai"),
            video_provider=os.getenv("VIDEO_PROVIDER", "replicate"),
            image_model=os.getenv("IMAGE_MODEL", "gpt-image-1"),
            video_model=os.getenv("VIDEO_MODEL", "pika-labs/pika-1.0"),
            image_size=os.getenv("IMAGE_SIZE", "1024x1024"),
            video_duration=int(os.getenv("VIDEO_DURATION_SECONDS", "8")),
        )

        fallback_hashtags = _build_hashtag_fallback(search_topics)
        hashtag_config = HashtagConfig(
            trending_url=os.getenv("TRENDING_HASHTAG_URL", ""),
            fallback_hashtags=fallback_hashtags,
            refresh_interval_minutes=int(os.getenv("HASHTAG_REFRESH_MINUTES", "45")),
        )

        return cls(
            debug_enabled=debug_enabled,
            profile_dir=profile_dir,
            search_topics=search_topics,
            relevant_keywords=relevant_keywords,
            spam_keywords=spam_keywords,
            referral_link=referral_link,
            max_replies_per_topic=max_replies_per_topic,
            min_tweet_length=min_tweet_length,
            min_keyword_matches=min_keyword_matches,
            dm_enabled=dm_enabled,
            dm_trigger_length=dm_trigger_length,
            dm_question_weight=dm_question_weight,
            dm_interest_threshold=dm_interest_threshold,
            message_registry_path=registry_path,
            delay_config=delay_config,
            media_config=media_config,
            hashtag_config=hashtag_config,
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


def _build_hashtag_fallback(topics: Sequence[str]) -> Dict[str, List[str]]:
    fallback: Dict[str, List[str]] = {}
    for topic in topics:
        tokens = [token for token in re.split(r"[^A-Za-z0-9]+", topic) if token]
        fallback[topic] = [f"#{token.lower()}" for token in tokens]
    return fallback


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


def log(message: str, *, level: str = "info") -> None:
    if level == "debug" and not CONFIG.debug_enabled:
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level.upper()}] {message}"
    print(line)
    sys.stdout.flush()


CONFIG = BotConfig.from_env()


# ---------------------------------------------------------------------------
# Template management
# ---------------------------------------------------------------------------


class TemplatePool:
    """Randomly rotates templates without repeating the same message twice."""

    def __init__(self, templates: Sequence[str]):
        if not templates:
            raise ValueError("At least one template is required")
        self.templates = list(templates)
        self._queue: List[str] = []
        self._last_used: Optional[str] = None
        self._reshuffle()

    def _reshuffle(self) -> None:
        order = self.templates[:]
        random.shuffle(order)
        if self._last_used and order and order[0] == self._last_used:
            order.append(order.pop(0))
        self._queue = order

    def next(self, context: Dict[str, Any]) -> str:
        if not self._queue:
            self._reshuffle()
        template = self._queue.pop(0)
        self._last_used = template
        return template.format(**context)


class TemplateManager:
    """Loads and maintains template sets from the environment file."""

    def __init__(
        self,
        env_path: Path,
        env_key: str,
        fallback: Sequence[str],
        *,
        min_count: int = 1,
    ) -> None:
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
                raise ValueError(f"At least {self.min_count} templates are required for {self.env_key}.")
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

    def next(self, context: Dict[str, Any]) -> str:
        return self._pool.next(context)

    def add_template(self, template: str) -> None:
        template = template.strip()
        if not template:
            raise ValueError("Template content cannot be empty")
        self.templates.append(template)
        self._persist(self.templates)
        self._pool = TemplatePool(self.templates)


reply_templates = TemplateManager(
    ENV_PATH,
    "REPLY_TEMPLATES",
    DEFAULT_REPLY_TEMPLATES,
    min_count=10,
)
dm_templates = TemplateManager(
    ENV_PATH,
    "DM_TEMPLATES",
    DEFAULT_DM_TEMPLATES,
    min_count=5,
)


# ---------------------------------------------------------------------------
# Delay scheduling and registry management
# ---------------------------------------------------------------------------


class ActionScheduler:
    """Introduces human-like random delays between actions."""

    def __init__(self, config: DelayConfig) -> None:
        self.config = config

    async def wait(self, reason: str) -> None:
        delay_seconds = self.config.next_delay()
        log(f"Waiting {delay_seconds // 60}m{delay_seconds % 60:02d}s before {reason}.", level="debug")
        await asyncio.sleep(delay_seconds)


class MessageRegistry:
    """Tracks recently messaged users to prevent spamming."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self._records: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            with self.storage_path.open("r", encoding="utf-8") as handle:
                with contextlib.suppress(json.JSONDecodeError):
                    self._records = json.load(handle)

    def _persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as handle:
            json.dump(self._records, handle, indent=2)

    def prune(self) -> None:
        now = datetime.utcnow()
        expiry = now - timedelta(hours=24)
        updated = {
            username: timestamp
            for username, timestamp in self._records.items()
            if datetime.fromisoformat(timestamp) > expiry
        }
        if len(updated) != len(self._records):
            self._records = updated
            self._persist()

    def can_contact(self, username: str) -> bool:
        self.prune()
        timestamp = self._records.get(username.lower())
        if not timestamp:
            return True
        return datetime.fromisoformat(timestamp) <= datetime.utcnow() - timedelta(hours=24)

    def record(self, username: str) -> None:
        self.prune()
        self._records[username.lower()] = datetime.utcnow().isoformat()
        self._persist()


# ---------------------------------------------------------------------------
# AI media services
# ---------------------------------------------------------------------------


class AIImageService:
    """Generates topic-aware images via OpenAI's Images API."""

    def __init__(self, config: MediaConfig) -> None:
        self.config = config
        self.provider = (self.config.image_provider or "").strip().lower()
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self._client_ready = False
        self._disabled = False

        if self.provider in {"", "none", "disabled"}:
            self._disabled = True
            log("Image generation disabled via IMAGE_PROVIDER setting.", level="debug")
        elif self.provider in {"openai", "dalle", "dall-e"}:
            if _OPENAI_IMPORT_ERROR:
                raise SystemExit(
                    "IMAGE_PROVIDER=openai requires the optional 'openai' package. "
                    "Install it with `pip install openai` or set IMAGE_PROVIDER=none."
                ) from _OPENAI_IMPORT_ERROR
            if not self.api_key:
                raise SystemExit(
                    "IMAGE_PROVIDER=openai requires OPENAI_API_KEY to be set in the environment."
                )
            try:
                assert openai is not None
                openai.api_key = self.api_key
                self._client_ready = True
            except Exception as exc:  # noqa: BLE001
                self._client_ready = False
                log(f"Failed to initialize OpenAI client: {exc}", level="error")
        else:
            raise SystemExit(
                f"Unsupported IMAGE_PROVIDER '{self.config.image_provider}'. "
                "Set IMAGE_PROVIDER to 'openai' or 'none'."
            )

    async def generate(self, prompt: str) -> Optional[str]:
        if self._disabled:
            return None
        if not self._client_ready:
            log("Image generation unavailable (OpenAI client failed to initialize).", level="error")
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_generate, prompt)

    def _sync_generate(self, prompt: str) -> Optional[str]:
        try:
            assert openai is not None
            model = self.config.image_model
            if model == "gpt-image-1":
                model = "dall-e-3"
            response = openai.Image.create(
                prompt=prompt,
                size=self.config.image_size,
                n=1,
                model=model or None,
            )
            data = response.get("data") if isinstance(response, dict) else getattr(response, "data", None)
            if data:
                first = data[0]
                if isinstance(first, dict):
                    return first.get("url")
                url = getattr(first, "url", None)
                if isinstance(url, str):
                    return url
        except Exception as exc:  # noqa: BLE001
            log(f"Image generation failed: {exc}", level="warning")
        return None


class AIVideoService:
    """Generates short topic videos using Replicate."""

    def __init__(self, config: MediaConfig) -> None:
        self.config = config
        self.provider = (self.config.video_provider or "").strip().lower()
        self.api_token = os.getenv("REPLICATE_API_TOKEN", "").strip()
        self.client: Optional[Any] = None
        self._disabled = False

        if self.provider in {"", "none", "disabled"}:
            self._disabled = True
            log("Video generation disabled via VIDEO_PROVIDER setting.", level="debug")
        elif self.provider == "replicate":
            if _REPLICATE_IMPORT_ERROR:
                raise SystemExit(
                    "VIDEO_PROVIDER=replicate requires the optional 'replicate' package. "
                    "Install it with `pip install replicate` or set VIDEO_PROVIDER=none."
                ) from _REPLICATE_IMPORT_ERROR
            if not self.api_token:
                raise SystemExit(
                    "VIDEO_PROVIDER=replicate requires REPLICATE_API_TOKEN to be set in the environment."
                )
            try:
                self.client = ReplicateClient(api_token=self.api_token)
            except Exception as exc:  # noqa: BLE001
                self._disabled = True
                log(f"Failed to initialize Replicate client: {exc}", level="error")
        else:
            raise SystemExit(
                f"Unsupported VIDEO_PROVIDER '{self.config.video_provider}'. "
                "Set VIDEO_PROVIDER to 'replicate' or 'none'."
            )

    async def generate(self, prompt: str) -> Optional[str]:
        if self._disabled:
            return None
        if not self.client:
            log("Video generation unavailable (Replicate client failed to initialize).", level="error")
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._sync_generate, prompt)

    def _sync_generate(self, prompt: str) -> Optional[str]:
        try:
            output = self.client.run(
                self.config.video_model,
                input={
                    "prompt": prompt,
                    "duration": self.config.video_duration,
                },
            )
            if isinstance(output, str):
                return output
            if isinstance(output, Sequence) and output:
                return str(output[0])
        except Exception as exc:  # noqa: BLE001
            log(f"Video generation failed: {exc}", level="warning")
        return None


class MediaOrchestrator:
    """Coordinates media prompts and generation for replies/DMs."""

    def __init__(self, media_config: MediaConfig) -> None:
        self.image_service = AIImageService(media_config)
        self.video_service = AIVideoService(media_config)

    async def build_assets(self, topic: str, focus: str, post_text: str) -> Dict[str, Optional[str]]:
        prompt = f"{topic} focus: {focus}. Key post insight: {post_text[:200]}"
        image_url, video_url = await asyncio.gather(
            self.image_service.generate(prompt),
            self.video_service.generate(prompt),
        )
        return {"image_url": image_url, "video_url": video_url}


# ---------------------------------------------------------------------------
# Hashtag service
# ---------------------------------------------------------------------------


class HashtagService:
    """Maintains trending hashtags for each topic."""

    def __init__(self, config: HashtagConfig) -> None:
        self.config = config
        self._last_refresh: Optional[datetime] = None
        self._cache: Dict[str, List[str]] = {k: v[:] for k, v in config.fallback_hashtags.items()}

    async def refresh(self) -> None:
        if not self.config.trending_url:
            return
        if self._last_refresh and datetime.utcnow() - self._last_refresh < timedelta(
            minutes=self.config.refresh_interval_minutes
        ):
            return
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self.config.trending_url)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    for topic, tags in payload.items():
                        if isinstance(tags, list):
                            normalized = [tag if tag.startswith("#") else f"#{tag.strip()}" for tag in tags]
                            self._cache[topic] = normalized
            self._last_refresh = datetime.utcnow()
            log("Refreshed trending hashtag cache.", level="debug")
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to refresh hashtags: {exc}", level="warning")

    async def get_hashtags(self, topic: str, focus_tokens: Iterable[str]) -> List[str]:
        await self.refresh()
        topic_tags = self._cache.get(topic, [])
        focus_tags = [f"#{token.lower()}" for token in focus_tokens if token]
        merged = list(dict.fromkeys([*topic_tags, *focus_tags]))
        return merged[:6]


# ---------------------------------------------------------------------------
# Relevance and intent scoring
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> List[str]:
    return [token for token in re.split(r"[^A-Za-z0-9]+", text.lower()) if token]


@dataclass(slots=True)
class TopicProfile:
    raw: str
    tokens: List[str] = field(init=False)
    key: str = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = _tokenize(self.raw)
        self.key = " ".join(self.tokens)

    def score(self, text: str) -> float:
        normalized = text.lower()
        score = 0.0
        if self.raw.lower() in normalized:
            score += 2.5
        token_matches = sum(1 for token in self.tokens if token in normalized)
        score += token_matches * 1.2
        if self.tokens and f"#{self.tokens[0]}" in normalized:
            score += 1.0
        return score


@dataclass(slots=True)
class AnalysisResult:
    is_relevant: bool
    topic: str
    focus: str
    hashtags: List[str]
    keyword_hits: int
    interest_score: float
    high_intent: bool
    display_name: str
    handle: str
    snippet: str


class RelevanceEngine:
    """Determines whether posts align with configured topics and DM criteria."""

    QUESTION_PATTERNS = [
        re.compile(pattern, re.I)
        for pattern in [
            r"\?$",
            r"\bhow\b",
            r"\bwhat should\b",
            r"\bany advice\b",
            r"\bneed (help|advice)\b",
        ]
    ]

    REQUEST_PATTERNS = [re.compile(r"\bdm me\b", re.I), re.compile(r"\breach out\b", re.I)]

    def __init__(self, topics: Sequence[str], keywords: Sequence[str], spam_keywords: Sequence[str], *, min_keyword_matches: int) -> None:
        self.profiles = [TopicProfile(topic) for topic in topics]
        self.keyword_inventory = {keyword for keyword in keywords if keyword}
        self.spam_keywords = {keyword.lower() for keyword in spam_keywords if keyword}
        self.min_keyword_matches = max(1, min_keyword_matches)
        self.hashtag_service = HashtagService(CONFIG.hashtag_config)

    async def analyze(self, topic: str, display_name: str, handle: str, text: str) -> AnalysisResult:
        if len(text) < CONFIG.min_tweet_length:
            return AnalysisResult(False, topic, "", [], 0, 0.0, False, display_name, handle, "")

        normalized = text.lower()
        if any(spam in normalized for spam in self.spam_keywords):
            return AnalysisResult(False, topic, "", [], 0, 0.0, False, display_name, handle, "")
        profile = max(self.profiles, key=lambda candidate: candidate.score(normalized))
        keyword_hits = sum(1 for keyword in self.keyword_inventory if keyword in normalized)
        is_relevant = keyword_hits >= self.min_keyword_matches and profile.score(normalized) >= 2.0

        focus_tokens = profile.tokens[:2]
        hashtags = await self.hashtag_service.get_hashtags(topic, focus_tokens)
        interest_score = self._interest_score(text)
        high_intent = self._is_high_intent(normalized, interest_score, len(text))
        snippet = self._extract_snippet(text)

        return AnalysisResult(
            is_relevant,
            profile.raw,
            profile.tokens[0] if profile.tokens else topic,
            hashtags,
            keyword_hits,
            interest_score,
            high_intent,
            display_name,
            handle,
            snippet,
        )

    def _interest_score(self, text: str) -> float:
        normalized = text.lower()
        length_score = min(len(normalized) / 90, 4.0)
        question_score = normalized.count("?") * CONFIG.dm_question_weight
        urgency_score = normalized.count("!") * 0.2
        help_words = sum(
            normalized.count(keyword)
            for keyword in ["need", "looking for", "anyone", "recommend", "urgent", "best"]
        )
        return length_score + question_score + urgency_score + help_words * 0.6

    def _is_high_intent(self, normalized: str, interest_score: float, text_length: int) -> bool:
        if interest_score >= CONFIG.dm_interest_threshold and text_length >= CONFIG.dm_trigger_length:
            return True
        if any(pattern.search(normalized) for pattern in self.QUESTION_PATTERNS):
            return True
        if any(pattern.search(normalized) for pattern in self.REQUEST_PATTERNS):
            return True
        return False

    @staticmethod
    def _extract_snippet(text: str) -> str:
        sentences = re.split(r"(?<=[.!?]) +", text.strip())
        return sentences[0][:180] if sentences else text[:180]


# ---------------------------------------------------------------------------
# Personalization engine
# ---------------------------------------------------------------------------


class PersonalizationEngine:
    """Builds reply and DM payloads with personalized content."""

    def __init__(self, media_orchestrator: MediaOrchestrator) -> None:
        self.media = media_orchestrator

    async def craft_reply(self, analysis: AnalysisResult, topic: str, post_text: str) -> Dict[str, Any]:
        media_assets = await self.media.build_assets(topic, analysis.focus, post_text)
        context = {
            "name": analysis.display_name,
            "username": analysis.handle or analysis.display_name,
            "topic": topic,
            "focus": analysis.focus,
            "snippet": analysis.snippet,
            "hashtags": " ".join(analysis.hashtags),
            "ref_link": CONFIG.referral_link or "",
        }
        message = reply_templates.next(context)
        message = self._append_media_links(message, media_assets)
        return {"text": message, **media_assets}

    async def craft_dm(self, analysis: AnalysisResult, topic: str, post_text: str) -> Dict[str, Any]:
        media_assets = await self.media.build_assets(topic, analysis.focus, post_text)
        context = {
            "name": analysis.display_name,
            "username": analysis.handle or analysis.display_name,
            "topic": topic,
            "focus": analysis.focus,
            "snippet": analysis.snippet,
            "hashtags": " ".join(analysis.hashtags[:3]),
            "ref_link": CONFIG.referral_link or "",
        }
        message = dm_templates.next(context)
        message = self._append_media_links(message, media_assets)
        return {"text": message, **media_assets}

    @staticmethod
    def _append_media_links(message: str, media_assets: Dict[str, Optional[str]]) -> str:
        parts = [message]
        if media_assets.get("image_url"):
            parts.append(f"📷 {media_assets['image_url']}")
        if media_assets.get("video_url"):
            parts.append(f"🎬 {media_assets['video_url']}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Playwright helper utilities
# ---------------------------------------------------------------------------


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
                await page.wait_for_timeout(500)
                log("Selected Latest tab", level="debug")
                return
            except PlaywrightError as exc:
                log(f"Failed to click Latest tab via {selector}: {exc}", level="debug")
    log("Latest tab not found; continuing with default view.", level="warning")


async def wait_for_tweets(page) -> None:
    try:
        await page.wait_for_selector("article[data-testid='tweet']", timeout=25_000)
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
        with contextlib.suppress(Exception):
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


async def extract_author(tweet_locator) -> Tuple[str, str]:
    name_locator = tweet_locator.locator("div[data-testid='User-Names'] span").first
    handle_locator = tweet_locator.locator("a[href*='/status/']").first
    display = "there"
    handle = ""
    if await name_locator.count():
        with contextlib.suppress(PlaywrightError):
            display = " ".join((await name_locator.inner_text()).split())
    if await handle_locator.count():
        with contextlib.suppress(PlaywrightError):
            href = await handle_locator.get_attribute("href")
            if href:
                parts = href.split("/")
                if len(parts) >= 5:
                    handle = parts[3].lstrip("@").lower()
    return display, handle


async def open_reply_composer(page, tweet_locator) -> bool:
    reply_button = tweet_locator.locator("[data-testid='reply']").first
    if not await reply_button.count():
        log("Reply button not found for tweet; skipping.", level="warning")
        return False
    await reply_button.click()
    await page.wait_for_timeout(500)
    return True


async def send_text_to_composer(page, message: str) -> bool:
    textbox = page.locator("div[data-testid='tweetTextarea_0']").first
    if not await textbox.count():
        textbox = page.locator("div[data-testid='tweetTextarea_1']").first
    if not await textbox.count():
        log("Reply textbox not found; skipping tweet.", level="warning")
        await close_composer_if_open(page)
        return False
    await textbox.click()
    await page.keyboard.type(message, delay=random.randint(14, 24))
    await page.wait_for_timeout(400)
    return True


async def submit_reply(page) -> bool:
    with contextlib.suppress(Exception):
        await page.keyboard.press("Meta+Enter")
    await page.wait_for_timeout(1500)
    return True


async def attach_media(page, media_assets: Dict[str, Optional[str]]) -> None:
    upload_button = page.locator("input[data-testid='fileInput']").first
    if not await upload_button.count():
        log("Upload input unavailable; media links embedded instead.", level="debug")
        return
    for asset_key in ("image_url", "video_url"):
        url = media_assets.get(asset_key)
        if not url:
            continue
        try:
            tmp_path = await _download_media(url, suffix=".jpg" if "image" in asset_key else ".mp4")
            await upload_button.set_input_files(str(tmp_path))
            log(f"Attached media from {url}.", level="debug")
        except Exception as exc:  # noqa: BLE001
            log(f"Failed to attach media {url}: {exc}", level="warning")


async def _download_media(url: str, suffix: str) -> Path:
    tmp_dir = ROOT_DIR / "tmp_media"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        response.raise_for_status()
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    file_path = tmp_dir / f"asset_{timestamp}{suffix}"
    file_path.write_bytes(response.content)
    return file_path


# ---------------------------------------------------------------------------
# Messaging workflow orchestrator
# ---------------------------------------------------------------------------


class MessagingWorkflow:
    """Coordinates replies and DMs for each relevant post."""

    def __init__(
        self,
        relevance_engine: RelevanceEngine,
        personalizer: PersonalizationEngine,
        registry: MessageRegistry,
        scheduler: ActionScheduler,
    ) -> None:
        self.relevance_engine = relevance_engine
        self.personalizer = personalizer
        self.registry = registry
        self.scheduler = scheduler

    async def handle_tweet(self, page, topic: str, tweet_locator, index: int) -> bool:
        # 1) Gather context about the post before making any decisions.
        post_text = await extract_tweet_text(tweet_locator)
        if not post_text:
            log(f"Skipped tweet #{index + 1} for '{topic}' (no readable text).", level="debug")
            return False

        display_name, handle = await extract_author(tweet_locator)
        analysis = await self.relevance_engine.analyze(topic, display_name, handle, post_text)
        if not analysis.is_relevant:
            log(
                (
                    f"Ignored tweet #{index + 1} for '{topic}' (keyword_hits={analysis.keyword_hits}, "
                    f"interest={analysis.interest_score:.2f})."
                ),
                level="debug",
            )
            return False

        # 2) Draft a personalized public reply and attach generated media.
        reply_payload = await self.personalizer.craft_reply(analysis, topic, post_text)
        if not await open_reply_composer(page, tweet_locator):
            return False
        await self.scheduler.wait("typing reply")
        if not await send_text_to_composer(page, reply_payload["text"]):
            return False
        await attach_media(page, reply_payload)
        await self.scheduler.wait("submitting reply")
        await submit_reply(page)
        handle_note = f" (@{analysis.handle})" if analysis.handle else ""
        log(f"Replied to {analysis.display_name}{handle_note} on '{topic}'.")

        if CONFIG.referral_link and CONFIG.referral_link not in reply_payload["text"]:
            log("Consider updating templates to include referral link automatically.", level="debug")

        # 3) Escalate to DM for high-intent posts, respecting the contact registry.
        if CONFIG.dm_enabled and analysis.high_intent and handle and self.registry.can_contact(handle):
            await self.scheduler.wait("opening DM composer")
            dm_sent = await self._send_dm(page, tweet_locator, analysis, topic, post_text, handle)
            if dm_sent:
                self.registry.record(handle)
        else:
            log(
                "DM skipped (disabled, not high-intent, or recently contacted).",
                level="debug",
            )

        # 4) Allow a buffer before moving to the next candidate tweet.
        await self.scheduler.wait("moving to next tweet")
        return True

    async def _send_dm(
        self,
        page,
        tweet_locator,
        analysis: AnalysisResult,
        topic: str,
        post_text: str,
        username: str,
    ) -> bool:
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

            payload = await self.personalizer.craft_dm(analysis, topic, post_text)
            await composer.click()
            await dm_page.keyboard.type(payload["text"], delay=random.randint(12, 22))
            await attach_media(dm_page, payload)
            await self.scheduler.wait("sending DM")
            with contextlib.suppress(Exception):
                await dm_page.keyboard.press("Meta+Enter")
            await dm_page.wait_for_timeout(1000)
            handle_display = f"@{username}" if username else analysis.display_name
            log(f"Sent DM to {handle_display}.")
            return True
        except PlaywrightTimeout as exc:
            log(f"Timeout while attempting DM: {exc}", level="debug")
            return False
        except PlaywrightError as exc:
            log(f"Playwright error while attempting DM: {exc}", level="debug")
            return False
        finally:
            await dm_page.close()


# ---------------------------------------------------------------------------
# Main social agent
# ---------------------------------------------------------------------------


class SocialAgent:
    """Primary orchestration class controlling the bot lifecycle."""

    def __init__(self) -> None:
        # Compose modular services so each concern can be extended independently.
        self.scheduler = ActionScheduler(CONFIG.delay_config)
        self.registry = MessageRegistry(CONFIG.message_registry_path)
        self.relevance_engine = RelevanceEngine(
            CONFIG.search_topics,
            CONFIG.relevant_keywords,
            CONFIG.spam_keywords,
            min_keyword_matches=CONFIG.min_keyword_matches,
        )
        self.personalizer = PersonalizationEngine(MediaOrchestrator(CONFIG.media_config))
        self.workflow = MessagingWorkflow(
            self.relevance_engine,
            self.personalizer,
            self.registry,
            self.scheduler,
        )

    async def run(self) -> None:
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
                    # Iterate over configured topics so new workflows can be injected or reordered easily.
                    for topic in CONFIG.search_topics:
                        try:
                            await self._process_topic(page, topic)
                        except Exception as exc:  # noqa: BLE001
                            log(f"Error while processing topic '{topic}': {exc}", level="error")
                    log("Cycle complete. Restarting after scheduled delay.")
                    await self.scheduler.wait("starting new cycle")
            finally:
                await context.close()

    async def _process_topic(self, page, topic: str) -> None:
        await self.scheduler.wait(f"opening search for {topic}")
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
            handled = await self.workflow.handle_tweet(page, topic, tweet, idx)
            if handled:
                replies_sent += 1
        log(f"Finished topic '{topic}' with {replies_sent} replies.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        asyncio.run(SocialAgent().run())
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message:
            log(
                "Playwright Chromium binaries are missing. After installing dependencies, "
                "run `playwright install` to download the required browsers.",
                level="error",
            )
        else:
            log(f"Playwright failed: {message}", level="error")
        raise SystemExit(1)
    except KeyboardInterrupt:
        log("Interrupted by user. Exiting.", level="info")


if __name__ == "__main__":
    main()
