from __future__ import annotations

import logging
import re
from typing import Iterable, List


class TrendAnalyzer:
    """Build a clean, de-duplicated topic list for the influencer loop."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        require_trending: bool = False,
        max_topics: int | None = None,
    ):
        self.logger = logger
        self.require_trending = require_trending
        self.max_topics = max_topics

    @staticmethod
    def _normalize_topic(topic: str) -> str:
        cleaned = topic.strip().lstrip("#")
        cleaned = re.sub(r"[^A-Za-z0-9\s]", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""
        no_space = cleaned.replace(" ", "")
        return f"#{no_space}" if not cleaned.startswith("#") else cleaned

    def build_topics(self, configured: Iterable[str], trending: Iterable[str]) -> List[str]:
        topics: List[str] = []

        trending_tags: List[str] = []
        for raw in trending:
            tag = self._normalize_topic(raw)
            if tag and tag not in trending_tags:
                trending_tags.append(tag)

        if self.require_trending and not trending_tags:
            self.logger.warning("Trending fetch returned nothing; skipping cycle by configuration.")
            return []

        for raw in configured:
            normalized = self._normalize_topic(raw)
            if normalized and normalized not in topics:
                topics.append(normalized)

        topics.extend([t for t in trending_tags if t not in topics])

        if self.max_topics is not None:
            topics = topics[: self.max_topics]

        self.logger.info("Prepared %d topics for scraping.", len(topics))
        return topics


__all__ = ["TrendAnalyzer"]
