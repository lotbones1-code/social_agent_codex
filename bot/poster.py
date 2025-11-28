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
        Open composer using multiple methods (robust fallback).
        Returns the page with composer, or None if failed.
        """
        context = self.page.context

        # METHOD 1: Click compose button on home page (MOST RELIABLE)
        try:
            self.logger.info("Opening composer via home page button...")

            # First go to home to ensure we're logged in
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            # Find and click the compose/post button
            compose_selectors = [
                "a[data-testid='SideNav_NewTweet_Button']",
                "a[href='/compose/tweet']",
                "div[data-testid='SideNav_NewTweet_Button']",
            ]

            compose_clicked = False
            for selector in compose_selectors:
                try:
                    btn = self.page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        btn.click()
                        compose_clicked = True
                        self.logger.info(f"Clicked compose button: {selector}")
                        break
                except:
                    continue

            if not compose_clicked:
                self.logger.debug("Could not find compose button, trying modal...")

            # Wait for compose modal/dialog to appear
            time.sleep(2)

            # Try to find the textarea in modal
            textarea_selectors = [
                "div[data-testid='tweetTextarea_0'] div[contenteditable='true']",
                "div[contenteditable='true'][data-text='What is happening?!']",
                "div[role='textbox'][contenteditable='true']",
            ]

            textarea_found = False
            for selector in textarea_selectors:
                try:
                    textarea = self.page.locator(selector).first
                    if textarea.is_visible(timeout=5000):
                        self.logger.info("✅ Composer modal ready")
                        textarea_found = True
                        return self.page  # Use main page, not new page
                except:
                    continue

            if textarea_found:
                return self.page

        except Exception as exc:
            self.logger.debug(f"Method 1 (button click) failed: {exc}")

        # METHOD 2: Open composer in new tab via direct URL
        try:
            self.logger.info("Opening composer in new tab...")
            composer_page = context.new_page()
            composer_page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=40000)
            time.sleep(3)

            # Wait for textarea
            composer_page.wait_for_selector(
                "div[data-testid='tweetTextarea_0'] div[contenteditable='true']",
                timeout=15000
            )
            self.logger.info("✅ Composer page ready (new tab)")
            return composer_page

        except Exception as exc:
            self.logger.debug(f"Method 2 (new tab) failed: {exc}")
            try:
                composer_page.close()
            except:
                pass

        # METHOD 3: Navigate main page to compose URL
        try:
            self.logger.info("Navigating to compose URL...")
            self.page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=40000)
            time.sleep(3)

            self.page.wait_for_selector(
                "div[data-testid='tweetTextarea_0'] div[contenteditable='true']",
                timeout=15000
            )
            self.logger.info("✅ Composer ready")
            return self.page

        except Exception as exc:
            self.logger.debug(f"Method 3 (navigate) failed: {exc}")

        self.logger.warning("❌ All composer opening methods failed")
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

        # Open composer (might be modal or new page)
        composer_page = self._open_composer()
        if not composer_page:
            return False

        # Check if composer is the main page or a new page
        is_main_page = (composer_page == self.page)

        try:
            # Type caption
            self.logger.info("Typing caption...")

            # Try multiple textarea selectors
            textarea_selectors = [
                "div[data-testid='tweetTextarea_0'] div[contenteditable='true']",
                "div[contenteditable='true'][role='textbox']",
            ]

            composer = None
            for selector in textarea_selectors:
                try:
                    elem = composer_page.locator(selector).first
                    if elem.is_visible(timeout=3000):
                        composer = elem
                        break
                except:
                    continue

            if not composer:
                self.logger.warning("Could not find composer textarea")
                if not is_main_page:
                    composer_page.close()
                return False

            composer.click()
            time.sleep(0.5)
            composer.type(caption, delay=50)
            time.sleep(0.5)
            self.logger.info("✅ Caption typed successfully")

            # Upload video
            self.logger.info("Uploading video...")
            upload_input = composer_page.locator("input[data-testid='fileInput']").first
            upload_input.set_input_files(str(video_path))

            # Wait for upload with progress tracking
            time.sleep(3)
            try:
                composer_page.wait_for_selector("div[data-testid='media-preview']", timeout=90000)
                self.logger.info("✅ Video uploaded successfully")
                time.sleep(3)  # Let it process
            except PlaywrightTimeout:
                self.logger.warning("Video upload timed out")
                if not is_main_page:
                    composer_page.close()
                return False

            # Submit the post
            self.logger.info("Submitting post...")

            # Try multiple post button selectors
            post_button_selectors = [
                "div[data-testid='tweetButton']",
                "div[data-testid='tweetButtonInline']",
                "button[data-testid='tweetButton']",
            ]

            post_button = None
            for selector in post_button_selectors:
                try:
                    btn = composer_page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        post_button = btn
                        break
                except:
                    continue

            if not post_button:
                self.logger.warning("Could not find post button")
                if not is_main_page:
                    composer_page.close()
                return False

            post_button.click()
            time.sleep(6)  # Wait for post to go through

            self.logger.info("✅ Post published successfully!")

            # Close composer tab if it's not main page
            if not is_main_page:
                try:
                    composer_page.close()
                except:
                    pass

            return True

        except Exception as exc:
            self.logger.warning(f"Failed to post video: {exc}")
            if not is_main_page:
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
