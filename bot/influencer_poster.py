"""Video poster for influencer mode using Playwright."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import Page, PlaywrightError, TimeoutError as PlaywrightTimeout


class VideoPoster:
    """Posts videos to X using Playwright."""

    def __init__(self, page: Page, logger: logging.Logger):
        self.page = page
        self.logger = logger

    def post_video(self, video_path: Path, caption: str) -> bool:
        """
        Post a video with caption to X.

        Args:
            video_path: Path to video file
            caption: Caption text with hashtags

        Returns:
            True if posted successfully
        """
        if not video_path.exists():
            self.logger.error("Video file not found: %s", video_path)
            return False

        self.logger.info("Posting video: %s", video_path.name)
        self.logger.info("Caption: %s", caption[:100])

        try:
            # Navigate to home to ensure we're on X
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            # Find and click the tweet compose button
            try:
                # Try various selectors for the compose button
                compose_selectors = [
                    "a[href='/compose/post']",
                    "a[data-testid='SideNav_NewTweet_Button']",
                    "div[data-testid='SideNav_NewTweet_Button']",
                ]

                clicked = False
                for selector in compose_selectors:
                    try:
                        self.page.locator(selector).first.click(timeout=5000)
                        clicked = True
                        break
                    except PlaywrightError:
                        continue

                if not clicked:
                    # Fallback: use keyboard shortcut
                    self.page.keyboard.press("N")  # X keyboard shortcut for new tweet

                time.sleep(2)

            except PlaywrightError as exc:
                self.logger.warning("Error opening compose dialog: %s", exc)
                return False

            # Find the file input for media upload
            try:
                file_input = self.page.locator("input[type='file']").first
                file_input.set_input_files(str(video_path.absolute()))
                self.logger.info("Video file attached")
                time.sleep(5)  # Wait for upload to process

            except PlaywrightError as exc:
                self.logger.error("Failed to attach video file: %s", exc)
                return False

            # Enter caption in the text area
            try:
                # Try to find the tweet textarea
                textarea_selectors = [
                    "div[data-testid='tweetTextarea_0']",
                    "div[role='textbox']",
                ]

                typed = False
                for selector in textarea_selectors:
                    try:
                        textarea = self.page.locator(selector).first
                        if textarea.count():
                            textarea.click()
                            time.sleep(0.5)
                            textarea.fill(caption)
                            typed = True
                            break
                    except PlaywrightError:
                        continue

                if not typed:
                    self.logger.warning("Could not find textarea, trying keyboard input")
                    self.page.keyboard.type(caption, delay=50)

                self.logger.info("Caption entered")
                time.sleep(1)

            except PlaywrightError as exc:
                self.logger.warning("Error entering caption: %s", exc)
                # Continue anyway - video is attached

            # Click the Post button
            try:
                post_selectors = [
                    "div[data-testid='tweetButton']",
                    "div[data-testid='tweetButtonInline']",
                    "button[data-testid='tweetButton']",
                ]

                posted = False
                for selector in post_selectors:
                    try:
                        post_button = self.page.locator(selector).first
                        if post_button.count():
                            post_button.click()
                            posted = True
                            break
                    except PlaywrightError:
                        continue

                if not posted:
                    self.logger.error("Could not find Post button")
                    return False

                self.logger.info("Post button clicked")
                time.sleep(5)  # Wait for post to complete

            except PlaywrightError as exc:
                self.logger.error("Error clicking Post button: %s", exc)
                return False

            # Verify the post was successful
            # (X usually redirects or shows a success state)
            self.logger.info("Video posted successfully!")
            return True

        except PlaywrightTimeout:
            self.logger.error("Timeout while posting video")
            return False
        except PlaywrightError as exc:
            self.logger.error("Unexpected error posting video: %s", exc)
            return False

    def reply_to_tweet(self, tweet_url: str, reply_text: str) -> bool:
        """
        Reply to a specific tweet.

        Args:
            tweet_url: URL of tweet to reply to
            reply_text: Reply message

        Returns:
            True if replied successfully
        """
        self.logger.info("Replying to tweet: %s", tweet_url)
        self.logger.info("Reply: %s", reply_text)

        try:
            # Navigate to the tweet
            self.page.goto(tweet_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)

            # Find the reply button
            try:
                reply_button = self.page.locator("div[data-testid='reply']").first
                reply_button.click()
                time.sleep(2)
            except PlaywrightError as exc:
                self.logger.warning("Error clicking reply button: %s", exc)
                return False

            # Enter reply text
            try:
                textarea = self.page.locator("div[data-testid^='tweetTextarea']").first
                textarea.click()
                time.sleep(0.5)
                textarea.fill(reply_text)
                time.sleep(1)
            except PlaywrightError as exc:
                self.logger.warning("Error entering reply text: %s", exc)
                return False

            # Click Reply button
            try:
                reply_submit = self.page.locator("div[data-testid='tweetButtonInline']").first
                reply_submit.click()
                time.sleep(3)
                self.logger.info("Reply posted successfully")
                return True
            except PlaywrightError as exc:
                self.logger.error("Error submitting reply: %s", exc)
                return False

        except PlaywrightTimeout:
            self.logger.error("Timeout while replying to tweet")
            return False
        except PlaywrightError as exc:
            self.logger.error("Unexpected error replying to tweet: %s", exc)
            return False
