"""Video scraper for X (Twitter) influencer mode."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from playwright.sync_api import Page, PlaywrightError, TimeoutError as PlaywrightTimeout


@dataclass
class VideoCandidate:
    """Represents a scraped video tweet."""

    tweet_id: str
    tweet_url: str
    tweet_text: str
    author_handle: str
    video_url: Optional[str] = None


class VideoScraper:
    """Scrapes video tweets from X."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def scrape_explore_videos(self, max_videos: int = 30) -> list[VideoCandidate]:
        """
        Scrape videos from X Explore → Videos tab.

        Args:
            max_videos: Maximum number of videos to scrape

        Returns:
            List of VideoCandidate objects
        """
        self.logger.info("Navigating to X Explore → Videos")

        try:
            self.page.goto("https://x.com/explore/tabs/video", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)  # Let content load
        except PlaywrightTimeout:
            self.logger.warning("Timeout loading Explore Videos page")
            return []
        except PlaywrightError as exc:
            self.logger.warning("Error loading Explore Videos: %s", exc)
            return []

        candidates: list[VideoCandidate] = []
        seen_ids: set[str] = set()

        # Scroll to load more content
        for scroll_attempt in range(3):
            self.logger.debug("Scroll attempt %d/3", scroll_attempt + 1)
            try:
                self.page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(2)
            except PlaywrightError:
                break

        # Find all tweet articles
        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
            self.logger.info("Found %d total tweet articles", len(tweets))
        except PlaywrightError as exc:
            self.logger.warning("Error finding tweet articles: %s", exc)
            return []

        for tweet in tweets:
            if len(candidates) >= max_videos:
                break

            try:
                # Check if this tweet contains video
                video_player = tweet.locator("div[data-testid='videoPlayer']").first
                if not video_player.count():
                    continue

                # Extract tweet data
                data = self._extract_tweet_data(tweet)
                if not data:
                    continue

                tweet_id = data["id"]
                if tweet_id in seen_ids:
                    continue

                seen_ids.add(tweet_id)

                candidate = VideoCandidate(
                    tweet_id=tweet_id,
                    tweet_url=data["url"],
                    tweet_text=data["text"],
                    author_handle=data["handle"],
                    video_url=data.get("video_url"),
                )

                candidates.append(candidate)
                self.logger.debug(
                    "Found video candidate: @%s - %s",
                    candidate.author_handle,
                    candidate.tweet_text[:50],
                )

            except PlaywrightError as exc:
                self.logger.debug("Error processing tweet: %s", exc)
                continue

        self.logger.info("Scraped %d video candidates from Explore", len(candidates))
        return candidates

    def _extract_tweet_data(self, tweet) -> Optional[dict[str, str]]:
        """Extract data from a tweet locator."""
        try:
            # Get tweet text
            text_locator = tweet.locator("div[data-testid='tweetText']").first
            text = text_locator.inner_text().strip() if text_locator.count() else ""

            # Get tweet URL and ID
            tweet_href = ""
            try:
                link = tweet.locator("a[href*='/status/']").first
                tweet_href = link.get_attribute("href") or ""
            except PlaywrightError:
                pass

            if not tweet_href:
                return None

            tweet_url = f"https://x.com{tweet_href}" if tweet_href.startswith("/") else tweet_href

            # Extract tweet ID
            tweet_id = ""
            if "/status/" in tweet_href:
                tweet_id = tweet_href.split("/status/")[-1].split("?")[0].split("/")[0]

            if not tweet_id:
                return None

            # Get author handle
            author_handle = ""
            try:
                user_link = tweet.locator("div[data-testid='User-Name'] a").first
                href = user_link.get_attribute("href")
                if href:
                    author_handle = href.strip("/").split("/")[-1]
            except PlaywrightError:
                pass

            # Try to extract video URL (might be in various places)
            video_url = None
            try:
                video_elem = tweet.locator("video").first
                if video_elem.count():
                    video_url = video_elem.get_attribute("src")
            except PlaywrightError:
                pass

            return {
                "id": tweet_id,
                "url": tweet_url,
                "text": text,
                "handle": author_handle,
                "video_url": video_url,
            }

        except PlaywrightError:
            return None

    def search_topic_videos(self, topic: str, max_videos: int = 10) -> list[VideoCandidate]:
        """
        Search for video tweets by topic.

        Args:
            topic: Search topic
            max_videos: Maximum videos to find

        Returns:
            List of VideoCandidate objects
        """
        from urllib.parse import quote_plus

        self.logger.info("Searching for videos about '%s'", topic)
        search_url = f"https://x.com/search?q={quote_plus(topic)}%20filter%3Avideo&src=typed_query&f=live"

        try:
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
        except PlaywrightTimeout:
            self.logger.warning("Timeout searching for topic '%s'", topic)
            return []
        except PlaywrightError as exc:
            self.logger.warning("Error searching for topic '%s': %s", topic, exc)
            return []

        candidates: list[VideoCandidate] = []
        seen_ids: set[str] = set()

        # Scroll once to load more
        try:
            self.page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)
        except PlaywrightError:
            pass

        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
            self.logger.debug("Found %d tweets in search results", len(tweets))
        except PlaywrightError:
            return []

        for tweet in tweets:
            if len(candidates) >= max_videos:
                break

            try:
                # Check for video
                video_player = tweet.locator("div[data-testid='videoPlayer']").first
                if not video_player.count():
                    continue

                data = self._extract_tweet_data(tweet)
                if not data:
                    continue

                tweet_id = data["id"]
                if tweet_id in seen_ids:
                    continue

                seen_ids.add(tweet_id)

                candidate = VideoCandidate(
                    tweet_id=tweet_id,
                    tweet_url=data["url"],
                    tweet_text=data["text"],
                    author_handle=data["handle"],
                    video_url=data.get("video_url"),
                )

                candidates.append(candidate)

            except PlaywrightError:
                continue

        self.logger.info("Found %d video candidates for topic '%s'", len(candidates), topic)
        return candidates
