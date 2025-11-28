#!/usr/bin/env python3
"""Self-contained influencer bot that scrapes, downloads, and reposts videos on X."""
from __future__ import annotations

import logging
import random
from typing import List

from playwright.sync_api import sync_playwright

from bot.browser import BrowserManager
from bot.captioner import CaptionGenerator, VideoContext
from bot.config import AgentConfig, load_config
from bot.downloader import VideoDownloader
from bot.auto_reply import AutoReplyEngine
from bot.growth import GrowthActions
from bot.poster import VideoPoster
from bot.scheduler import Scheduler
from bot.scraper import ScrapedPost, VideoScraper
from bot.trending import TrendingTopics
from bot.influencer_captioner import InfluencerCaptioner
from bot.influencer_downloader import InfluencerDownloader
from bot.influencer_replies import InfluencerReplyAgent
from bot.influencer_runner import InfluencerRunner
from bot.influencer_scraper import InfluencerScraper


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


def handle_topic(
    topic: str,
    scraper: VideoScraper,
    downloader: VideoDownloader,
    poster: VideoPoster,
    captioner: CaptionGenerator,
    scheduler: Scheduler,
    growth: GrowthActions,
    config: AgentConfig,
    logger: logging.Logger,
) -> None:
    posts = scraper.search_topic(topic)
    if not posts:
        logger.info("No video posts surfaced for '%s'", topic)
        return

    repost_candidates: List[ScrapedPost] = []
    for post in posts:
        if len(repost_candidates) >= config.max_videos_per_topic:
            break
        if not post.video_url:
            continue
        slug = _slug_from_url(post.url)
        downloaded = downloader.download(post.video_url, filename_hint=slug)
        if not downloaded:
            continue
        context = VideoContext(
            author=post.author,
            summary=_shorten(post.text, max_len=200),
            topic=topic,
            url=post.url,
        )
        caption = captioner.generate(context)
        if poster.post_video(caption, downloaded):
            repost_candidates.append(post)
        scheduler.between_actions()

    if repost_candidates:
        growth.engage(repost_candidates, max_actions=config.growth_actions_per_cycle)
    else:
        logger.info("No successful reposts to engage with for '%s'", topic)


def run_bot() -> None:
    config = load_config()

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("social_agent")

    scheduler = Scheduler(config)

    def influencer_cycle() -> None:
        logger.info("Starting influencer cycle.")
        with sync_playwright() as playwright:
            manager = BrowserManager(playwright, config, logger)
            session = manager.start()
            if not session:
                logger.error("Could not start authenticated session. Exiting cycle.")
                return

            poster = VideoPoster(session.page, logger)
            scraper = InfluencerScraper(session.page, logger, debug=config.debug)
            downloader = InfluencerDownloader(
                config.influencer_inbox_dir,
                config.influencer_posted_dir,
                logger,
                user_agent=config.download_user_agent,
            )
            try:
                downloader.set_cookies(session.context.cookies())
            except Exception:
                logger.debug("Could not inject cookies into influencer downloader")
            captioner = InfluencerCaptioner(
                config.influencer_caption_template,
                openai_api_key=config.openai_api_key,
                model=config.gpt_caption_model,
            )
            reply_agent = InfluencerReplyAgent(
                session.page,
                logger,
                captioner,
                delay_min=config.influencer_reply_delay_min_seconds,
                delay_max=config.influencer_reply_delay_max_seconds,
            )
            runner = InfluencerRunner(
                scraper,
                downloader,
                poster,
                captioner,
                reply_agent,
                config,
                logger,
            )

            trending_topics: List[str] = []
            if config.trending_enabled:
                trending = TrendingTopics(
                    session.page,
                    logger,
                    refresh_minutes=config.trending_refresh_minutes,
                    max_topics=config.trending_max_topics,
                )
                trending_topics = [t for t in trending.fetch() if t]

            topics = list(dict.fromkeys(config.search_topics + trending_topics))
            if not topics:
                topics = ["trending videos"]
            try:
                runner.run_posts(topics)
                runner.run_replies()
            finally:
                session.close()
        logger.info(
            "Influencer cycle complete. Waiting %ss before the next run.",
            config.loop_delay_seconds,
        )

    def cycle() -> None:
        logger.info("Starting engagement cycle.")
        with sync_playwright() as playwright:
            manager = BrowserManager(playwright, config, logger)
            session = manager.start()
            if not session:
                logger.error("Could not start authenticated session. Exiting cycle.")
                return
            poster = VideoPoster(session.page, logger)
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
                for topic in topics:
                    handle_topic(
                        topic,
                        scraper,
                        downloader,
                        poster,
                        captioner,
                        scheduler,
                        growth,
                        config,
                        logger,
                    )
            finally:
                session.close()
            auto_reply.reply_to_latest(
                max_replies=config.auto_replies_per_cycle
            )
        logger.info("Cycle complete. Waiting %ss before the next run.", config.loop_delay_seconds)

    if config.influencer_mode:
        scheduler.run_forever(influencer_cycle)
    else:
        scheduler.run_forever(cycle)


if __name__ == "__main__":
    run_bot()
