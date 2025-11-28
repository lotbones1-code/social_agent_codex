from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, Page


class VideoPoster:
    """Handle composing and publishing posts on X."""

    def __init__(self, page: Page, logger: logging.Logger, dry_run: bool = False):
        self.page = page
        self.logger = logger
        self.dry_run = dry_run

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
        for attempt in range(1, 4):
            try:
                if attempt > 1:
                    self.logger.info("Retrying upload attempt %d/3…", attempt)
                    time.sleep(2)  # Brief pause between retries

                self.logger.info("📤 Uploading video: %s (%.2f MB)", video_path.name, video_path.stat().st_size / (1024*1024))
                self.logger.debug("Waiting for upload zone to render...")
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
                    self.logger.warning("Could not find any working file input selector.")
                    continue

                self.logger.debug("Setting video file on input element...")
                upload_input.set_input_files(str(video_path))

                # Wait for upload progress to finish
                self.logger.info("⏳ Waiting for upload to complete (max 120s)...")
                try:
                    # Progressbar appears FIRST then disappears
                    self.page.wait_for_selector("div[role='progressbar']", timeout=15000)
                    self.logger.debug("Progress bar detected, waiting for upload to finish...")
                    self.page.wait_for_selector(
                        "div[role='progressbar']", state="detached", timeout=120000
                    )
                    self.logger.debug("Progress bar disappeared (upload complete)")
                except PlaywrightTimeout:
                    self.logger.debug("No progress bar appeared, checking for media preview...")
                except PlaywrightError:
                    pass  # X sometimes doesn't show progressbar at all

                # Confirm media preview attached
                self.logger.debug("Waiting for media preview to appear...")
                self.page.wait_for_selector(
                    "div[data-testid='media-preview']", timeout=120000
                )
                self.logger.debug("✔ Media preview detected")

                # Wait for Post button to be enabled
                self.logger.debug("Waiting for Post button to be enabled...")
                self.page.wait_for_selector(
                    "button[data-testid='tweetButtonInline']:not([disabled])",
                    timeout=120000,
                )
                self.logger.info("✅ Upload complete - Post button is enabled")
                return True

            except PlaywrightTimeout as exc:
                self.logger.warning("Upload attempt %d timed out: %s", attempt, exc)
                if attempt == 3:
                    self.logger.error("❌ Video upload failed after 3 attempts")
            except PlaywrightError as exc:
                self.logger.warning("Upload attempt %d failed: %s", attempt, exc)
                if attempt == 3:
                    self.logger.error("❌ Video upload failed after 3 attempts")
        return False

    def _submit(self) -> bool:
        """Try multiple strategies to click the Post button."""
        self.logger.info("🚀 Attempting to submit post...")

        # FIX #2: Post button detection with fallback selectors
        post_button_selectors = [
            "button[data-testid='tweetButtonInline']",
            "button[data-testid='tweetButton']",
            "div[data-testid='tweetButtonInline']",
            "div[data-testid='tweetButton']",
        ]

        post_button = None
        for sel in post_button_selectors:
            try:
                self.page.wait_for_selector(sel, timeout=4000)
                post_button = self.page.locator(sel)
                break
            except:
                continue

        if not post_button:
            raise Exception("Post button not found - tried all selectors")

        post_button.click()
        self.logger.info("✅ Clicked Post button")
        time.sleep(3)
        return True

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

        # Dry-run mode: simulate posting without actually clicking Post
        if self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("🔍 DRY-RUN MODE - Post will NOT be submitted")
            self.logger.info("=" * 60)
            self.logger.info("Video: %s (%.2f MB)", video_path.name, video_path.stat().st_size / (1024*1024))
            self.logger.info("Caption: %s", caption)
            self.logger.info("=" * 60)
            self.logger.info("In normal mode, this would:")
            self.logger.info("  1. Open the composer")
            self.logger.info("  2. Type the caption")
            self.logger.info("  3. Upload the video")
            self.logger.info("  4. Click the Post button")
            self.logger.info("=" * 60)
            return "DRY_RUN_NO_URL"

        if not self._open_composer():
            return None
        self.logger.info("Typing caption into composer…")
        try:
            # FIX #1: Composer detection with fallback selectors
            composer_selectors = [
                "div[data-testid='tweetTextarea_0']",
                "div[role='textbox']",
                "textarea",
            ]

            composer_box = None
            for sel in composer_selectors:
                try:
                    self.page.wait_for_selector(sel, timeout=5000)
                    composer_box = self.page.locator(sel)
                    break
                except:
                    continue

            if not composer_box:
                raise Exception("Composer not found - tried all selectors")

            composer_box.wait_for(state="visible", timeout=15000)
            composer_box.click()
            composer_box.fill(caption)
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
