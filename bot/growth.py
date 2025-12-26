from __future__ import annotations

import logging
import random
import time
from typing import Iterable

from .poster import VideoPoster
from .scraper import ScrapedPost


class GrowthActions:
    """Perform lightweight engagement to boost account growth."""

    def __init__(self, poster: VideoPoster, logger: logging.Logger):
        self.poster = poster
        self.logger = logger

    def engage(self, posts: Iterable[ScrapedPost], *, max_actions: int) -> None:
        pool = list(posts)
        random.shuffle(pool)
        actions = 0
        for post in pool:
            if actions >= max_actions:
                break
            if self.poster.like(post.url):
                actions += 1
            time.sleep(random.uniform(1.5, 3.0))
            if actions >= max_actions:
                break
            if self.poster.follow_author(post.url):
                actions += 1
            time.sleep(random.uniform(1.5, 3.0))
        self.logger.info("Completed %d growth actions.", actions)


__all__ = ["GrowthActions"]
