#!/usr/bin/env python3
"""Self-contained influencer bot that scrapes, downloads, and reposts videos on X."""
from __future__ import annotations

import logging
import random
from typing import List, Optional

from playwright.sync_api import sync_playwright

from bot.browser import BrowserManager
from bot.captioner import CaptionGenerator, VideoContext
from bot.config import AgentConfig, load_config
from bot.downloader import VideoDownloader
from bot.growth import GrowthActions
from bot.poster import VideoPoster
from bot.scheduler import Scheduler
from bot.scraper import ScrapedPost, VideoScraper
from bot.trending import TrendingTopics
from bot.trend_analyzer import TrendAnalyzer
from bot.viral_scorer import ScoredPost, ViralScorer


def _shorten(text: str, *, max_len: int = 140) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def _slug_from_url(url: str) -> str:
    slug = url.rstrip("/").split("/")[-1]
    if not slug:
        slug = f"vid-{random.randint(1000, 9999)}"
    return slug.replace("?", "-").replace("#", "-")


def _repost_video(
    candidate: ScoredPost,
    topic: str,
    downloader: VideoDownloader,
    poster: VideoPoster,
    captioner: CaptionGenerator,
    logger: logging.Logger,
    scheduler: Scheduler,
) -> Optional[str]:
    post = candidate.post
    logger.info("[stage:download] Fetching video for %s (score=%.2f)", post.url, candidate.score)
    slug = _slug_from_url(post.url)
    video_path = downloader.download(
        tweet_url=post.url, video_url=post.video_url, filename_hint=slug
    )
    if not video_path:
        logger.warning("Skipping candidate because download failed: %s", post.url)
        return None

    context = VideoContext(
        author=post.author,
        summary=_shorten(post.text, max_len=200),
        topic=topic,
        url=post.url,
    )
    caption = captioner.generate(context)
    logger.info("[stage:caption] Generated caption: %s", caption)

    logger.info("[stage:upload] Opening composer for %s", slug)
    posted_url = poster.post_video(caption, video_path)
    scheduler.between_actions()
    return posted_url


def handle_topic(
    topic: str,
    scraper: VideoScraper,
    scorer: ViralScorer,
    downloader: VideoDownloader,
    poster: VideoPoster,
    captioner: CaptionGenerator,
    scheduler: Scheduler,
    growth: GrowthActions,
    config: AgentConfig,
    logger: logging.Logger,
    posts_remaining: Optional[int],
) -> int:
    logger.info("[stage:scrape] Searching for trending videos on '%s'", topic)
    posts = scraper.search_topic(topic)
    if not posts:
        logger.info("No video posts surfaced for '%s'", topic)
        return 0

    scored_posts = scorer.rank(posts)
    if not scored_posts:
        logger.info("No candidates met the viral score threshold for '%s'", topic)
        return 0

    repost_candidates: List[ScrapedPost] = []
    posted_count = 0
    for candidate in scored_posts:
        if len(repost_candidates) >= config.max_videos_per_topic:
            break
        if posts_remaining is not None and posted_count >= posts_remaining:
            logger.info(
                "Post limit reached for this cycle (%s); skipping remaining candidates for '%s'",
                posts_remaining,
                topic,
            )
            break

        posted_url = _repost_video(
            candidate, topic, downloader, poster, captioner, logger, scheduler
        )
        if posted_url:
            repost_candidates.append(candidate.post)
            posted_count += 1

    if repost_candidates:
        growth.engage(repost_candidates, max_actions=config.growth_actions_per_cycle)
    else:
        logger.info("No successful reposts to engage with for '%s'", topic)
    return posted_count


def run_bot() -> None:
    config = load_config()

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("social_agent")

    # Debug: Print configuration summary
    logger.info("=== BOT CONFIGURATION ===")
    logger.info("headless: %s", config.headless)
    logger.info("debug: %s", config.debug)
    logger.info("search_topics: %s", config.search_topics)
    logger.info("max_videos_per_topic: %d", config.max_videos_per_topic)
    logger.info("max_posts_per_cycle: %d", config.max_posts_per_cycle)
    logger.info("growth_actions_per_cycle: %d", config.growth_actions_per_cycle)
    logger.info("openai_api_key: %s", "SET" if config.openai_api_key else "NOT SET")
    logger.info("auth_state: %s (exists: %s)", config.auth_state, config.auth_state.exists())
    logger.info("user_data_dir: %s", config.user_data_dir)
    logger.info("=========================")

    scheduler = Scheduler(config)

    def cycle() -> None:
        logger.info("Starting engagement cycle.")
        with sync_playwright() as playwright:
            manager = BrowserManager(playwright, config, logger)
            session = manager.start()
            if not session:
                logger.error("Could not start authenticated session. Exiting cycle.")
                return
            poster = VideoPoster(
                session.page,
                logger,
                upload_retries=config.upload_retry_attempts,
                post_retries=config.post_retry_attempts,
            )
            scraper = VideoScraper(session.page, logger)
            scorer = ViralScorer(logger, min_score=config.min_viral_score)
            downloader = VideoDownloader(
                config.download_dir,
                logger,
                user_agent=config.download_user_agent,
            )
            try:
                downloader.set_cookies(session.context.cookies())
            except Exception:
                logger.debug("Could not inject cookies into downloader; continuing without Premium headers")
            captioner = CaptionGenerator(
                config.caption_template,
                openai_api_key=config.openai_api_key,
                model=config.gpt_caption_model,
            )
            growth = GrowthActions(poster, logger)
            trending = TrendingTopics(
                session.page,
                logger,
                refresh_minutes=config.trending_refresh_minutes,
                max_topics=config.trending_max_topics,
            )
            trend_analyzer = TrendAnalyzer(
                logger,
                require_trending=config.require_trending,
                max_topics=config.trending_max_topics,
            )

            try:
                configured_topics = list(dict.fromkeys(config.search_topics))
                trending_topics: List[str] = []
                if config.trending_enabled:
                    logger.info("[stage:trending] Fetching trending topics…")
                    trending_topics = trending.fetch()
                topics = trend_analyzer.build_topics(configured_topics, trending_topics)
                if not topics:
                    logger.info("No topics available; ending cycle early.")
                    return
                total_posted = 0
                per_cycle_cap = (
                    config.max_posts_per_cycle if config.strict_mode else None
                )

                for topic in topics:
                    remaining = None
                    if per_cycle_cap is not None:
                        remaining = max(per_cycle_cap - total_posted, 0)
                        if remaining == 0:
                            logger.info(
                                "Per-cycle post cap of %d reached; skipping remaining topics.",
                                per_cycle_cap,
                            )
                            break

                    posted = handle_topic(
                        topic,
                        scraper,
                        scorer,
                        downloader,
                        poster,
                        captioner,
                        scheduler,
                        growth,
                        config,
                        logger,
                        remaining,
                    )
                    total_posted += posted
            finally:
                session.close()
        logger.info("Cycle complete. Waiting %ss before the next run.", config.loop_delay_seconds)

    scheduler.run_forever(cycle)


if __name__ == "__main__":
    run_bot()
