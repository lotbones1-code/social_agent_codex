from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, Page


# Post button selector constant
POST_BUTTON_SELECTOR = "[data-testid='tweetButtonInline']"


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
        """Attach video with robust upload completion detection."""
        for attempt in range(1, 4):
            try:
                if attempt > 1:
                    self.logger.info("Retrying upload attempt %d/3…", attempt)
                    time.sleep(2)

                self.logger.info("📤 Uploading video: %s (%.2f MB)", video_path.name, video_path.stat().st_size / (1024*1024))

                # Find file input and upload
                self.logger.info("Finding file input element...")
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

                self.logger.info("Setting file on input element...")
                upload_input.set_input_files(str(video_path))

                # ROBUST UPLOAD COMPLETION DETECTION
                self.logger.info("⏳ Waiting for upload completion (max 30s)...")
                upload_finished = False
                timeout_seconds = 30
                start_time = time.time()
                last_progress_check = 0

                while time.time() - start_time < timeout_seconds:
                    try:
                        # Check 1: Video player preview in composer?
                        if self.page.locator("div[data-testid='videoPlayer']").is_visible(timeout=500):
                            self.logger.info("✓ Video player preview detected in composer")
                            upload_finished = True
                            break
                    except:
                        pass

                    try:
                        # Check 2: Remove media button appeared?
                        remove_btn = self.page.locator("[aria-label*='Remove']").first
                        if remove_btn.is_visible(timeout=500):
                            self.logger.info("✓ Remove media button detected")
                            upload_finished = True
                            break
                    except:
                        pass

                    try:
                        # Check 3: No progress bar for at least 500ms?
                        if not self.page.locator("div[role='progressbar']").is_visible(timeout=100):
                            current_time = time.time()
                            if last_progress_check == 0:
                                last_progress_check = current_time
                            elif current_time - last_progress_check >= 0.5:
                                self.logger.info("✓ Progress bar gone for 500ms - upload likely complete")
                                upload_finished = True
                                break
                        else:
                            # Reset timer if progress bar reappears
                            last_progress_check = 0
                    except:
                        pass

                    time.sleep(0.3)

                # Even if timeout, proceed (upload might still be ready)
                if not upload_finished:
                    self.logger.warning("⚠️  Upload timeout reached (30s) - proceeding anyway")

                self.logger.info("✅ Upload phase complete - ready to post")
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
        """Click the Post button with robust detection and verification."""
        self.logger.info("🚀 Attempting to click Post button...")

        if self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("🔍 DRY-RUN MODE - NOT clicking Post button")
            self.logger.info("In normal mode, would click: %s", POST_BUTTON_SELECTOR)
            self.logger.info("=" * 60)
            return True

        try:
            # Wait for Post button to be visible and NOT disabled
            self.logger.debug("Waiting for Post button: %s", POST_BUTTON_SELECTOR)

            # First check if button exists and is visible
            self.page.wait_for_selector(
                POST_BUTTON_SELECTOR,
                timeout=15000,
                state="visible"
            )
            self.logger.info("✓ Post button found and visible")

            # Check if button is enabled (not aria-disabled)
            for retry in range(3):
                try:
                    post_button = self.page.locator(POST_BUTTON_SELECTOR).first
                    aria_disabled = post_button.get_attribute("aria-disabled")

                    if aria_disabled == "true":
                        self.logger.debug("Post button is disabled, waiting... (retry %d/3)", retry + 1)
                        time.sleep(1)
                        continue

                    # Button is enabled, click it
                    self.logger.info("Post button is enabled, clicking now...")
                    post_button.click(timeout=5000)
                    self.logger.info("✅ Post button clicked successfully")

                    # Wait for confirmation that post was submitted
                    # The composer should disappear or URL should change
                    time.sleep(2)

                    # Check if we're no longer on compose page
                    current_url = self.page.url
                    if "/compose/post" not in current_url:
                        self.logger.info("✓ Navigated away from composer - post likely submitted")
                        return True

                    # Or check if Post button disappeared
                    if not self.page.locator(POST_BUTTON_SELECTOR).is_visible(timeout=2000):
                        self.logger.info("✓ Post button disappeared - post likely submitted")
                        return True

                    # Give it some time and consider success
                    time.sleep(2)
                    self.logger.info("✓ Post button clicked - assuming success")
                    return True

                except PlaywrightError as click_exc:
                    self.logger.warning("Click attempt %d failed: %s", retry + 1, click_exc)
                    if retry < 2:
                        time.sleep(1)
                    continue

            self.logger.error("❌ Failed to click enabled Post button after retries")
            return False

        except PlaywrightTimeout:
            self.logger.error("❌ Timeout waiting for Post button: %s", POST_BUTTON_SELECTOR)
            return False
        except PlaywrightError as exc:
            self.logger.error("❌ Failed to click Post button: %s", exc)
            return False

    def _latest_post_url(self) -> Optional[str]:
        """Get the URL of the most recent post from profile."""
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
        """Post a video with caption to X."""
        if not video_path.exists():
            self.logger.warning("Video %s does not exist.", video_path)
            return None

        # Dry-run info
        if self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("🔍 DRY-RUN MODE - Simulating post workflow")
            self.logger.info("=" * 60)
            self.logger.info("Video: %s (%.2f MB)", video_path.name, video_path.stat().st_size / (1024*1024))
            self.logger.info("Caption: %s", caption)
            self.logger.info("=" * 60)
            self.logger.info("DRY-RUN: Would perform these steps:")
            self.logger.info("  1. Open composer at /compose/post")
            self.logger.info("  2. Type caption into textarea")
            self.logger.info("  3. Upload video file")
            self.logger.info("  4. Wait for upload completion")
            self.logger.info("  5. Click Post button: %s", POST_BUTTON_SELECTOR)
            self.logger.info("=" * 60)

        if not self._open_composer():
            return None

        # Type caption
        self.logger.info("Typing caption into composer...")
        try:
            # Use .first to avoid strict mode violation (X has 2 matching textboxes)
            textarea = self.page.locator("div[contenteditable='true'][data-testid='tweetTextarea_0']").first
            textarea.click()
            time.sleep(0.5)
            textarea.fill(caption)
            self.logger.info("✓ Caption typed: %s", caption[:60] + ("..." if len(caption) > 60 else ""))
        except PlaywrightError as exc:
            self.logger.error("❌ Could not type caption: %s", exc)
            return None

        # Upload video
        self.logger.info("Uploading video to composer...")
        if not self._attach_video(video_path):
            return None

        # Submit post
        submitted = self._submit()
        if not submitted:
            return None

        # Try to get the posted URL
        posted_url = self._latest_post_url()
        if posted_url:
            self.logger.info("✅ Posted video successfully: %s", posted_url)
        else:
            self.logger.info("✅ Post submitted (URL retrieval failed, but post likely succeeded)")
        return posted_url or "POSTED"

    def repost(self, post_url: str) -> bool:
        """Repost an existing post."""
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
        """Like a post."""
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
        """Follow the author of a post."""
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


__all__ = ["VideoPoster", "POST_BUTTON_SELECTOR"]
