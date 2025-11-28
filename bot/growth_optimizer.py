"""Strategic engagement to grow followers organically."""
from __future__ import annotations

import logging
import random
import time
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout


class GrowthOptimizer:
    """Organic follower growth through strategic engagement."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def engage_with_viral_accounts(
        self,
        topic: str,
        max_accounts: int = 5,
        actions_per_account: int = 3,
    ) -> int:
        """
        Find and engage with viral accounts in your niche.

        Strategy:
        1. Search for trending topic
        2. Find high-engagement posts
        3. Like, retweet, and reply to their best content
        4. Follow strategic accounts

        Returns:
            Number of successful engagements
        """
        try:
            self.logger.info(f"Growing followers by engaging with '{topic}' accounts...")

            # Search for topic
            search_url = f"https://x.com/search?q={topic.replace(' ', '%20')}&src=typed_query&f=top"
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            engagements = 0
            accounts_engaged = set()

            # Find high-engagement posts
            articles = self.page.locator("article[data-testid='tweet']").all()[:20]

            for article in articles:
                if len(accounts_engaged) >= max_accounts:
                    break

                try:
                    # Get author handle
                    author_link = article.locator("a[href*='/status/']").first
                    if not author_link.count():
                        continue

                    href = author_link.get_attribute("href")
                    if not href:
                        continue

                    author_handle = href.split("/")[1] if "/" in href else None
                    if not author_handle or author_handle in accounts_engaged:
                        continue

                    # Check engagement metrics
                    text = article.inner_text()

                    # Look for high engagement (replies, likes, retweets)
                    has_high_engagement = any([
                        "K" in text and any(x in text for x in ["reply", "retweet", "like"]),
                        "M" in text,  # Million views/likes
                    ])

                    if not has_high_engagement:
                        continue

                    self.logger.info(f"Engaging with high-value account: @{author_handle}")
                    accounts_engaged.add(author_handle)

                    # Strategic engagement actions
                    actions_done = 0

                    # 1. Like the post
                    try:
                        like_button = article.locator("button[data-testid='like']").first
                        if like_button.is_visible(timeout=2000):
                            like_button.click()
                            engagements += 1
                            actions_done += 1
                            self.logger.debug("  ✅ Liked post")
                            time.sleep(random.uniform(1, 2))
                    except Exception:
                        pass

                    # 2. Retweet (if engagement is VERY high)
                    if "M" in text or ("K" in text and random.random() < 0.3):
                        try:
                            retweet_button = article.locator("button[data-testid='retweet']").first
                            if retweet_button.is_visible(timeout=2000):
                                retweet_button.click()
                                time.sleep(1)

                                # Click "Retweet" in menu
                                confirm = self.page.locator("div[data-testid='retweetConfirm']").first
                                if confirm.is_visible(timeout=2000):
                                    confirm.click()
                                    engagements += 1
                                    actions_done += 1
                                    self.logger.debug("  ✅ Retweeted post")
                                    time.sleep(random.uniform(1, 2))
                        except Exception:
                            pass

                    # 3. Follow the account (if they have high engagement)
                    if "M" in text:  # Only follow mega-viral accounts
                        try:
                            # Click on profile
                            profile_link = article.locator(f"a[href='/{author_handle}']").first
                            if profile_link.is_visible(timeout=2000):
                                profile_link.click()
                                time.sleep(2)

                                # Click follow button
                                follow_button = self.page.locator("button[data-testid*='follow']").first
                                if follow_button.is_visible(timeout=2000):
                                    button_text = follow_button.inner_text().lower()
                                    if "follow" in button_text and "following" not in button_text:
                                        follow_button.click()
                                        engagements += 1
                                        actions_done += 1
                                        self.logger.debug(f"  ✅ Followed @{author_handle}")
                                        time.sleep(random.uniform(2, 3))

                                # Go back to search
                                self.page.go_back()
                                time.sleep(2)
                        except Exception:
                            pass

                    if actions_done > 0:
                        self.logger.info(f"  Completed {actions_done} engagement actions")

                    # Rate limiting
                    time.sleep(random.uniform(3, 6))

                    if actions_done >= actions_per_account:
                        break

                except Exception as exc:
                    self.logger.debug(f"Failed to engage with account: {exc}")
                    continue

            self.logger.info(f"✅ Completed {engagements} growth engagements with {len(accounts_engaged)} accounts")
            return engagements

        except PlaywrightTimeout:
            self.logger.warning("Timeout during growth engagement")
            return 0
        except Exception as exc:
            self.logger.warning(f"Growth engagement failed: {exc}")
            return 0

    def engage_with_trending_hashtag(self, hashtag: str, max_actions: int = 10) -> int:
        """
        Engage with posts in a trending hashtag to gain visibility.

        Args:
            hashtag: Trending hashtag (with or without #)
            max_actions: Maximum engagement actions

        Returns:
            Number of successful engagements
        """
        try:
            # Clean hashtag
            if not hashtag.startswith("#"):
                hashtag = f"#{hashtag}"

            hashtag_clean = hashtag[1:]  # Remove # for URL

            self.logger.info(f"Engaging with trending hashtag: {hashtag}")

            # Search for hashtag
            search_url = f"https://x.com/hashtag/{hashtag_clean}?src=hashtag_click&f=top"
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            engagements = 0

            # Find top posts
            articles = self.page.locator("article[data-testid='tweet']").all()[:max_actions * 2]

            for article in articles[:max_actions]:
                if engagements >= max_actions:
                    break

                try:
                    # Like the post
                    like_button = article.locator("button[data-testid='like']").first
                    if like_button.is_visible(timeout=2000):
                        # Check if not already liked
                        aria_label = like_button.get_attribute("aria-label") or ""
                        if "unlike" not in aria_label.lower():
                            like_button.click()
                            engagements += 1
                            self.logger.debug(f"  ✅ Liked post in {hashtag}")
                            time.sleep(random.uniform(2, 4))

                except Exception as exc:
                    self.logger.debug(f"Failed to engage with hashtag post: {exc}")
                    continue

            self.logger.info(f"✅ Completed {engagements} engagements on {hashtag}")
            return engagements

        except Exception as exc:
            self.logger.warning(f"Trending hashtag engagement failed: {exc}")
            return 0


__all__ = ["GrowthOptimizer"]
