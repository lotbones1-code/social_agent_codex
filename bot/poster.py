from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, Page, Locator


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

    def _get_post_button(self) -> Locator:
        """Get the Post button locator."""
        btn = self.page.locator(POST_BUTTON_SELECTOR).first
        return btn

    def _is_post_button_enabled(self, btn: Locator) -> bool:
        """Check if the Post button is enabled and clickable."""
        try:
            if not btn.is_visible(timeout=2000):
                return False
            # aria-disabled is the most important
            aria_disabled = btn.get_attribute("aria-disabled") or ""
            if aria_disabled.lower() == "true":
                return False
            # X sometimes uses disabled attribute too
            disabled_attr = btn.get_attribute("disabled")
            if disabled_attr is not None:
                return False
            return True
        except PlaywrightError:
            return False

    def _submit(self) -> bool:
        """Click the Post button with robust detection and verification."""
        self.logger.info("🚀 Attempting to click Post button...")

        # 1) Add settle wait for X to finalize upload
        self.logger.info("🕒 Giving X a moment to finalize upload before posting...")
        self.page.wait_for_timeout(3000)  # 3 seconds

        if self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("🧪 DRY-RUN: would click Post button now (skipping actual click).")
            self.logger.info("=" * 60)
            return True

        # 2) Wait for Post button to become enabled (up to 10 seconds)
        self.logger.info("Waiting for Post button to become enabled...")
        btn_enabled = False
        for i in range(10):
            btn = self._get_post_button()
            if self._is_post_button_enabled(btn):
                self.logger.info("✓ Post button is visible and enabled (attempt %d).", i + 1)
                btn_enabled = True
                break
            self.logger.info("Post button still disabled (attempt %d).", i + 1)
            self.page.wait_for_timeout(1000)

        if not btn_enabled:
            self.logger.error("❌ Post button never became enabled; aborting post attempt.")
            return False

        # 3) Click with force=True and retry logic
        btn = self._get_post_button()
        self.logger.info("🖱 Attempting to click Post button...")
        click_ok = False
        for attempt in range(3):
            try:
                btn = self._get_post_button()
                if not self._is_post_button_enabled(btn):
                    self.logger.info("Post button not enabled before click attempt %d; waiting 1s", attempt + 1)
                    self.page.wait_for_timeout(1000)
                    continue
                btn.click(timeout=10000, force=True)
                self.logger.info("✓ Post button click sent (attempt %d).", attempt + 1)
                click_ok = True
                break
            except PlaywrightError as exc:
                self.logger.warning("Click attempt %d on Post button failed: %s", attempt + 1, exc)
                self.page.wait_for_timeout(1500)

        if not click_ok:
            self.logger.error("❌ Failed to click enabled Post button after retries – will try keyboard shortcut.")

        # 4) Keyboard shortcut fallback (Cmd/Ctrl + Enter)
        if not click_ok:
            try:
                self.logger.info("⌨️ Sending Cmd+Enter shortcut as fallback...")
                self.page.keyboard.press("Meta+Enter")
                click_ok = True  # Assume it worked
            except PlaywrightError:
                self.logger.warning("Cmd+Enter failed, trying Ctrl+Enter...")
                try:
                    self.page.keyboard.press("Control+Enter")
                    click_ok = True
                except PlaywrightError as exc:
                    self.logger.error("Keyboard fallback failed: %s", exc)
                    return False

        # 5) Detect that the tweet was actually posted
        self.logger.info("⏳ Waiting for composer to close or Post button to disappear...")
        try:
            self.page.wait_for_timeout(2000)
            self.page.wait_for_selector(POST_BUTTON_SELECTOR, state="detached", timeout=15000)
            self.logger.info("✅ Post appears to have been submitted (Post button gone).")
            return True
        except PlaywrightError:
            self.logger.warning("Composer did not fully close; tweet may or may not have posted.")
            return True  # still treat as best-effort success

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
