from __future__ import annotations

import logging
import time
from typing import List

from playwright.sync_api import Error as PlaywrightError, Page


class TrendingTopics:
    """Scrape trending topics/hashtags to feed the search pipeline.

    A Premium+ login unlocks the native Trending tab, so we reuse the active
    authenticated Playwright page to surface the freshest topics with video
    potential.
    """

    def __init__(self, page: Page, logger: logging.Logger, *, refresh_minutes: int, max_topics: int):
        self.page = page
        self.logger = logger
        self.refresh_minutes = refresh_minutes
        self.max_topics = max_topics
        self._cache: List[str] = []
        self._last_fetch: float = 0.0

    def _is_stale(self) -> bool:
        return (time.time() - self._last_fetch) > (self.refresh_minutes * 60)

    def _extract_topics(self) -> List[str]:
        try:
            cards = self.page.locator("div[data-testid='trend']").all()
        except PlaywrightError as exc:
            self.logger.warning("Could not read trending topics: %s", exc)
            return []

        topics: List[str] = []
        for card in cards:
            try:
                text = card.inner_text(timeout=2000)
            except PlaywrightError:
                continue
            if not text:
                continue
            cleaned = text.replace("#", "").split("\n")[0].strip()
            if cleaned and cleaned not in topics:
                topics.append(cleaned)
            if len(topics) >= self.max_topics:
                break
        return topics

    def fetch(self) -> List[str]:
        if self._cache and not self._is_stale():
            return self._cache

        url = "https://x.com/explore/tabs/trending"
        self.logger.info("Refreshing trending topics from %s", url)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(1500)
        except PlaywrightError as exc:
            self.logger.warning("Failed to load trending tab: %s", exc)
            return self._cache

        topics = self._extract_topics()
        if topics:
            self._cache = topics
            self._last_fetch = time.time()
            self.logger.info("Loaded %d trending topics", len(topics))
        else:
            self.logger.info("No trending topics found; using cached set of %d", len(self._cache))
        return self._cache


__all__ = ["TrendingTopics"]
