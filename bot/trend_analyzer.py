"""Real-time trend analysis using X Trending page."""
from __future__ import annotations

import logging
import time
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout


class TrendAnalyzer:
    """Analyze X trending topics to find what's viral right now."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def get_trending_topics(self, max_topics: int = 10) -> list[dict]:
        """
        Get current trending topics from X Explore → Trending.

        Returns:
            List of trending topics with metadata:
            [
                {
                    "topic": "Thanksgiving",
                    "category": "Sports",
                    "tweet_count": "500K posts",
                    "rank": 1
                },
                ...
            ]
        """
        try:
            self.logger.info("Fetching trending topics from X...")

            # Navigate to X Explore → Trending
            self.page.goto("https://x.com/explore/tabs/trending", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            trending_topics = []

            # Try multiple selectors for trending items
            trend_selectors = [
                "div[data-testid='trend']",
                "div[aria-label*='Trending']",
                "section[aria-labelledby*='accessible-list'] div[role='link']",
            ]

            trends = None
            for selector in trend_selectors:
                try:
                    elems = self.page.locator(selector).all()
                    if len(elems) > 0:
                        trends = elems[:max_topics]
                        self.logger.info(f"Found {len(trends)} trending items with selector: {selector}")
                        break
                except Exception:
                    continue

            if not trends:
                self.logger.warning("Could not find trending topics on page")
                return []

            # Extract trending topic data
            for idx, trend_elem in enumerate(trends, 1):
                try:
                    text = trend_elem.inner_text()
                    lines = [line.strip() for line in text.split('\n') if line.strip()]

                    # Parse trend structure (usually: category, topic, tweet_count)
                    topic = None
                    category = None
                    tweet_count = None

                    for line in lines:
                        # Look for tweet count (e.g., "500K posts", "1.2M posts")
                        if 'post' in line.lower() or 'tweet' in line.lower():
                            tweet_count = line
                        # Category is usually first (e.g., "Sports · Trending", "Entertainment")
                        elif '·' in line and not topic:
                            category = line.split('·')[0].strip()
                        # Topic is the main text (usually the largest/bold text)
                        elif not any(x in line.lower() for x in ['trending', 'post', 'tweet']) and len(line) > 2:
                            if not topic or len(line) > len(topic):
                                topic = line

                    if topic:
                        trending_topics.append({
                            "topic": topic,
                            "category": category or "Unknown",
                            "tweet_count": tweet_count or "N/A",
                            "rank": idx
                        })
                        self.logger.debug(f"Trending #{idx}: {topic} ({category}) - {tweet_count}")

                except Exception as exc:
                    self.logger.debug(f"Failed to parse trend item: {exc}")
                    continue

            self.logger.info(f"✅ Found {len(trending_topics)} trending topics")
            return trending_topics

        except PlaywrightTimeout:
            self.logger.warning("Timeout fetching trending topics")
            return []
        except Exception as exc:
            self.logger.warning(f"Failed to get trending topics: {exc}")
            return []

    def get_trending_hashtags(self, max_hashtags: int = 5) -> list[str]:
        """
        Extract trending hashtags from the Trending page.

        Returns:
            List of trending hashtags (e.g., ["#Thanksgiving", "#NFL"])
        """
        try:
            trending_topics = self.get_trending_topics(max_topics=max_hashtags * 2)

            hashtags = []
            for topic_data in trending_topics:
                topic = topic_data.get("topic", "")

                # If it's already a hashtag, use it
                if topic.startswith("#"):
                    hashtags.append(topic)
                # Otherwise, convert to hashtag (remove spaces, special chars)
                else:
                    # Clean up topic to make valid hashtag
                    clean_topic = "".join(c for c in topic if c.isalnum() or c.isspace())
                    clean_topic = "".join(clean_topic.split())  # Remove spaces

                    if clean_topic and len(clean_topic) > 2:
                        hashtags.append(f"#{clean_topic}")

                if len(hashtags) >= max_hashtags:
                    break

            self.logger.info(f"✅ Extracted {len(hashtags)} trending hashtags: {hashtags}")
            return hashtags

        except Exception as exc:
            self.logger.warning(f"Failed to extract trending hashtags: {exc}")
            return []

    def should_post_about_topic(self, video_topic: str, trending_topics: list[dict]) -> bool:
        """
        Check if a video topic matches current trending topics.

        Args:
            video_topic: The topic of the video candidate
            trending_topics: List of trending topics from get_trending_topics()

        Returns:
            True if video topic is trending right now
        """
        video_topic_lower = video_topic.lower()

        for trend in trending_topics:
            trend_topic = trend.get("topic", "").lower()

            # Check for keyword matches
            if trend_topic in video_topic_lower or video_topic_lower in trend_topic:
                self.logger.info(f"🔥 Video topic '{video_topic}' matches trending: '{trend['topic']}'")
                return True

            # Check individual words
            trend_words = set(trend_topic.split())
            video_words = set(video_topic_lower.split())

            # If 2+ words match, consider it trending
            if len(trend_words & video_words) >= 2:
                self.logger.info(f"🔥 Video topic '{video_topic}' related to trending: '{trend['topic']}'")
                return True

        return False


__all__ = ["TrendAnalyzer"]
