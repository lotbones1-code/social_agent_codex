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

        # Store topics with metadata for smarter sorting
        topic_data: List[tuple[str, int, bool]] = []  # (topic, post_count, is_new)

        for card in cards:
            try:
                text = card.inner_text(timeout=2000)
            except PlaywrightError:
                continue
            if not text:
                continue

            lines = text.split("\n")
            if not lines:
                continue

            # FIND ACTUAL TOPIC (not category metadata or numbers)
            topic = None
            for line in lines:
                line_clean = line.replace("#", "").strip()
                if not line_clean:
                    continue

                # Skip metadata lines (categories, "Trending", etc.)
                if any(skip in line_clean for skip in ["·", "Trending in", "posts", "post"]):
                    continue

                # Skip if line is just a number (like "12.3K" or "1,234")
                if line_clean.replace(",", "").replace(".", "").replace("K", "").replace("M", "").isdigit():
                    continue

                # Skip very short lines (likely metadata)
                if len(line_clean) < 3:
                    continue

                # This looks like the actual topic!
                topic = line_clean
                break

            if not topic:
                continue

            # Extract post count (e.g., "1,234 posts" or "12.3K posts")
            post_count = 999999  # Default high number for unknown
            is_new = False

            for line in lines:
                line_lower = line.lower()
                # Check if marked as new/trending
                if "new" in line_lower or "🔥" in line:
                    is_new = True

                # Extract post count for velocity estimation
                if "post" in line_lower or "tweet" in line_lower:
                    # Parse numbers like "1,234 posts" or "12.3K posts"
                    parts = line.split()
                    for part in parts:
                        try:
                            # Handle K/M suffixes
                            if "k" in part.lower():
                                num = float(part.lower().replace("k", "").replace(",", ""))
                                post_count = int(num * 1000)
                                break
                            elif "m" in part.lower():
                                num = float(part.lower().replace("m", "").replace(",", ""))
                                post_count = int(num * 1000000)
                                break
                            else:
                                # Regular number
                                num_str = part.replace(",", "")
                                if num_str.isdigit():
                                    post_count = int(num_str)
                                    break
                        except (ValueError, AttributeError):
                            continue

            topic_data.append((topic, post_count, is_new))

        # PRIORITIZE NEW/FRESH TRENDS:
        # 1. Topics marked "NEW" first
        # 2. Then topics with LOWER post counts (newer trends)
        # 3. Then everything else
        topic_data.sort(key=lambda x: (
            not x[2],      # is_new=True first (False sorts before True, so invert)
            x[1],          # Then by post count ascending (lower = newer)
        ))

        # Extract just the topic names, deduplicate, and validate
        topics: List[str] = []
        for topic, count, is_new in topic_data:
            if topic in topics:
                continue

            # FINAL VALIDATION: Ensure topic makes sense
            # Skip if it's just numbers or garbage
            if not any(c.isalpha() for c in topic):
                self.logger.debug("⚠️ Rejected topic (no letters): %r", topic)
                continue

            # Skip very generic/useless topics
            if topic.lower() in ["trending", "new", "live", "viral", "hot"]:
                self.logger.debug("⚠️ Rejected topic (too generic): %r", topic)
                continue

            marker = "🆕" if is_new else f"({count} posts)" if count < 999999 else ""
            self.logger.info("✓ Trend: %s %s", topic, marker)
            topics.append(topic)

            if len(topics) >= self.max_topics:
                break

        return topics

    def fetch(self) -> List[str]:
        if self._cache and not self._is_stale():
            return self._cache

        # Try main Trending tab first (best for catching NEW trends)
        url = "https://x.com/explore/tabs/trending"
        self.logger.info("🔍 Refreshing trending topics from %s", url)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(2000)  # Give trends time to load
        except PlaywrightError as exc:
            self.logger.warning("Failed to load trending tab: %s", exc)
            return self._cache

        topics = self._extract_topics()

        # If we got topics, great! Cache them
        if topics:
            self._cache = topics
            self._last_fetch = time.time()
            self.logger.info("✅ Loaded %d trending topics (prioritizing NEW/fresh trends)", len(topics))
            for i, topic in enumerate(topics[:5]):  # Log top 5
                self.logger.info("  %d. %s", i + 1, topic)
        else:
            self.logger.info("No trending topics found; using cached set of %d", len(self._cache))

        return self._cache


__all__ = ["TrendingTopics"]
