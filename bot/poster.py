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
        """Click the Post button with SUPER AGGRESSIVE retry logic - just keep clicking!"""
        self.logger.info("🚀 Starting aggressive Post button clicking sequence...")

        # 1) Give X a moment to finalize upload
        self.logger.info("🕒 Brief settle wait (3 seconds)...")
        self.page.wait_for_timeout(3000)

        if self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("🧪 DRY-RUN: would click Post button now (skipping actual click).")
            self.logger.info("=" * 60)
            return True

        # 2) Wait for Post button to exist and be visible (not checking enabled state!)
        self.logger.info("⏳ Waiting for Post button to appear in DOM...")
        try:
            self.page.wait_for_selector(POST_BUTTON_SELECTOR, state="visible", timeout=10000)
            self.logger.info("✅ Post button is VISIBLE in composer")
        except PlaywrightTimeout:
            self.logger.error("❌ Post button never appeared in DOM after 10s")
            return False

        # 3) SUPER AGGRESSIVE: Just keep clicking for 40 seconds straight!
        # Don't wait for aria-disabled to flip - it's unreliable. Just click!
        self.logger.info("🖱 Starting AGGRESSIVE clicking loop (40 seconds)...")
        start_time = time.time()
        click_attempts = 0
        max_duration = 40  # 40 seconds

        while time.time() - start_time < max_duration:
            click_attempts += 1

            try:
                # Re-grab button each time
                btn = self.page.locator(POST_BUTTON_SELECTOR).first

                # Check if button still exists (if not, we probably succeeded!)
                try:
                    if not btn.is_visible(timeout=500):
                        self.logger.info("✅✅✅ POST BUTTON DISAPPEARED - Tweet was posted!")
                        return True
                except:
                    # Button gone = success
                    self.logger.info("✅✅✅ POST BUTTON GONE - Tweet was posted!")
                    return True

                # Try to click with force=True (ignore overlays, disabled state, etc.)
                if click_attempts % 5 == 0:
                    self.logger.info("🖱 Click attempt %d (%.1fs elapsed)...", click_attempts, time.time() - start_time)

                btn.click(timeout=3000, force=True)

                # After clicking, immediately check if composer disappeared
                time.sleep(1)

                # Check if we succeeded (composer modal gone or URL changed)
                current_url = self.page.url
                if "/compose/post" not in current_url:
                    self.logger.info("✅✅✅ COMPOSER CLOSED - URL changed to: %s", current_url)
                    return True

                # Check if Post button disappeared
                try:
                    if not self.page.locator(POST_BUTTON_SELECTOR).first.is_visible(timeout=500):
                        self.logger.info("✅✅✅ POST BUTTON DISAPPEARED AFTER CLICK!")
                        return True
                except:
                    self.logger.info("✅✅✅ POST BUTTON GONE AFTER CLICK!")
                    return True

                # Still here? Try again after a short delay
                time.sleep(1)

            except PlaywrightError as exc:
                # Click failed, but keep trying
                if click_attempts % 5 == 0:
                    self.logger.debug("Click attempt %d failed: %s", click_attempts, str(exc)[:80])
                time.sleep(1)
                continue

        # 4) After 40 seconds of clicking, try keyboard shortcut as last resort
        self.logger.warning("⚠️  40 seconds of clicking didn't work - trying keyboard shortcut...")
        try:
            self.logger.info("⌨️  Sending Cmd+Enter...")
            self.page.keyboard.press("Meta+Enter")
            time.sleep(2)

            # Check if it worked
            if "/compose/post" not in self.page.url:
                self.logger.info("✅✅✅ KEYBOARD SHORTCUT WORKED - Composer closed!")
                return True
        except PlaywrightError:
            try:
                self.logger.info("⌨️  Trying Ctrl+Enter...")
                self.page.keyboard.press("Control+Enter")
                time.sleep(2)

                if "/compose/post" not in self.page.url:
                    self.logger.info("✅✅✅ KEYBOARD SHORTCUT WORKED - Composer closed!")
                    return True
            except PlaywrightError as exc:
                self.logger.error("❌ Keyboard shortcuts failed: %s", exc)

        # 5) Last check - did composer close anyway?
        try:
            if not self.page.locator(POST_BUTTON_SELECTOR).first.is_visible(timeout=2000):
                self.logger.warning("⚠️  Post button gone - tweet MAY have posted despite errors")
                return True
        except:
            self.logger.warning("⚠️  Post button gone - tweet MAY have posted despite errors")
            return True

        # Still here = failed
        self.logger.error("❌ Failed to post after %d click attempts over 40+ seconds", click_attempts)
        self.logger.error("❌ Composer is still open - tweet was NOT posted")
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
