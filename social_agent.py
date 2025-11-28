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
from bot.auto_reply import AutoReplyEngine
from bot.growth import GrowthActions
from bot.poster import VideoPoster
from bot.post_tracker import PostTracker
from bot.scheduler import Scheduler
from bot.scraper import ScrapedPost, VideoScraper
from bot.trending import TrendingTopics


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
    post: ScrapedPost,
    topic: str,
    downloader: VideoDownloader,
    poster: VideoPoster,
    captioner: CaptionGenerator,
    tracker: PostTracker,
    logger: logging.Logger,
    scheduler: Scheduler,
) -> Optional[str]:
    # Check for duplicates before downloading
    if tracker.is_duplicate(post.video_url):
        logger.info("⏭️  Skipping duplicate video: %s", post.url)
        return None

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
    logger.info("Generated caption: %s", caption)

    posted_url = poster.post_video(caption, video_path)
    if posted_url:
        # Record the post for duplicate tracking
        tracker.record_post(
            video_url=post.video_url,
            caption=caption,
            topic=topic,
            tweet_url=posted_url if posted_url != "DRY_RUN_NO_URL" else None,
        )
    scheduler.between_actions()
    return posted_url


def handle_topic(
    topic: str,
    scraper: VideoScraper,
    downloader: VideoDownloader,
    poster: VideoPoster,
    captioner: CaptionGenerator,
    tracker: PostTracker,
    scheduler: Scheduler,
    growth: GrowthActions,
    config: AgentConfig,
    logger: logging.Logger,
    posts_remaining: Optional[int],
) -> int:
    posts = scraper.search_topic(topic)
    if not posts:
        logger.info("No video posts surfaced for '%s'", topic)
        return 0

    repost_candidates: List[ScrapedPost] = []
    posted_count = 0
    for post in posts:
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
            post, topic, downloader, poster, captioner, tracker, logger, scheduler
        )
        if posted_url:
            repost_candidates.append(post)
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

    scheduler = Scheduler(config)

    def cycle() -> None:
        logger.info("=" * 70)
        logger.info("🚀 Starting new engagement cycle")
        logger.info("=" * 70)

        # Initialize post tracker
        tracker = PostTracker(
            log_path=config.post_log,
            duplicate_check_hours=config.duplicate_check_hours,
            max_posts_24h=config.max_posts_per_24h,
            logger=logger,
        )

        # Clean up old records periodically
        tracker.cleanup_old_records(keep_days=30)

        # Check if we can post now (24h rate limit)
        if not tracker.can_post_now():
            logger.warning("⏸️  Cycle skipped due to 24-hour posting limit")
            return

        if config.dry_run:
            logger.info("🔍 DRY-RUN MODE ENABLED - No posts will be submitted")

        with sync_playwright() as playwright:
            manager = BrowserManager(playwright, config, logger)
            session = manager.start()
            if not session:
                logger.error("Could not start authenticated session. Exiting cycle.")
                return
            poster = VideoPoster(session.page, logger, dry_run=config.dry_run)
            scraper = VideoScraper(session.page, logger)
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
            auto_reply = AutoReplyEngine(
                session.page, logger, config.auto_reply_template
            )
            trending = TrendingTopics(
                session.page,
                logger,
                refresh_minutes=config.trending_refresh_minutes,
                max_topics=config.trending_max_topics,
            )

            try:
                topics = list(dict.fromkeys(config.search_topics))
                if config.trending_enabled:
                    topics.extend([t for t in trending.fetch() if t not in topics])
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
                        downloader,
                        poster,
                        captioner,
                        tracker,
                        scheduler,
                        growth,
                        config,
                        logger,
                        remaining,
                    )
                    total_posted += posted
            finally:
                session.close()
            if not config.dry_run:
                auto_reply.reply_to_latest(
                    max_replies=config.auto_replies_per_cycle
                )
        logger.info("=" * 70)
        logger.info("✅ Cycle complete. Waiting %ss before the next run.", config.loop_delay_seconds)
        logger.info("=" * 70)

    scheduler.run_forever(cycle)


if __name__ == "__main__":
    run_bot()
