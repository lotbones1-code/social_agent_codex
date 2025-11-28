"""Engagement actions: likes, retweets, replies."""
from __future__ import annotations

import logging
import random
import time
from typing import List, Optional

from playwright.sync_api import Error as PlaywrightError, Page

from .viral_scraper import VideoCandidate


class EngagementModule:
    """Handle engagement actions to grow the account."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def like_tweet(self, tweet_url: str) -> bool:
        """Like a tweet."""
        try:
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)

            like_button = self.page.locator("div[data-testid='like']").first
            if like_button.is_visible(timeout=3000):
                like_button.click()
                time.sleep(1)
                self.logger.info(f"Liked: {tweet_url}")
                return True
            return False
        except PlaywrightError as exc:
            self.logger.debug(f"Could not like {tweet_url}: {exc}")
            return False

    def retweet(self, tweet_url: str) -> bool:
        """Retweet a tweet."""
        try:
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(1)

            retweet_button = self.page.locator("div[data-testid='retweet']").first
            if retweet_button.is_visible(timeout=3000):
                retweet_button.click()
                time.sleep(0.5)

                # Click the "Repost" option in the menu
                repost_option = self.page.get_by_text("Repost").first
                if repost_option.is_visible(timeout=2000):
                    repost_option.click()
                    time.sleep(1)
                    self.logger.info(f"Retweeted: {tweet_url}")
                    return True
            return False
        except PlaywrightError as exc:
            self.logger.debug(f"Could not retweet {tweet_url}: {exc}")
            return False

    def engage_with_sources(
        self,
        candidates: List[VideoCandidate],
        like: bool = True,
        retweet: bool = False,
        max_actions: int = 5,
    ) -> int:
        """
        Engage with source tweets (like/retweet).

        Args:
            candidates: List of video candidates to engage with
            like: Whether to like tweets
            retweet: Whether to retweet them
            max_actions: Max number of engagements

        Returns:
            Number of successful engagements
        """
        self.logger.info(f"Engaging with up to {max_actions} source tweets...")

        # Shuffle and limit
        shuffled = random.sample(candidates, min(len(candidates), max_actions * 2))
        actions = 0

        for candidate in shuffled:
            if actions >= max_actions:
                break

            # Random delay between actions
            time.sleep(random.uniform(2, 5))

            # Like
            if like and random.random() > 0.3:  # 70% chance to like
                if self.like_tweet(candidate.url):
                    actions += 1

            # Retweet (less frequent)
            if retweet and random.random() > 0.7:  # 30% chance to retweet
                if self.retweet(candidate.url):
                    actions += 1

            if actions >= max_actions:
                break

        self.logger.info(f"Completed {actions} engagement actions")
        return actions


__all__ = ["EngagementModule"]
