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
        try:
            self.logger.info("Opening composer page…")
            self.page.goto("https://x.com/compose/post", wait_until="networkidle")
            self.page.wait_for_selector(
                "div[data-testid='tweetTextarea_0'] div[contenteditable='true']",
                timeout=15000,
            )
            return True
        except PlaywrightError as exc:
            self.logger.warning("Could not open composer: %s", exc)
            return False

    def _attach_video(self, video_path: Path) -> bool:
        """Attach video reliably across all 2025 X upload variants."""
        try:
            self.logger.info("Waiting for upload zone…")
            # Ensure the upload zone renders
            self.page.wait_for_selector("input[type='file']", timeout=20000)
            
            # Try new 2025 input selector first
            candidates = [
                "input[type='file'][accept*='video']",
                "input[data-testid='fileInput']",
                "//input[@type='file']",
            ]
            
            upload_input = None
            for selector in candidates:
                try:
                    el = self.page.locator(selector).first
                    el.wait_for(state="attached", timeout=5000)
                    upload_input = el
                    break
                except:
                    continue

            if upload_input is None:
                self.logger.warning("Could not find any working file input.")
                return False
            
            self.logger.info("Setting video file…")
            upload_input.set_input_files(str(video_path))

            # Wait for upload progress to finish
            self.logger.info("Waiting for upload to finish…")
            try:
                # Progressbar appears FIRST then disappears
                self.page.wait_for_selector("div[role='progressbar']", timeout=15000)
                self.page.wait_for_selector("div[role='progressbar']", state="detached", timeout=45000)
            except:
                pass  # X sometimes doesn’t show progressbar at all

            # Confirm media preview attached
            self.page.wait_for_selector("div[data-testid='media-preview']", timeout=30000)
            return True

        except PlaywrightError as exc:
            self.logger.warning(f"Upload failed: {exc}")
            return False

    def _submit(self) -> bool:
        selectors = [
            "button[data-testid='tweetButtonInline']",
            "div[data-testid='tweetButtonInline']",
            "button[role='button'][data-testid='tweetButtonInline']",
            "div[role='button'][data-testid='tweetButtonInline']",
        ]

        for sel in selectors:
            try:
                btn = self.page.wait_for_selector(sel, timeout=8000)
                if btn:
                    btn.scroll_into_view_if_needed()
                    self.page.wait_for_timeout(200)
                    try:
                        btn.click(force=True)
                        self.logger.info("✔ Successfully clicked Post button via: " + sel)
                        return True
                    except:
                        # Try JS click fallback
                        self.page.evaluate("(el) => el.click()", btn)
                        self.logger.info("✔ JS clicked Post button via: " + sel)
                        return True
            except:
                continue

        self.logger.warning("Failed to submit the post: no tweet button matched.")
        return False

    def _latest_post_url(self) -> Optional[str]:
        try:
            profile = self.page.locator("a[aria-label='Profile']").first
            profile_href = profile.get_attribute("href")
            if not profile_href:
                return None
            profile_url = profile_href if profile_href.startswith("http") else f"https://x.com{profile_href}"
            self.page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_timeout(2000)
            status_link = self.page.locator("article[data-testid='tweet'] a[href*='/status/']").first
            href = status_link.get_attribute("href")
            if href:
                return href if href.startswith("http") else f"https://x.com{href}"
        except PlaywrightError:
            return None
        return None

    def post_video(self, caption: str, video_path: Path) -> Optional[str]:
        if not video_path.exists():
            self.logger.warning("Video %s does not exist.", video_path)
            return None
        if not self._open_composer():
            return None
        self.logger.info("Typing caption into composer…")
        try:
            composer = self.page.locator("div[data-testid='tweetTextarea_0'] div[contenteditable='true']").first
            composer.wait_for(state="visible", timeout=15000)
            composer.click()
            composer.fill(caption)
        except PlaywrightError as exc:
            self.logger.warning("Could not type caption: %s", exc)
            return None
        self.logger.info("Caption typed successfully.")

        self.logger.info("Uploading video to composer…")
        if not self._attach_video(video_path):
            return None

        submitted = self._submit()
        if not submitted:
            return None

        posted_url = self._latest_post_url()
        if posted_url:
            self.logger.info("Posted influencer tweet successfully: %s", posted_url)
        else:
            self.logger.info("Post with video %s published successfully.", video_path)
        return posted_url

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
