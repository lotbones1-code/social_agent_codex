#!/usr/bin/env python3
"""Complete influencer bot workflow with Playwright persistence."""
from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from agent.browser import BrowserSession, start_session
from agent.captions import CaptionGenerator
from agent.config import BotSettings
from agent.downloader import VideoDownloader
from agent.poster import GrowthActions, Poster
from agent.scheduler import TaskScheduler
from agent.scraper import VideoScraper


def setup_logging(debug: bool) -> logging.Logger:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="[%(asctime)s] [%(levelname)s] %(message)s")
    return logging.getLogger("social_agent")


def engagement_cycle(session: BrowserSession, settings: BotSettings, logger: logging.Logger) -> None:
    assert session.page is not None
    scraper = VideoScraper(settings, logger)
    downloader = VideoDownloader(settings.download_dir, logger)
    captions = CaptionGenerator.from_config(settings)
    poster = Poster(session.page, logger, attach_rate=settings.attach_rate)
    growth = GrowthActions(
        session.page, logger, like_limit=settings.like_limit, follow_limit=settings.follow_limit
    )
    scheduler = TaskScheduler(logger)

    def post_item(item) -> None:
        media_path = downloader.download(item)
        caption = captions.render(item)
        poster.publish(caption, media_path, allow_media=True)
        session.page.wait_for_timeout(settings.wait_after_actions * 1000)
        growth.run_cycle()

    tasks = [lambda item=item: post_item(item) for item in scraper.cycle_topics()]
    if not tasks:
        logger.warning("No videos discovered. Check VIDEO_SOURCES configuration.")
        return
    scheduler.run(tasks, delay_range=(20, 60))


def run() -> None:
    load_dotenv()
    settings = BotSettings.from_env()
    logger = setup_logging(settings.debug)

    logger.info("Topics: %s", ", ".join(settings.topics))
    logger.info("Downloads: %s", settings.download_dir)
    logger.info("Playwright profile: %s", settings.user_data_dir)

    session = start_session(settings, logger)
    if not session:
        sys.exit(1)

    try:
        if not session.ensure_login():
            logger.error("Login was not completed. Exiting.")
            return
        engagement_cycle(session, settings, logger)
    finally:
        session.__exit__(None, None, None)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        logging.getLogger("social_agent").info("Shutdown requested by user.")
        sys.exit(0)
