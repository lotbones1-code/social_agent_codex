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
        url = f"https://x.com/search?q={query}&f=live"
        self.logger.info("Searching for videos about '%s'", topic)
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError as exc:
            self.logger.warning("Failed to load search page: %s", exc)
            return []

        self._scroll(steps=6)

        posts: List[ScrapedPost] = []
        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
        except PlaywrightError as exc:
            self.logger.warning("Could not collect tweets: %s", exc)
            return []

        for tweet in tweets:
            try:
                if tweet.locator("video").count() == 0 and tweet.locator("div[data-testid='videoPlayer']").count() == 0:
                    continue
                text = tweet.locator("div[data-testid='tweetText']").inner_text(timeout=3000)
                link = tweet.locator("a[href*='/status/']").first
                href = link.get_attribute("href") or ""
                author_link = tweet.locator("div[data-testid='User-Name'] a").first
                author = author_link.inner_text(timeout=3000)
                video_src = None
                if tweet.locator("video source").count() > 0:
                    try:
                        video_src = tweet.locator("video source").first.get_attribute("src")
                    except PlaywrightError:
                        video_src = None
                if not video_src and tweet.locator("video").count() > 0:
                    try:
                        video_src = tweet.locator("video").first.get_attribute("src")
                    except PlaywrightError:
                        video_src = None
                posts.append(
                    ScrapedPost(
                        url=f"https://x.com{href}" if href.startswith("/") else href,
                        author=author,
                        text=text,
                        video_url=video_src,
                    )
                )
            except PlaywrightError:
                continue
            if len(posts) >= 10:
                break
        self.logger.info("Found %d candidate video posts for topic '%s'", len(posts), topic)
        return posts


__all__ = ["ScrapedPost", "VideoScraper"]
