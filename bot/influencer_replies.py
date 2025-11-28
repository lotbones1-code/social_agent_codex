from __future__ import annotations

import logging
import random
import time
from typing import Iterable, List

from playwright.sync_api import Error as PlaywrightError, Page

from .influencer_captioner import InfluencerCaptioner, InfluencerContext


class InfluencerReplyAgent:
    """Optional lightweight replies to large accounts to look human."""

    def __init__(
        self,
        page: Page,
        logger: logging.Logger,
        captioner: InfluencerCaptioner,
        *,
        delay_min: int,
        delay_max: int,
    ) -> None:
        self.page = page
        self.logger = logger
        self.captioner = captioner
        self.delay_min = delay_min
        self.delay_max = delay_max

    def _recent_posts(self, handle: str, limit: int) -> List[tuple[str, str]]:
        url = f"https://x.com/{handle}"
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError as exc:
            self.logger.warning("Could not load timeline for @%s: %s", handle, exc)
            return []

        articles = self.page.locator("article[data-testid='tweet']").all()
        results: List[tuple[str, str]] = []
        for article in articles:
            try:
                text = article.locator("div[data-testid='tweetText']").inner_text(timeout=3500)
                anchor = article.locator("a[href*='/status/']").first
                href = anchor.get_attribute("href") or ""
                if "/status/" in href:
                    results.append((f"https://x.com{href}", text))
                if len(results) >= limit:
                    break
            except PlaywrightError:
                continue
        return results

    def _reply(self, url: str, reply: str) -> bool:
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            btn = self.page.locator("div[data-testid='reply']").first
            btn.click()
            composer = self.page.locator("div[data-testid^='tweetTextarea_']").first
            composer.fill(reply)
            send = self.page.locator("div[data-testid='tweetButtonInline']").first
            send.click()
            time.sleep(2)
            return True
        except PlaywrightError as exc:
            self.logger.debug("Failed to reply to %s: %s", url, exc)
            return False

    def run(self, targets: Iterable[str], *, replies_per_target: int) -> None:
        handles = [h for h in targets if h]
        if not handles:
            return
        for handle in handles:
            queue = self._recent_posts(handle, replies_per_target * 2)
            random.shuffle(queue)
            sent = 0
            for url, text in queue:
                if sent >= replies_per_target:
                    break
                reply = self.captioner.generate(
                    InfluencerContext(author=f"@{handle}", topic="reply", text=text, url=url)
                )
                if self._reply(url, reply):
                    sent += 1
                    self.logger.info("Influencer reply sent to %s", url)
                    time.sleep(random.uniform(self.delay_min, self.delay_max))


__all__ = ["InfluencerReplyAgent"]
