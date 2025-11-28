from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, Page


class VideoPoster:
    """Handle composing and publishing posts on X."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def _open_composer(self) -> Optional[Page]:
        """
        Open composer in a new tab (more reliable than clicking button).
        Returns the new page with composer, or None if failed.
        """
        try:
            self.logger.info("Opening composer in new tab...")
            context = self.page.context
            composer_page = context.new_page()
            composer_page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=60000)

            # Wait for the textarea to be ready
            composer_page.wait_for_selector(
                "div[data-testid='tweetTextarea_0'] div[contenteditable='true']",
                timeout=20000
            )
            self.logger.info("Composer page ready")
            return composer_page
        except Exception as exc:
            self.logger.warning(f"Could not open composer: {exc}")
            return None

    def _attach_video(self, video_path: Path) -> bool:
        try:
            upload_input = self.page.locator("input[data-testid='fileInput']").first
            upload_input.set_input_files(str(video_path))
            # Wait for video to upload and process (can take longer for larger videos)
            time.sleep(3)
            self.page.wait_for_selector("div[data-testid='media-preview']", timeout=90000)
            self.logger.info("Video uploaded successfully")
            # Wait a bit more for processing
            time.sleep(2)
            return True
        except PlaywrightTimeout:
            self.logger.warning("Video upload timed out for %s", video_path)
            return False
        except PlaywrightError as exc:
            self.logger.warning("Failed to attach video %s: %s", video_path, exc)
            return False

    def _submit(self) -> bool:
        try:
            self.page.locator("div[data-testid='tweetButtonInline']").click()
            time.sleep(4)
            return True
        except PlaywrightError as exc:
            self.logger.warning("Failed to submit the post: %s", exc)
            return False

    def post_video(self, caption: str, video_path: Path) -> bool:
        """Post a video with caption to X."""
        if not video_path.exists():
            self.logger.warning("Video %s does not exist.", video_path)
            return False

        # Open composer in new tab
        composer_page = self._open_composer()
        if not composer_page:
            return False

        try:
            # Type caption
            self.logger.info("Typing caption...")
            composer = composer_page.locator("div[data-testid='tweetTextarea_0'] div[contenteditable='true']").first
            composer.click()
            time.sleep(0.5)
            composer.type(caption, delay=50)
            time.sleep(0.5)
            self.logger.info("Caption typed successfully")

            # Upload video
            self.logger.info("Uploading video: %s", video_path)
            upload_input = composer_page.locator("input[data-testid='fileInput']").first
            upload_input.set_input_files(str(video_path))

            # Wait for upload with progress tracking
            time.sleep(3)
            try:
                composer_page.wait_for_selector("div[data-testid='media-preview']", timeout=90000)
                self.logger.info("Video uploaded successfully")
                time.sleep(2)  # Let it process
            except PlaywrightTimeout:
                self.logger.warning("Video upload timed out")
                composer_page.close()
                return False

            # Submit the post
            self.logger.info("Submitting post...")
            post_button = composer_page.locator("div[data-testid='tweetButton']").first
            post_button.click()
            time.sleep(5)  # Wait for post to go through

            self.logger.info("Post with video %s published successfully!", video_path)

            # Close composer tab
            composer_page.close()
            return True

        except Exception as exc:
            self.logger.warning("Failed to post video: %s", exc)
            try:
                composer_page.close()
            except:
                pass
            return False

    def repost(self, post_url: str) -> bool:
        try:
            self.page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            button = self.page.locator("div[data-testid='retweet']").first
            button.click()
            repost_option = self.page.get_by_text("Repost").first
            repost_option.click()
            time.sleep(2)
            self.logger.info("Reposted %s", post_url)
            return True
        except PlaywrightError as exc:
            self.logger.warning("Failed to repost %s: %s", post_url, exc)
            return False

    def like(self, post_url: str) -> bool:
        try:
            self.page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            like_button = self.page.locator("div[data-testid='like']").first
            like_button.click()
            time.sleep(1)
            return True
        except PlaywrightError as exc:
            self.logger.debug("Could not like %s: %s", post_url, exc)
            return False

    def follow_author(self, post_url: str) -> bool:
        try:
            self.page.goto(post_url, wait_until="domcontentloaded", timeout=60000)
            follow_button = self.page.get_by_text("Follow").first
            if follow_button.is_visible(timeout=3000):
                follow_button.click()
                time.sleep(1)
                return True
            return False
        except PlaywrightError as exc:
            self.logger.debug("Could not follow from %s: %s", post_url, exc)
            return False


__all__ = ["VideoPoster"]
