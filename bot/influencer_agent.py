"""Main influencer agent orchestrator."""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page

from bot.influencer_caption import CaptionGenerator
from bot.influencer_downloader import VideoDownloader
from bot.influencer_poster import VideoPoster
from bot.influencer_scraper import VideoCandidate, VideoScraper


class InfluencerAgent:
    """Orchestrates the influencer video repost workflow."""

    def __init__(
        self,
        page: Page,
        config,
        logger: logging.Logger,
    ):
        self.page = page
        self.config = config
        self.logger = logger

        # Initialize components
        inbox_dir = Path("media/influencer_inbox")
        posted_dir = Path("media/influencer_posted")

        self.scraper = VideoScraper(page, logger)
        self.downloader = VideoDownloader(inbox_dir, posted_dir, logger)
        self.poster = VideoPoster(page, logger)

        # Initialize caption generator if OpenAI key available
        self.caption_generator: Optional[CaptionGenerator] = None
        if config.openai_api_key:
            try:
                self.caption_generator = CaptionGenerator(
                    config.openai_api_key,
                    config.openai_model,
                    logger,
                )
                self.logger.info("OpenAI caption generator initialized")
            except Exception as exc:
                self.logger.warning("Failed to initialize OpenAI: %s", exc)

        # Load or initialize state
        self.state_file = Path("logs/influencer_state.json")
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """Load agent state from disk."""
        if self.state_file.exists():
            try:
                with self.state_file.open("r") as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            "last_post_time": None,
            "posts_today": 0,
            "last_date": None,
            "posted_tweet_ids": [],
        }

    def _save_state(self):
        """Save agent state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with self.state_file.open("w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as exc:
            self.logger.warning("Failed to save state: %s", exc)

    def _reset_daily_counter(self):
        """Reset posts counter if it's a new day."""
        today = datetime.now().strftime("%Y-%m-%d")

        if self.state.get("last_date") != today:
            self.logger.info("New day - resetting post counter")
            self.state["last_date"] = today
            self.state["posts_today"] = 0
            self._save_state()

    def run_cycle(self):
        """Run one influencer cycle: scrape → download → post → reply."""
        self.logger.info("=" * 60)
        self.logger.info("INFLUENCER MODE - Starting cycle")
        self.logger.info("=" * 60)

        self._reset_daily_counter()

        # Check if we should post
        if not self._should_post_now():
            next_post_time = self._get_next_post_time()
            wait_seconds = max(60, (next_post_time - datetime.now()).total_seconds())
            self.logger.info("Next post scheduled in %d seconds", int(wait_seconds))
            return

        # Phase 1: Scrape videos
        candidates = self._scrape_videos()

        if not candidates:
            self.logger.warning("No video candidates found")
            return

        # Phase 2: Download videos
        downloaded = self._download_videos(candidates)

        if not downloaded:
            self.logger.warning("No videos downloaded successfully")
            return

        # Phase 3: Post a video
        success = self._post_next_video()

        if success:
            self.state["posts_today"] += 1
            self.state["last_post_time"] = datetime.now().isoformat()
            self._save_state()

        # Phase 4: Optional auto-replies
        if self.config.influencer_reply_targets:
            self._auto_reply_to_targets()

    def _should_post_now(self) -> bool:
        """Check if we should post a video now."""
        # Check daily limit
        posts_today = self.state.get("posts_today", 0)
        max_posts = self.config.influencer_posts_per_day_max

        if posts_today >= max_posts:
            self.logger.info("Daily post limit reached: %d/%d", posts_today, max_posts)
            return False

        # Check time since last post
        last_post_str = self.state.get("last_post_time")
        if not last_post_str:
            return True  # Never posted before

        try:
            last_post = datetime.fromisoformat(last_post_str)
        except Exception:
            return True

        next_post = self._get_next_post_time()

        if datetime.now() >= next_post:
            return True

        return False

    def _get_next_post_time(self) -> datetime:
        """Calculate when the next post should happen."""
        last_post_str = self.state.get("last_post_time")

        if not last_post_str:
            return datetime.now()  # Post immediately if never posted

        try:
            last_post = datetime.fromisoformat(last_post_str)
        except Exception:
            return datetime.now()

        # Calculate delay between posts
        posts_today = self.state.get("posts_today", 0)
        posts_remaining = max(1, self.config.influencer_posts_per_day_max - posts_today)

        # Distribute remaining posts across the rest of the day
        hours_remaining = 24 - datetime.now().hour
        hours_between_posts = max(2, hours_remaining / posts_remaining)

        # Add randomness in STRICT_MODE
        if not self.config.strict_mode:
            # Testing mode: shorter delays
            delay_hours = random.uniform(0.05, 0.2)  # 3-12 minutes
        else:
            # Production mode: realistic delays
            delay_hours = random.uniform(
                hours_between_posts * 0.7, hours_between_posts * 1.3
            )

        next_post = last_post + timedelta(hours=delay_hours)
        return next_post

    def _scrape_videos(self) -> list[VideoCandidate]:
        """Scrape video candidates from X."""
        self.logger.info("Scraping videos from X...")

        # Primary method: Explore → Videos
        candidates = self.scraper.scrape_explore_videos(max_videos=30)

        # Secondary method: Topic-based search (if configured)
        if len(candidates) < 10 and self.config.influencer_video_topics:
            for topic in self.config.influencer_video_topics[:3]:
                topic_vids = self.scraper.search_topic_videos(topic, max_videos=10)
                candidates.extend(topic_vids)

        # Filter out already posted
        posted_ids = set(self.state.get("posted_tweet_ids", []))
        candidates = [c for c in candidates if c.tweet_id not in posted_ids]

        self.logger.info("Found %d new video candidates", len(candidates))
        return candidates

    def _download_videos(self, candidates: list[VideoCandidate]) -> list[Path]:
        """Download videos from candidates."""
        self.logger.info("Downloading videos...")

        downloaded: list[Path] = []

        for candidate in candidates[:10]:  # Download max 10
            video_path = self.downloader.download_video(candidate, self.page)
            if video_path:
                downloaded.append(video_path)

            if len(downloaded) >= 5:  # Enough for now
                break

        self.logger.info("Downloaded %d videos", len(downloaded))
        return downloaded

    def _post_next_video(self) -> bool:
        """Post the next pending video."""
        pending = self.downloader.get_pending_videos()

        if not pending:
            self.logger.warning("No pending videos to post")
            return False

        video_path = pending[0]  # Post oldest first
        tweet_id = video_path.stem  # Filename is tweet ID

        self.logger.info("Posting video: %s", video_path.name)

        # Generate caption
        if self.caption_generator:
            # Try to find candidate info for better captions
            topic = (
                random.choice(self.config.influencer_video_topics)
                if self.config.influencer_video_topics
                else None
            )
            candidate = VideoCandidate(
                tweet_id=tweet_id,
                tweet_url="",
                tweet_text="",
                author_handle="",
            )
            caption = self.caption_generator.generate_caption(candidate, topic)
        else:
            # Fallback caption
            caption = "This is incredible 🔥 #Viral #MustWatch #Trending"

        # Post the video
        success = self.poster.post_video(video_path, caption)

        if success:
            # Mark as posted
            self.downloader.mark_as_posted(video_path)

            # Track posted ID
            if "posted_tweet_ids" not in self.state:
                self.state["posted_tweet_ids"] = []
            self.state["posted_tweet_ids"].append(tweet_id)

            # Keep only recent 1000 IDs
            self.state["posted_tweet_ids"] = self.state["posted_tweet_ids"][-1000:]

            self.logger.info("✅ Video posted successfully!")
            return True

        self.logger.warning("❌ Failed to post video")
        return False

    def _auto_reply_to_targets(self):
        """Auto-reply to big accounts."""
        if not self.config.influencer_reply_targets:
            return

        if not self.caption_generator:
            self.logger.info("Auto-replies require OpenAI API key")
            return

        self.logger.info("Running auto-reply to target accounts...")

        for target_handle in self.config.influencer_reply_targets:
            try:
                self._reply_to_handle(target_handle)
                time.sleep(random.uniform(30, 90))  # Delay between replies
            except Exception as exc:
                self.logger.warning("Error replying to @%s: %s", target_handle, exc)

    def _reply_to_handle(self, handle: str):
        """Reply to recent tweets from a specific handle."""
        self.logger.info("Checking tweets from @%s", handle)

        # Navigate to profile
        profile_url = f"https://x.com/{handle}"
        self.page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        # Find recent tweets
        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
        except Exception:
            self.logger.warning("Could not load tweets from @%s", handle)
            return

        if not tweets:
            return

        # Reply to a few random recent tweets
        num_replies = min(self.config.influencer_replies_per_target, len(tweets))
        selected_tweets = random.sample(tweets, num_replies)

        for tweet in selected_tweets:
            try:
                # Extract tweet data
                text_loc = tweet.locator("div[data-testid='tweetText']").first
                tweet_text = text_loc.inner_text() if text_loc.count() else ""

                link_loc = tweet.locator("a[href*='/status/']").first
                tweet_href = link_loc.get_attribute("href") if link_loc.count() else ""

                if not tweet_text or not tweet_href:
                    continue

                tweet_url = (
                    f"https://x.com{tweet_href}"
                    if tweet_href.startswith("/")
                    else tweet_href
                )

                # Generate reply
                reply_text = self.caption_generator.generate_reply(tweet_text, handle)

                # Post reply
                success = self.poster.reply_to_tweet(tweet_url, reply_text)

                if success:
                    self.logger.info("Replied to @%s", handle)

                time.sleep(random.uniform(10, 30))

            except Exception as exc:
                self.logger.debug("Error processing tweet: %s", exc)
                continue
