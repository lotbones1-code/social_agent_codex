from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Iterable, List

from .config import AgentConfig
from .influencer_captioner import InfluencerCaptioner, InfluencerContext
from .influencer_downloader import InfluencerDownloader
from .influencer_replies import InfluencerReplyAgent
from .influencer_scraper import InfluencerPost, InfluencerScraper
from .poster import VideoPoster


class InfluencerRunner:
    """Orchestrates scraping → download → caption → post for influencer mode."""

    def __init__(
        self,
        scraper: InfluencerScraper,
        downloader: InfluencerDownloader,
        poster: VideoPoster,
        captioner: InfluencerCaptioner,
        reply_agent: InfluencerReplyAgent,
        config: AgentConfig,
        logger: logging.Logger,
    ) -> None:
        self.scraper = scraper
        self.downloader = downloader
        self.poster = poster
        self.captioner = captioner
        self.reply_agent = reply_agent
        self.config = config
        self.logger = logger

    def _post_count(self) -> int:
        if not self.config.strict_mode:
            return random.randint(2, max(2, min(3, self.config.influencer_posts_max_per_day)))
        return random.randint(
            self.config.influencer_posts_min_per_day, self.config.influencer_posts_max_per_day
        )

    def _post_delay(self) -> float:
        if not self.config.strict_mode:
            return random.uniform(10, 60)
        return random.uniform(
            self.config.influencer_delay_min_seconds, self.config.influencer_delay_max_seconds
        )

    def _choose_topic(self, post: InfluencerPost, topics: Iterable[str]) -> str:
        lowered = post.text.lower()
        for topic in topics:
            if topic.lower() in lowered:
                return topic
        return next(iter(topics), "trending")

    def run_posts(self, topics: List[str]) -> None:
        targets = self.scraper.gather(topics, cap=self.config.influencer_candidate_cap)
        if not targets:
            self.logger.info("No influencer candidates surfaced; skipping this cycle.")
            return

        posts_to_send = self._post_count()
        self.logger.info("Planning %d influencer posts this run", posts_to_send)

        for post in targets:
            if posts_to_send <= 0:
                break
            media_path = self.downloader.download(post)
            if not media_path:
                continue
            topic = self._choose_topic(post, topics)
            caption = self.captioner.generate(
                InfluencerContext(author=post.author, topic=topic, text=post.text, url=post.url)
            )
            if self.poster.post_video(caption, Path(media_path)):
                self.downloader.mark_posted(Path(media_path))
                posts_to_send -= 1
                delay = self._post_delay()
                self.logger.info("Posted influencer video tweet successfully. Sleeping %.1fs", delay)
                time.sleep(delay)
            else:
                self.logger.warning("Failed to post influencer video for %s", post.url)

    def run_replies(self) -> None:
        self.reply_agent.run(
            self.config.influencer_reply_targets,
            replies_per_target=self.config.influencer_replies_per_target,
        )


__all__ = ["InfluencerRunner"]
