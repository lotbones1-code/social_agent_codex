"""Track daily posts to respect rate limits."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List


class PostTracker:
    """Track posts to enforce daily limits."""

    def __init__(self, tracking_file: str, logger: logging.Logger):
        self.tracking_file = Path(tracking_file)
        self.logger = logger
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Ensure tracking file and directory exist."""
        self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.tracking_file.exists():
            self.tracking_file.write_text(json.dumps({"posts": []}))

    def _load_posts(self) -> List[str]:
        """Load post timestamps from file."""
        try:
            data = json.loads(self.tracking_file.read_text())
            return data.get("posts", [])
        except Exception as exc:
            self.logger.warning(f"Failed to load post history: {exc}")
            return []

    def _save_posts(self, posts: List[str]) -> None:
        """Save post timestamps to file."""
        try:
            self.tracking_file.write_text(json.dumps({"posts": posts}, indent=2))
        except Exception as exc:
            self.logger.warning(f"Failed to save post history: {exc}")

    def _clean_old_posts(self, posts: List[str]) -> List[str]:
        """Remove posts older than 24 hours."""
        cutoff = datetime.now() - timedelta(hours=24)
        recent_posts = []
        for post_time_str in posts:
            try:
                post_time = datetime.fromisoformat(post_time_str)
                if post_time > cutoff:
                    recent_posts.append(post_time_str)
            except:
                continue
        return recent_posts

    def get_posts_today(self) -> int:
        """Get number of posts in the last 24 hours."""
        posts = self._load_posts()
        recent = self._clean_old_posts(posts)
        return len(recent)

    def can_post(self, max_daily: int) -> bool:
        """Check if we can post (haven't hit daily limit)."""
        posts_today = self.get_posts_today()
        can_post = posts_today < max_daily
        self.logger.info(f"Posts in last 24h: {posts_today}/{max_daily} - Can post: {can_post}")
        return can_post

    def record_post(self) -> None:
        """Record a new post with current timestamp."""
        posts = self._load_posts()
        posts = self._clean_old_posts(posts)
        posts.append(datetime.now().isoformat())
        self._save_posts(posts)
        self.logger.info(f"Recorded new post. Total in 24h: {len(posts)}")


__all__ = ["PostTracker"]
