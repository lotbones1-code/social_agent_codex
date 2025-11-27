"""Lightweight video discovery helpers."""
from __future__ import annotations

import logging
import re
import urllib.request
from dataclasses import dataclass
from typing import Iterable, List

from .config import BotSettings


@dataclass(slots=True)
class VideoItem:
    url: str
    source: str
    topic: str


class VideoScraper:
    """Scrape videos from configured sources without third-party APIs."""

    def __init__(self, config: BotSettings, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger

    def _find_mp4_links(self, content: str) -> list[str]:
        pattern = r"https?://[^\"' ]+\.mp4"
        return re.findall(pattern, content)

    def _fetch_source(self, url: str) -> list[str]:
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                body = response.read().decode("utf-8", errors="ignore")
            return self._find_mp4_links(body) or [url]
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Failed to scrape %s: %s", url, exc)
            return []

    def discover(self, topic: str) -> List[VideoItem]:
        videos: list[VideoItem] = []
        for source in self.config.video_sources:
            for link in self._fetch_source(source):
                videos.append(VideoItem(url=link, source=source, topic=topic))
                if len(videos) >= self.config.max_videos:
                    return videos
        return videos

    def cycle_topics(self) -> Iterable[VideoItem]:
        for topic in self.config.topics:
            for item in self.discover(topic):
                yield item
