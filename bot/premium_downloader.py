"""Video downloader that uses X Premium+ download feature."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError, Page, Download


class PremiumDownloader:
    """Download videos using X Premium+ built-in download button."""

    def __init__(self, page: Page, download_dir: Path, logger: logging.Logger):
        self.page = page
        self.download_dir = download_dir
        self.logger = logger
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def download_from_tweet(self, tweet_url: str, filename_hint: str) -> Optional[Path]:
        """
        Download video from a tweet URL using Premium+ download button.

        Args:
            tweet_url: URL of the tweet containing the video
            filename_hint: Suggested filename (without extension)

        Returns:
            Path to downloaded video, or None if failed
        """
        self.logger.info(f"Navigating to tweet: {tweet_url}")

        try:
            # Navigate to the tweet
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            # Find the video player
            video_player = self.page.locator("div[data-testid='videoPlayer']").first
            if not video_player.is_visible(timeout=5000):
                self.logger.warning("No video found in tweet")
                return None

            # Hover over video to show controls
            video_player.hover()
            time.sleep(1)

            # Look for the download button (Premium+ feature)
            # Try multiple selectors as X UI changes
            download_selectors = [
                "div[aria-label='Download']",
                "button[aria-label='Download']",
                "[data-testid='videoDownloadButton']",
                "div[role='button']:has-text('Download')",
            ]

            download_button = None
            for selector in download_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        download_button = btn
                        break
                except PlaywrightError:
                    continue

            if not download_button:
                self.logger.warning("Download button not found - is this account Premium+?")
                return None

            # Start download
            self.logger.info("Clicking download button...")
            with self.page.expect_download(timeout=60000) as download_info:
                download_button.click()

            download: Download = download_info.value

            # Save to target path
            target_path = self.download_dir / f"{filename_hint}.mp4"
            download.save_as(target_path)

            self.logger.info(f"Video downloaded successfully: {target_path}")
            return target_path

        except PlaywrightError as exc:
            self.logger.warning(f"Failed to download video from {tweet_url}: {exc}")
            return None
        except Exception as exc:
            self.logger.warning(f"Unexpected error downloading video: {exc}")
            return None


__all__ = ["PremiumDownloader"]
