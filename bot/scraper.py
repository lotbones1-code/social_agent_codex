from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional

from playwright.sync_api import Error as PlaywrightError, Page


@dataclass
class ScrapedPost:
    url: str
    author: str
    text: str
    video_url: Optional[str]


class VideoScraper:
    """Navigate X search results and surface posts that contain playable videos."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def _scroll(self, *, steps: int = 5) -> None:
        for _ in range(steps):
            try:
                self.page.mouse.wheel(0, 2000)
            except PlaywrightError:
                return
            time.sleep(1.5)

    def search_topic(self, topic: str) -> List[ScrapedPost]:
        query = topic.replace(" ", "%20")
        # Use X's video filter to find only video posts
        url = f"https://x.com/search?q={query}&f=video"
        self.logger.info("Searching for videos about '%s'", topic)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError as exc:
            self.logger.warning("Failed to load search page: %s", exc)
            return []

        # Wait for content to load
        time.sleep(3)
        self._scroll(steps=8)
        time.sleep(2)

        posts: List[ScrapedPost] = []
        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
            self.logger.info("Found %d total tweets in search results", len(tweets))
        except PlaywrightError as exc:
            self.logger.warning("Could not collect tweets: %s", exc)
            return []

        video_count = 0
        for tweet in tweets:
            try:
                # Check if tweet has video
                has_video = tweet.locator("video").count() > 0 or tweet.locator("div[data-testid='videoPlayer']").count() > 0
                if not has_video:
                    continue

                video_count += 1
                self.logger.debug("Found tweet #%d with video", video_count)

                # Get tweet text (may be empty)
                text = ""
                try:
                    text = tweet.locator("div[data-testid='tweetText']").inner_text(timeout=3000)
                except PlaywrightError:
                    pass

                # Get tweet URL
                link = tweet.locator("a[href*='/status/']").first
                href = link.get_attribute("href") or ""
                if not href:
                    continue

                # Get author
                author = "@unknown"
                try:
                    author_link = tweet.locator("div[data-testid='User-Name'] a").first
                    author = author_link.inner_text(timeout=3000)
                except PlaywrightError:
                    pass

                # Try to get video URL
                video_src = None
                if tweet.locator("video source").count() > 0:
                    try:
                        video_src = tweet.locator("video source").first.get_attribute("src")
                    except PlaywrightError:
                        pass
                if not video_src and tweet.locator("video").count() > 0:
                    try:
                        video_src = tweet.locator("video").first.get_attribute("src")
                    except PlaywrightError:
                        pass

                tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                self.logger.info("Video tweet found: %s (video_src=%s)", tweet_url, "YES" if video_src else "NO")

                # Add post even if we don't have direct video URL yet
                # We can extract it later when we open the tweet
                posts.append(
                    ScrapedPost(
                        url=tweet_url,
                        author=author,
                        text=text or "Video post",
                        video_url=video_src,
                    )
                )
            except PlaywrightError as e:
                self.logger.debug("Error processing tweet: %s", e)
                continue
            if len(posts) >= 20:
                break
        self.logger.info("Found %d candidate video posts for topic '%s'", len(posts), topic)
        return posts


__all__ = ["ScrapedPost", "VideoScraper"]
