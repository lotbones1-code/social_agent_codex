"""Video downloader for influencer mode."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests
from playwright.sync_api import Page, Error as PlaywrightError

from bot.influencer_scraper import VideoCandidate


class VideoDownloader:
    """Downloads videos from X tweets."""

    def __init__(self, inbox_dir: Path, posted_dir: Path, logger: logging.Logger):
        self.inbox_dir = inbox_dir
        self.posted_dir = posted_dir
        self.logger = logger

        # Ensure directories exist
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.posted_dir.mkdir(parents=True, exist_ok=True)

    def download_video(self, candidate: VideoCandidate, page: Page) -> Optional[Path]:
        """
        Download video from a tweet.

        Args:
            candidate: VideoCandidate with tweet info
            page: Playwright Page for navigating to tweet

        Returns:
            Path to downloaded video file, or None if failed
        """
        output_path = self.inbox_dir / f"{candidate.tweet_id}.mp4"

        # Skip if already downloaded
        if output_path.exists():
            self.logger.info("Video %s already downloaded", candidate.tweet_id)
            return output_path

        # Also check if already posted
        posted_path = self.posted_dir / f"{candidate.tweet_id}.mp4"
        if posted_path.exists():
            self.logger.info("Video %s already posted", candidate.tweet_id)
            return None

        self.logger.info("Downloading video from tweet %s", candidate.tweet_id)

        # Method 1: Try direct video URL if available
        if candidate.video_url:
            success = self._download_direct(candidate.video_url, output_path)
            if success:
                return output_path

        # Method 2: Navigate to tweet and extract video
        success = self._download_from_page(candidate, page, output_path)
        if success:
            return output_path

        self.logger.warning("Failed to download video from tweet %s", candidate.tweet_id)
        return None

    def _download_direct(self, video_url: str, output_path: Path) -> bool:
        """Download video directly from URL."""
        try:
            self.logger.debug("Attempting direct download from %s", video_url[:100])
            response = requests.get(video_url, stream=True, timeout=60)
            response.raise_for_status()

            with output_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            if output_path.stat().st_size > 1000:  # At least 1KB
                self.logger.info("Direct download successful: %s", output_path.name)
                return True

            output_path.unlink(missing_ok=True)
            return False

        except Exception as exc:
            self.logger.debug("Direct download failed: %s", exc)
            output_path.unlink(missing_ok=True)
            return False

    def _download_from_page(self, candidate: VideoCandidate, page: Page, output_path: Path) -> bool:
        """Navigate to tweet page and extract video."""
        try:
            self.logger.debug("Navigating to tweet %s", candidate.tweet_url)
            page.goto(candidate.tweet_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)  # Let video load

            # Try to find video element
            video_locator = page.locator("video").first
            if not video_locator.count():
                self.logger.debug("No video element found on page")
                return False

            video_src = video_locator.get_attribute("src")
            if not video_src:
                self.logger.debug("Video element has no src attribute")
                return False

            # Download from extracted src
            return self._download_direct(video_src, output_path)

        except PlaywrightError as exc:
            self.logger.debug("Error navigating to tweet page: %s", exc)
            return False

    def mark_as_posted(self, video_path: Path) -> bool:
        """
        Move video from inbox to posted directory.

        Args:
            video_path: Path to video in inbox

        Returns:
            True if moved successfully
        """
        try:
            if not video_path.exists():
                self.logger.warning("Video file not found: %s", video_path)
                return False

            posted_path = self.posted_dir / video_path.name

            # Move file
            video_path.rename(posted_path)
            self.logger.info("Marked video as posted: %s", video_path.name)
            return True

        except Exception as exc:
            self.logger.warning("Failed to mark video as posted: %s", exc)
            return False

    def get_pending_videos(self) -> list[Path]:
        """Get list of videos in inbox ready to post."""
        return sorted(self.inbox_dir.glob("*.mp4"))

    def cleanup_old_videos(self, max_age_days: int = 7):
        """Remove old videos from posted directory."""
        import time as time_module
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)

        for video_path in self.posted_dir.glob("*.mp4"):
            try:
                mtime = datetime.fromtimestamp(video_path.stat().st_mtime)
                if mtime < cutoff:
                    video_path.unlink()
                    self.logger.info("Cleaned up old video: %s", video_path.name)
            except Exception as exc:
                self.logger.debug("Error cleaning up %s: %s", video_path.name, exc)
