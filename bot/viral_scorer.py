from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List

from .scraper import ScrapedPost


@dataclass
class ScoredPost:
    post: ScrapedPost
    score: float


class ViralScorer:
    """Lightweight heuristic scorer to prioritize high-signal videos."""

    def __init__(self, logger: logging.Logger, *, min_score: float = 0.25):
        self.logger = logger
        self.min_score = min_score

    @staticmethod
    def _density(text: str) -> float:
        words = text.split()
        if not words:
            return 0.0
        hashtags = [w for w in words if w.startswith("#")]
        return min(len(hashtags) / len(words), 0.6)

    def _score_post(self, post: ScrapedPost) -> float:
        base = 0.2 if post.video_url else 0.0
        text_len = len(post.text.strip())
        if text_len > 140:
            base += 0.35
        elif text_len > 80:
            base += 0.25
        elif text_len > 30:
            base += 0.15

        base += self._density(post.text) * 0.3

        # Prefer posts that look like highlights or clips
        keywords = ["wow", "insane", "breakdown", "clip", "epic", "must see", "viral"]
        for word in keywords:
            if word in post.text.lower():
                base += 0.05
                break

        return min(base, 1.0)

    def rank(self, posts: Iterable[ScrapedPost]) -> List[ScoredPost]:
        scored: List[ScoredPost] = []
        for post in posts:
            score = self._score_post(post)
            if score >= self.min_score:
                scored.append(ScoredPost(post=post, score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        self.logger.info("Ranked %d posts (>= %.2f) for virality", len(scored), self.min_score)
        return scored


__all__ = ["ViralScorer", "ScoredPost"]
