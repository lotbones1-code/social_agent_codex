#!/usr/bin/env python3
"""Production-ready social agent for engaging with X (Twitter)."""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from playwright.async_api import (
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeout,
    async_playwright,
)

load_dotenv()

DEFAULT_REPLY_TEMPLATES = [
    "Been riffing with other builders about {topic}, and this {focus} breakdown keeps delivering wins. Shortcut link: {ref_link}",
    "Every time {topic} comes up, I point people to this {focus} playbook: {ref_link}",
]
DEFAULT_SEARCH_TOPICS = ["AI automation"]
MESSAGE_LOG_PATH = Path("logs/replied.json")
PROFILE_DIR = Path(os.getenv("PW_PROFILE_DIR", ".pwprofile"))
PROFILE_DIR.mkdir(parents=True, exist_ok=True)
MESSAGE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
_DM_NOTICE_LOGGED = False


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
        print(f"[WARN] Invalid value for {name!r} -> {raw!r}. Using {default} instead.")
        return default


def _parse_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        print(f"[WARN] Invalid value for {name!r} -> {raw!r}. Using {default} instead.")
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
        print(
            "[WARN] ACTION_DELAY_MAX_SECONDS < ACTION_DELAY_MIN_SECONDS. Aligning maximum to minimum."
        )
        action_delay_max = action_delay_min

    if loop_delay_seconds < 0:
        print("[WARN] LOOP_DELAY_SECONDS was negative. Using default of 120.")
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
            print(f"[WARN] Failed to persist registry: {exc}")


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
                print(
                    "[WARN] VIDEO_PROVIDER=replicate but 'replicate' package missing. Video features disabled."
                )
                return
            if not token:
                print(
                    "[WARN] VIDEO_PROVIDER=replicate but REPLICATE_API_TOKEN missing. Video features disabled."
                )
                return
            self._client = replicate
            self.enabled = True
        elif self.provider:
            print(f"[WARN] VIDEO_PROVIDER={self.provider} is not supported. Video features disabled.")

    async def maybe_generate(self, topic: str, tweet_text: str) -> None:
        if not self.enabled:
            return
        print(
            f"[INFO] Video generation requested for topic '{topic}' using provider '{self.provider}'."
        )
        if self._client is None:
            print("[WARN] Video client unavailable. Skipping generation.")
            return
        try:
            # Placeholder for integration; real generation should be implemented as needed.
            _ = topic, tweet_text
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Video generation failed: {exc}")


async def create_browser(config: BotConfig) -> tuple[Playwright, BrowserContext, Page]:
    playwright = await async_playwright().start()
    context: BrowserContext = await playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=config.headless,
        args=["--no-sandbox"],
    )
    page: Page = await context.new_page()
    return playwright, context, page


async def is_logged_in(page: Page) -> bool:
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
            if await locator.is_visible(timeout=2000):
                return True
        except PlaywrightError:
            continue

    try:
        current_url = page.url
    except PlaywrightError:
        return False
    return "x.com/home" in current_url or "twitter.com/home" in current_url


async def ensure_logged_in(page: Page, config: BotConfig) -> bool:
    try:
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        print("[WARN] Timeout while loading home timeline during login check.")
    except PlaywrightError as exc:
        print(f"[WARN] Error while loading home timeline: {exc}")

    if await is_logged_in(page):
        print("[INFO] Session already authenticated.")
        return True

    username = config.x_username
    password = config.x_password

    if username and password:
        print("[INFO] Attempting automated login with provided credentials.")
        try:
            await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            await page.fill("input[name='text']", username)
            await page.keyboard.press("Enter")
            await page.wait_for_selector("input[name='password']", timeout=30000)
            await page.fill("input[name='password']", password)
            await page.keyboard.press("Enter")
            await page.wait_for_url("**/home", timeout=60000)
            await asyncio.sleep(3)
            if await is_logged_in(page):
                print("[INFO] Automated login succeeded.")
                return True
            print("[ERROR] Automated X login failed to reach authenticated state.")
            print(
                "[ERROR] Automated X login failed; please check credentials or log in manually once."
            )
            return False
        except PlaywrightTimeout:
            print("[ERROR] Automated X login timed out. Please verify credentials or log in manually once.")
            return False
        except PlaywrightError as exc:
            print(f"[ERROR] Playwright error during automated login: {exc}")
            return False

    print("[INFO] No X credentials provided. Waiting for manual login.")
    try:
        await page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
    except PlaywrightError as exc:
        print(f"[WARN] Unable to open login page: {exc}")

    deadline = asyncio.get_running_loop().time() + 120
    while asyncio.get_running_loop().time() < deadline:
        if await is_logged_in(page):
            print("[INFO] Manual login detected.")
            return True
        await asyncio.sleep(3)

    print(
        "[ERROR] Not logged into X. Start the bot with HEADLESS=false, log in in the opened browser once, then rerun."
    )
    return False


async def get_tweet_elements(page: Page) -> list[Locator]:
    try:
        await page.wait_for_selector("article[data-testid='tweet']", timeout=15000)
    except PlaywrightTimeout:
        print("[INFO] No tweets loaded within 15 seconds.")
        return []
    except PlaywrightError as exc:
        print(f"[WARN] Playwright error while waiting for tweets: {exc}")
        return []
    return await page.locator("article[data-testid='tweet']").all()


async def extract_tweet_data(tweet: Locator) -> dict[str, str] | None:
    try:
        text_locator = tweet.locator("div[data-testid='tweetText']")
        text = (await text_locator.inner_text()).strip()
    except PlaywrightError:
        return None

    if not text:
        return None

    tweet_href = ""
    try:
        link = tweet.locator("a[href*='/status/']").first
        tweet_href = (await link.get_attribute("href")) or ""
    except PlaywrightError:
        tweet_href = ""

    author_handle = ""
    try:
        user_link = tweet.locator("div[data-testid='User-Name'] a").first
        href = await user_link.get_attribute("href")
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


async def send_reply(page: Page, tweet: Locator, message: str) -> bool:
    try:
        await tweet.locator("div[data-testid='reply']").click()
        composer = page.locator("div[data-testid^='tweetTextarea_']").first
        await composer.wait_for(timeout=10000)
        await composer.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.insert_text(message)
        await page.locator("div[data-testid='tweetButtonInline']").click()
        await asyncio.sleep(2)
        return True
    except PlaywrightTimeout:
        print("[WARN] Timeout while composing reply.")
    except PlaywrightError as exc:
        print(f"[WARN] Failed to send reply: {exc}")
    return False


async def maybe_send_dm(config: BotConfig, page: Page, tweet_data: dict[str, str]) -> None:
    global _DM_NOTICE_LOGGED
    if not config.enable_dms:
        return
    if not config.dm_templates:
        if not _DM_NOTICE_LOGGED:
            print("[INFO] DM support enabled but no DM_TEMPLATES configured. Skipping DM attempt.")
            _DM_NOTICE_LOGGED = True
        return
    if not _DM_NOTICE_LOGGED:
        print(
            "[INFO] DM feature enabled, but automated DM workflows are not implemented in this build."
        )
        _DM_NOTICE_LOGGED = True


async def handle_topic(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    topic: str,
) -> None:
    print(f"[INFO] Topic '{topic}' - loading search results...")
    url = f"https://x.com/search?q={quote_plus(topic)}&src=typed_query&f=live"
    try:
        await page.goto(url, wait_until="networkidle", timeout=60000)
    except PlaywrightTimeout:
        print(f"[WARN] Timeout while loading topic '{topic}'.")
        return
    except PlaywrightError as exc:
        print(f"[WARN] Error while loading topic '{topic}': {exc}")
        return

    tweets = await get_tweet_elements(page)
    print(f"[INFO] Loaded {len(tweets)} tweets for topic '{topic}'.")
    if not tweets:
        print(f"[INFO] No eligible tweets for topic '{topic}'.")
        return

    await process_tweets(config, registry, page, video_service, tweets, topic)


async def process_tweets(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
    tweets: list[Locator],
    topic: str,
) -> None:
    candidates: list[tuple[dict[str, str], Locator]] = []

    for tweet in tweets:
        if page.is_closed():
            print("[INFO] Page closed while processing tweets.")
            return

        data = await extract_tweet_data(tweet)
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
            print(
                f"[INFO] Skipping tweet {data['id']} from @{data['handle'] or 'unknown'}: reason={','.join(skip_reasons)}"
            )
            continue

        candidates.append((data, tweet))

    print(f"[INFO] {len(candidates)} eligible tweets for topic '{topic}' after filtering.")

    if not candidates:
        print(f"[INFO] No eligible tweets for topic '{topic}'.")
        return

    replies = 0
    for data, tweet in candidates:
        if replies >= config.max_replies_per_topic:
            break

        template = random.choice(config.reply_templates)
        message = template.format(
            topic=topic,
            focus=text_focus(data["text"]),
            ref_link=config.referral_link or "",
        ).strip()

        if not message:
            print("[WARN] Generated empty reply. Skipping tweet.")
            continue

        print(f"[INFO] Replying to @{data['handle'] or 'unknown'} for topic '{topic}'.")

        if await send_reply(page, tweet, message):
            registry.add(identifier)
            replies += 1
            await video_service.maybe_generate(topic, data["text"])
            await maybe_send_dm(config, page, data)
            delay = random.randint(config.action_delay_min, config.action_delay_max)
            print(f"[INFO] Sleeping for {delay} seconds before next action.")
            await asyncio.sleep(delay)
        else:
            print("[WARN] Reply attempt failed; not recording tweet as replied.")


def text_focus(text: str, *, max_length: int = 80) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_length:
        return cleaned
    return f"{cleaned[: max_length - 3]}..."


async def run_engagement_loop(
    config: BotConfig,
    registry: MessageRegistry,
    page: Page,
    video_service: VideoService,
) -> None:
    print(f"[INFO] Starting engagement loop with {len(config.search_topics)} topic(s).")
    while True:
        try:
            if page.is_closed():
                print("[INFO] Browser page closed. Exiting engagement loop.")
                return

            if config.search_topics:
                for topic in config.search_topics:
                    await handle_topic(config, registry, page, video_service, topic)
            else:
                print("[INFO] No search topics configured. Sleeping before next cycle.")

            print(f"[INFO] Cycle complete. Sleeping for {config.loop_delay_seconds} seconds.")
            await asyncio.sleep(config.loop_delay_seconds)
        except KeyboardInterrupt:
            raise
        except PlaywrightTimeout as exc:
            print(f"[ERROR] Playwright timeout in engagement loop: {exc}")
            if config.debug:
                traceback.print_exc()
            await asyncio.sleep(10)
        except PlaywrightError as exc:
            print(f"[ERROR] Playwright error in engagement loop: {exc}")
            if config.debug:
                traceback.print_exc()
            await asyncio.sleep(10)
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] Unexpected error in engagement loop: {exc}")
            if config.debug:
                traceback.print_exc()
            await asyncio.sleep(10)


async def main() -> None:
    config = load_config()
    print(f"[INFO] Search topics configured: {', '.join(config.search_topics)}")
    print(f"[INFO] HEADLESS={config.headless}, DEBUG={config.debug}")
    if config.enable_dms:
        print("[INFO] ENABLE_DMS=true")
    registry = MessageRegistry(MESSAGE_LOG_PATH)
    video_service = VideoService(config)

    playwright = context = page = None
    try:
        playwright, context, page = await create_browser(config)
        print(f"[INFO] Browser launched (headless={config.headless}).")
        logged_in = await ensure_logged_in(page, config)
        if not logged_in:
            return
        print("[INFO] Login verified. Starting engagement loop.")
        await run_engagement_loop(config, registry, page, video_service)
    except KeyboardInterrupt:
        print("[INFO] Shutdown requested by user.")
    except PlaywrightTimeout as exc:
        print(f"[ERROR] Playwright timeout: {exc}")
        if config.debug:
            traceback.print_exc()
    except PlaywrightError as exc:
        print(f"[ERROR] Playwright error: {exc}")
        if config.debug:
            traceback.print_exc()
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Unhandled exception: {exc}")
        if config.debug:
            traceback.print_exc()
    finally:
        if context:
            try:
                await context.close()
            except Exception as exc:  # noqa: BLE001
                if config.debug:
                    print(f"[WARN] Failed to close browser context: {exc}")
        if playwright:
            try:
                await playwright.stop()
            except Exception as exc:  # noqa: BLE001
                if config.debug:
                    print(f"[WARN] Failed to stop Playwright: {exc}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[INFO] Shutdown requested by user.")
        sys.exit(0)
