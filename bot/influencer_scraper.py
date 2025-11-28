from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional

from playwright.sync_api import Error as PlaywrightError, Page


@dataclass
class InfluencerPost:
    url: str
    author: str
    text: str
    video_url: Optional[str]
    tweet_id: str


class InfluencerScraper:
    """Pull real video tweets from Explore → Video or topical searches.

    This scraper prefers the Explore video tab to guarantee a steady stream of
    playable clips. Topic searches are used to bias toward requested themes, but
    the collector will fall back to raw trending videos when a topic yields no
    results so we never return an empty queue.
    """

    def __init__(self, page: Page, logger: logging.Logger, *, debug: bool = False):
        self.page = page
        self.logger = logger
        self.debug = debug

    def _scroll(self, *, steps: int = 8, pause: float = 1.6) -> None:
        for _ in range(steps):
            try:
                self.page.mouse.wheel(0, 2200)
            except PlaywrightError:
                return
            time.sleep(pause)

    def _extract_posts(self) -> List[InfluencerPost]:
        posts: List[InfluencerPost] = []
        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
        except PlaywrightError as exc:
            self.logger.warning("Could not collect tweets: %s", exc)
            return posts

        for tweet in tweets:
            try:
                has_video = tweet.locator("video").count() > 0 or tweet.locator(
                    "div[data-testid='videoPlayer']"
                ).count() > 0
                if not has_video:
                    continue
                text = tweet.locator("div[data-testid='tweetText']").inner_text(timeout=4000)
                link = tweet.locator("a[href*='/status/']").first
                href = link.get_attribute("href") or ""
                if not href:
                    continue
                author_link = tweet.locator("div[data-testid='User-Name'] a").first
                author = author_link.inner_text(timeout=4000)
                tweet_id = self._tweet_id_from_href(href)
                video_src = self._video_source(tweet)
                url = f"https://x.com{href}" if href.startswith("/") else href
                posts.append(
                    InfluencerPost(
                        url=url,
                        author=author,
                        text=text,
                        video_url=video_src,
                        tweet_id=tweet_id,
                    )
                )
            except PlaywrightError:
                continue
        return posts

    def _video_source(self, tweet) -> Optional[str]:
        locators = ["video source", "video", "div[data-testid='videoPlayer'] video"]
        for selector in locators:
            try:
                node = tweet.locator(selector).first
                if node and node.count() > 0:
                    src = node.get_attribute("src")
                    if src:
                        return src
            except PlaywrightError:
                continue
        return None

    def _tweet_id_from_href(self, href: str) -> str:
        match = re.search(r"/status/([0-9]+)", href)
        if match:
            return match.group(1)
        return href.rstrip("/").split("/")[-1] or f"tweet-{int(time.time())}"

    def _navigate(self, url: str, *, label: str) -> bool:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self._scroll()
            return True
        except PlaywrightError as exc:
            self.logger.warning("Failed to load %s: %s", label, exc)
            return False

    def _collect(self, *, label: str) -> List[InfluencerPost]:
        posts = self._extract_posts()
        self.logger.info("Found %d video tweets from %s", len(posts), label)
        if self.debug and posts[:2]:
            for sample in posts[:2]:
                self.logger.debug("Sample tweet %s", sample.url)
        return posts

    def fetch_explore(self) -> List[InfluencerPost]:
        explore_url = "https://x.com/explore/tabs/video"
        if not self._navigate(explore_url, label="Explore → Video"):
            return []
        return self._collect(label="Explore → Video")

    def fetch_topic(self, topic: str) -> List[InfluencerPost]:
        query = topic.replace(" ", "%20")
        url = f"https://x.com/search?q={query}&f=live"
        self.logger.info("Searching for videos about '%s'", topic)
        if not self._navigate(url, label=f"search {topic}"):
            return []
        posts = self._collect(label=f"search '{topic}'")
        return posts

    def gather(self, topics: Iterable[str], *, cap: int) -> List[InfluencerPost]:
        collected: list[InfluencerPost] = []
        seen = set()

        for topic in topics:
            if len(collected) >= cap:
                break
            posts = self.fetch_topic(topic)
            for post in posts:
                if post.tweet_id in seen:
                    continue
                seen.add(post.tweet_id)
                collected.append(post)
                if len(collected) >= cap:
                    break
            if posts:
                continue

        if len(collected) < cap:
            fallback = self.fetch_explore()
            for post in fallback:
                if post.tweet_id in seen:
                    continue
                seen.add(post.tweet_id)
                collected.append(post)
                if len(collected) >= cap:
                    break

        self.logger.info("Total influencer candidates: %d", len(collected))
        return collected


__all__ = ["InfluencerPost", "InfluencerScraper"]
