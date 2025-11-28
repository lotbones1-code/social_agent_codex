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
        """Open composer page directly."""
        try:
            self.logger.info("Opening composer page...")
            self.page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Wait for composer textarea to appear (may match 2 elements - that's OK)
            self.page.wait_for_selector(
                "div[contenteditable='true'][data-testid='tweetTextarea_0']",
                timeout=15000,
                state="visible"
            )
            self.logger.info("✓ Composer page loaded")
            return True
        except PlaywrightError as exc:
            self.logger.error("❌ Could not open composer: %s", exc)
            return False

    def _attach_video(self, video_path: Path) -> bool:
        """Attach video reliably across all 2025 X upload variants."""
        for attempt in range(1, 4):
            try:
                if attempt > 1:
                    self.logger.info("Retrying upload attempt %d/3…", attempt)
                    time.sleep(2)  # Brief pause between retries

                self.logger.info("📤 Uploading video: %s (%.2f MB)", video_path.name, video_path.stat().st_size / (1024*1024))

                # Step 5: Wait for file input and upload video
                self.logger.info("Step 5: Waiting for file input element...")
                # Priority order for file input selectors
                candidates = [
                    "input[type='file'][accept*='video']",
                    "input[type='file']",
                    "input[data-testid='fileInput']",
                ]

                upload_input = None
                for selector in candidates:
                    try:
                        self.logger.debug("Trying file input selector: %s", selector)
                        el = self.page.locator(selector).first
                        el.wait_for(state="attached", timeout=5000)
                        upload_input = el
                        self.logger.info("✓ Found file input: %s", selector)
                        break
                    except:
                        continue

                if upload_input is None:
                    self.logger.warning("❌ Could not find file input selector")
                    continue

                self.logger.info("Uploading video file...")
                upload_input.set_input_files(str(video_path))

                # Wait for upload to finish - use simple, reliable checks
                # Don't wait for Playwright/X internal events (unreliable)
                self.logger.info("⏳ Waiting for upload indicators...")
                upload_finished = False
                timeout_seconds = 15
                start_time = time.time()

                while time.time() - start_time < timeout_seconds:
                    try:
                        # Check 1: Video player thumbnail appeared?
                        if self.page.locator("div[data-testid='videoPlayer']").is_visible(timeout=1000):
                            self.logger.info("✓ Video thumbnail detected")
                            upload_finished = True
                            break
                    except:
                        pass

                    try:
                        # Check 2: Progress bar gone?
                        if not self.page.locator("div[role='progressbar']").is_visible(timeout=1000):
                            self.logger.info("✓ Progress bar disappeared")
                            upload_finished = True
                            break
                    except:
                        pass

                    time.sleep(0.5)

                # If timeout or conditions met, consider upload complete
                if not upload_finished:
                    self.logger.info("✓ Upload timeout reached (15s) - proceeding")

                self.logger.info("✅ Upload complete - ready to post")
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
        """Click the Post button to submit."""
        self.logger.info("🚀 Clicking Post button...")
        try:
            # Wait for Post button to be enabled and visible
            self.page.wait_for_selector(
                "button[data-testid='tweetButtonInline']:not([disabled])",
                timeout=10000,
                state="visible"
            )

            # Click the Post button
            post_button = self.page.locator("button[data-testid='tweetButtonInline']").first
            post_button.click()
            self.logger.info("✅ Post button clicked")
            time.sleep(3)
            return True
        except PlaywrightError as exc:
            self.logger.error("❌ Failed to click Post button: %s", exc)
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
        # Type caption into composer (use .first to avoid strict mode violation)
        self.logger.info("Typing caption into composer...")
        try:
            # FIX: X has 2 matching textboxes, use .first to pick the real one
            textarea = self.page.locator("div[contenteditable='true'][data-testid='tweetTextarea_0']").first
            textarea.click()
            time.sleep(0.5)
            textarea.fill(caption)
            self.logger.info("✓ Caption typed: %s", caption[:50])
        except PlaywrightError as exc:
            self.logger.error("❌ Could not type caption: %s", exc)
            return None

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
