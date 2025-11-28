"""Hybrid video downloader with Premium+ and yt-dlp fallback."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError, Page, Download, TimeoutError as PlaywrightTimeout


class HybridDownloader:
    """Download videos using Premium+ button, with yt-dlp fallback."""

    def __init__(self, page: Page, download_dir: Path, logger: logging.Logger):
        self.page = page
        self.download_dir = download_dir
        self.logger = logger
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _try_premium_download(self, tweet_url: str, target_path: Path) -> bool:
        """Try to download using Premium+ button (click settings → Download video)."""
        try:
            self.logger.info("Trying Premium+ download button...")

            # Navigate to the tweet
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Find the video player
            video_player = self.page.locator("div[data-testid='videoPlayer']").first
            if not video_player.is_visible(timeout=3000):
                self.logger.debug("No video player found")
                return False

            # Hover over video to show controls
            video_player.hover()
            time.sleep(1)

            # Click the video settings menu (three dots icon)
            settings_selectors = [
                "div[data-testid='videoPlayer'] button[aria-label='More']",
                "div[data-testid='videoPlayer'] div[aria-label='More']",
                "button[aria-haspopup='menu']",
            ]

            settings_button = None
            for selector in settings_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        settings_button = btn
                        self.logger.info(f"Found settings menu button")
                        break
                except PlaywrightError:
                    continue

            if not settings_button:
                self.logger.debug("Video settings menu not found")
                return False

            # Click settings to open menu
            settings_button.click()
            time.sleep(1)

            # Click "Download video" from the menu
            download_menu_selectors = [
                "div[role='menuitem']:has-text('Download video')",
                "a[role='menuitem']:has-text('Download video')",
                "[data-testid='downloadVideo']",
                "div[role='menuitem'] span:has-text('Download')",
            ]

            download_menu_item = None
            for selector in download_menu_selectors:
                try:
                    item = self.page.locator(selector).first
                    if item.is_visible(timeout=2000):
                        download_menu_item = item
                        self.logger.info(f"Found 'Download video' menu item")
                        break
                except PlaywrightError:
                    continue

            if not download_menu_item:
                self.logger.debug("'Download video' menu item not found - Premium+ may not be enabled")
                return False

            # Click download and wait for file
            with self.page.expect_download(timeout=30000) as download_info:
                download_menu_item.click()

            download: Download = download_info.value
            download.save_as(target_path)

            self.logger.info(f"✅ Premium+ download successful: {target_path}")
            return True

        except (PlaywrightError, PlaywrightTimeout) as exc:
            self.logger.debug(f"Premium+ download failed: {exc}")
            return False
        except Exception as exc:
            self.logger.debug(f"Premium+ download error: {exc}")
            return False

    def _try_ytdlp_download(self, tweet_url: str, target_path: Path) -> bool:
        """Try to download using yt-dlp (highest quality)."""
        try:
            self.logger.info("Trying yt-dlp download (highest quality)...")

            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                # Download highest quality video+audio, merge if needed
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                # Merge into mp4
                "--merge-output-format", "mp4",
                "-o", str(target_path),
                tweet_url
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0 and target_path.exists():
                self.logger.info(f"✅ yt-dlp download successful (highest quality): {target_path}")
                return True
            else:
                self.logger.debug(f"yt-dlp failed: {result.stderr}")
                return False

        except FileNotFoundError:
            self.logger.warning("yt-dlp not installed. Install with: pip install yt-dlp")
            return False
        except subprocess.TimeoutExpired:
            self.logger.debug("yt-dlp download timed out")
            return False
        except Exception as exc:
            self.logger.debug(f"yt-dlp error: {exc}")
            return False

    def _try_direct_extraction(self, tweet_url: str, target_path: Path) -> bool:
        """Try to extract video URL directly from page."""
        try:
            self.logger.info("Trying direct video extraction...")

            # Navigate to tweet if not already there
            if not self.page.url.startswith(tweet_url):
                self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

            # Try to find video element with src
            video_selectors = [
                "video source",
                "video",
            ]

            video_url = None
            for selector in video_selectors:
                try:
                    elem = self.page.locator(selector).first
                    if elem.count() > 0:
                        src = elem.get_attribute("src")
                        if src and src.startswith("http"):
                            video_url = src
                            break
                except PlaywrightError:
                    continue

            if not video_url:
                self.logger.debug("Could not extract video URL from page")
                return False

            self.logger.info(f"Found video URL: {video_url[:80]}...")

            # Download using curl
            import requests
            response = requests.get(video_url, stream=True, timeout=60)
            response.raise_for_status()

            with target_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)

            self.logger.info(f"✅ Direct download successful: {target_path}")
            return True

        except Exception as exc:
            self.logger.debug(f"Direct extraction failed: {exc}")
            return False

    def download_from_tweet(self, tweet_url: str, filename_hint: str) -> Optional[Path]:
        """
        Download video from tweet URL using multiple methods.

        Tries in order:
        1. Premium+ download button (if available)
        2. yt-dlp (if installed)
        3. Direct video URL extraction

        Args:
            tweet_url: URL of the tweet with video
            filename_hint: Suggested filename (without extension)

        Returns:
            Path to downloaded video, or None if all methods failed
        """
        target_path = self.download_dir / f"{filename_hint}.mp4"

        # Remove existing file if present
        if target_path.exists():
            target_path.unlink()

        # Try methods in order
        methods = [
            ("Premium+", self._try_premium_download),
            ("yt-dlp", self._try_ytdlp_download),
            ("Direct extraction", self._try_direct_extraction),
        ]

        for method_name, method_func in methods:
            try:
                if method_func(tweet_url, target_path):
                    # Verify file exists and has content
                    if target_path.exists() and target_path.stat().st_size > 1024:
                        self.logger.info(f"Downloaded successfully using {method_name}")
                        return target_path
                    else:
                        self.logger.debug(f"{method_name} created invalid file")
            except Exception as exc:
                self.logger.debug(f"{method_name} exception: {exc}")
                continue

        self.logger.warning(f"All download methods failed for {tweet_url}")
        return None


__all__ = ["HybridDownloader"]
