"""Improved video scraper for finding viral content."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import List, Optional

from playwright.sync_api import Error as PlaywrightError, Page


@dataclass
class VideoCandidate:
    """A video candidate for reposting."""
    url: str
    tweet_id: str
    author: str
    text: str
    has_video: bool = True


class ViralScraper:
    """Scrape viral videos from X."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def _scroll_feed(self, steps: int = 8) -> None:
        """Scroll the feed to load more content."""
        for i in range(steps):
            try:
                self.page.mouse.wheel(0, 2000)
                time.sleep(random.uniform(1.0, 2.0))
            except PlaywrightError:
                break

    def _extract_candidates_from_page(self, max_candidates: int = 20) -> List[VideoCandidate]:
        """Extract video candidates from current page."""
        candidates: List[VideoCandidate] = []

        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
            self.logger.info(f"Found {len(tweets)} total tweets on page")
        except PlaywrightError as exc:
            self.logger.warning(f"Could not locate tweets: {exc}")
            return []

        for tweet in tweets:
            if len(candidates) >= max_candidates:
                break

            try:
                # Check for video
                has_video = (
                    tweet.locator("video").count() > 0 or
                    tweet.locator("div[data-testid='videoPlayer']").count() > 0
                )

                if not has_video:
                    continue

                # Get tweet URL and ID
                link = tweet.locator("a[href*='/status/']").first
                href = link.get_attribute("href") or ""
                if not href or "/status/" not in href:
                    continue

                tweet_id = href.split("/status/")[-1].split("?")[0]
                tweet_url = f"https://x.com{href}" if href.startswith("/") else href

                # Get author
                author = "@unknown"
                try:
                    author_elem = tweet.locator("div[data-testid='User-Name'] a").first
                    author = author_elem.inner_text(timeout=2000).strip()
                except PlaywrightError:
                    pass

                # Get text
                text = ""
                try:
                    text_elem = tweet.locator("div[data-testid='tweetText']").first
                    text = text_elem.inner_text(timeout=2000).strip()
                except PlaywrightError:
                    pass

                candidates.append(VideoCandidate(
                    url=tweet_url,
                    tweet_id=tweet_id,
                    author=author,
                    text=text or "Video post",
                ))

                self.logger.debug(f"Found video candidate: {tweet_url}")

            except PlaywrightError as e:
                self.logger.debug(f"Error processing tweet: {e}")
                continue

        return candidates

    def find_from_explore(self, max_candidates: int = 20) -> List[VideoCandidate]:
        """
        Find viral videos from Explore → Videos tab.
        This is often better than topic search for finding trending content.
        """
        self.logger.info("Scraping from Explore → Videos feed...")

        try:
            # Navigate to Explore Videos
            self.page.goto("https://x.com/explore/videos", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # Scroll to load content
            self._scroll_feed(steps=10)
            time.sleep(2)

            # Extract candidates
            candidates = self._extract_candidates_from_page(max_candidates)

            self.logger.info(f"Found {len(candidates)} video candidates from Explore")
            return candidates

        except PlaywrightError as exc:
            self.logger.warning(f"Failed to scrape Explore feed: {exc}")
            return []

    def find_from_topic(self, topic: str, max_candidates: int = 20) -> List[VideoCandidate]:
        """
        Find videos by searching for a specific topic.

        Args:
            topic: Search term (e.g., "sports", "fails", "funny")
            max_candidates: Max number of candidates to return

        Returns:
            List of video candidates
        """
        self.logger.info(f"Scraping videos for topic: '{topic}'")

        try:
            # Build search URL with video filter
            query = topic.replace(" ", "%20")
            url = f"https://x.com/search?q={query}&f=video"

            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # Scroll to load more results
            self._scroll_feed(steps=8)
            time.sleep(2)

            # Extract candidates
            candidates = self._extract_candidates_from_page(max_candidates)

            self.logger.info(f"Found {len(candidates)} video candidates for '{topic}'")
            return candidates

        except PlaywrightError as exc:
            self.logger.warning(f"Failed to search for topic '{topic}': {exc}")
            return []

    def find_candidates(
        self,
        topics: Optional[List[str]] = None,
        use_explore: bool = True,
        max_per_source: int = 20,
    ) -> List[VideoCandidate]:
        """
        Find video candidates from multiple sources.

        Args:
            topics: List of topics to search (optional)
            use_explore: Whether to check Explore feed first
            max_per_source: Max candidates per source

        Returns:
            Combined list of unique video candidates
        """
        all_candidates: List[VideoCandidate] = []
        seen_ids = set()

        # Primary source: Explore Videos (usually has best viral content)
        if use_explore:
            explore_candidates = self.find_from_explore(max_candidates=max_per_source)
            for candidate in explore_candidates:
                if candidate.tweet_id not in seen_ids:
                    all_candidates.append(candidate)
                    seen_ids.add(candidate.tweet_id)

        # Secondary source: Topic searches
        if topics:
            for topic in topics:
                topic_candidates = self.find_from_topic(topic, max_candidates=max_per_source)
                for candidate in topic_candidates:
                    if candidate.tweet_id not in seen_ids:
                        all_candidates.append(candidate)
                        seen_ids.add(candidate.tweet_id)

                # Small delay between topic searches
                time.sleep(random.uniform(2, 4))

        self.logger.info(f"Total unique video candidates found: {len(all_candidates)}")

        # Shuffle to randomize which videos we pick
        random.shuffle(all_candidates)

        return all_candidates


__all__ = ["VideoCandidate", "ViralScraper"]
