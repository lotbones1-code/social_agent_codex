"""Posting helpers for X using Playwright."""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import Error, Page

from .scraper import VideoItem


class Poster:
    def __init__(self, page: Page, logger: logging.Logger, attach_rate: float) -> None:
        self.page = page
        self.logger = logger
        self.attach_rate = attach_rate

    def _open_composer(self) -> bool:
        try:
            self.page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=45000)
            self.page.wait_for_selector("div[data-testid^='tweetTextarea']", timeout=15000)
            return True
        except Error as exc:
            self.logger.error("Failed to open composer: %s", exc)
            return False

    def _attach_video(self, file_path: Path) -> bool:
        try:
            upload = self.page.locator("input[type='file'][data-testid='fileInput']").first
            upload.set_input_files(str(file_path))
            self.page.wait_for_timeout(3000)
            return True
        except Error as exc:
            self.logger.warning("Unable to attach media: %s", exc)
            return False

    def publish(self, caption: str, media: Optional[Path], allow_media: bool = True) -> bool:
        if not self._open_composer():
            return False
        try:
            composer = self.page.locator("div[data-testid^='tweetTextarea']").first
            composer.click()
            self.page.keyboard.insert_text(caption)
            attached = False
            if allow_media and media and random.random() <= self.attach_rate:
                attached = self._attach_video(media)
            self.page.locator("div[data-testid='tweetButtonInline']").click()
            self.page.wait_for_timeout(3000)
            self.logger.info("Posted update%s", " with media" if attached else "")
            return True
        except Error as exc:
            self.logger.error("Failed to publish post: %s", exc)
            return False


class GrowthActions:
    def __init__(self, page: Page, logger: logging.Logger, like_limit: int, follow_limit: int):
        self.page = page
        self.logger = logger
        self.like_limit = like_limit
        self.follow_limit = follow_limit

    def like_timeline(self) -> int:
        liked = 0
        try:
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45000)
            cards = self.page.locator("div[data-testid='like']")
            count = min(cards.count(), self.like_limit)
            for idx in range(count):
                try:
                    cards.nth(idx).click()
                    liked += 1
                    self.page.wait_for_timeout(500)
                except Error:
                    continue
        except Error as exc:
            self.logger.warning("Unable to like timeline: %s", exc)
        if liked:
            self.logger.info("Liked %s posts", liked)
        return liked

    def follow_suggestions(self) -> int:
        followed = 0
        try:
            self.page.goto("https://x.com/i/connect_people", wait_until="domcontentloaded", timeout=45000)
            buttons = self.page.locator("div[data-testid='placementTracking'] span:has-text('Follow')")
            count = min(buttons.count(), self.follow_limit)
            for idx in range(count):
                try:
                    buttons.nth(idx).click()
                    followed += 1
                    self.page.wait_for_timeout(500)
                except Error:
                    continue
        except Error as exc:
            self.logger.warning("Unable to follow suggestions: %s", exc)
        if followed:
            self.logger.info("Followed %s suggested accounts", followed)
        return followed

    def run_cycle(self) -> None:
        liked = self.like_timeline()
        followed = self.follow_suggestions()
        if liked or followed:
            self.page.wait_for_timeout(1500)
