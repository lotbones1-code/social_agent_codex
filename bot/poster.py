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

    def _open_composer(self) -> bool:
        selectors = [
            "a[aria-label='Post']",
            "div[data-testid='SideNav_NewTweet_Button']",
            "a[href='/compose/post']",
        ]
        for selector in selectors:
            try:
                button = self.page.locator(selector)
                if button.is_visible(timeout=3000):
                    button.click()
                    return True
            except PlaywrightError:
                continue
        self.logger.warning("Could not locate the composer button.")
        return False

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
        if not video_path.exists():
            self.logger.warning("Video %s does not exist.", video_path)
            return False
        if not self._open_composer():
            return False

        # Wait for composer to open
        time.sleep(2)

        try:
            # Find the actual editable div (contenteditable)
            composer = self.page.locator("div[contenteditable='true'][data-testid='tweetTextarea_0']").first
            composer.click()
            time.sleep(0.5)
            # Use keyboard to type since it's contenteditable
            composer.type(caption, delay=50)
            time.sleep(0.5)
        except PlaywrightError as exc:
            self.logger.warning("Could not type caption: %s", exc)
            return False

        if not self._attach_video(video_path):
            return False

        submitted = self._submit()
        if submitted:
            self.logger.info("Post with video %s published successfully.", video_path)
        return submitted

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
