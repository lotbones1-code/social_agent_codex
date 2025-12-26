from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError, Page


@dataclass
class Mention:
    author: str
    url: str


class AutoReplyEngine:
    """Lightweight responder that replies to recent mentions."""

    def __init__(self, page: Page, logger: logging.Logger, template: str) -> None:
        self.page = page
        self.logger = logger
        self.template = template

    def _fetch_mentions(self, limit: int) -> list[Mention]:
        try:
            self.page.goto("https://x.com/notifications/mentions", wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError as exc:
            self.logger.warning("Could not load mentions timeline: %s", exc)
            return []

        mentions: list[Mention] = []
        cards = self.page.locator("article div[data-testid='tweet']").all()
        for card in cards:
            if len(mentions) >= limit:
                break
            try:
                anchor = card.locator("a[href*='/status/']").first
                href = anchor.get_attribute("href") or ""
                username_node = card.locator("div[dir='ltr'] span").first
                author = username_node.inner_text().strip() if username_node else ""
                if "/status/" in href:
                    mentions.append(Mention(author=author or "friend", url=f"https://x.com{href}"))
            except PlaywrightError:
                continue
        return mentions

    def _reply(self, mention: Mention) -> bool:
        try:
            self.page.goto(mention.url, wait_until="domcontentloaded", timeout=60000)
            reply_btn = self.page.locator("div[data-testid='reply']").first
            reply_btn.click()
            composer = self.page.locator("div[data-testid='tweetTextarea_0']").first
            composer.fill(self.template.format(author=mention.author))
            send_btn = self.page.locator("div[data-testid='tweetButtonInline']").first
            send_btn.click()
            time.sleep(2)
            return True
        except PlaywrightError as exc:
            self.logger.debug("Failed to reply to %s: %s", mention.url, exc)
            return False

    def reply_to_latest(self, *, max_replies: int) -> None:
        queue = self._fetch_mentions(max_replies * 2)
        random.shuffle(queue)
        replies = 0
        for mention in queue:
            if replies >= max_replies:
                break
            if self._reply(mention):
                replies += 1
                self.logger.info("Replied to %s", mention.url)
                time.sleep(random.uniform(1.5, 3.5))
        if replies:
            self.logger.info("Auto-reply complete: %d message(s) sent.", replies)


__all__ = ["AutoReplyEngine", "Mention"]
