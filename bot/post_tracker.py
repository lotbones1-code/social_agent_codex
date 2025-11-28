"""Track posted content to avoid duplicates and enforce posting limits."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional


@dataclass
class PostRecord:
    """Record of a posted tweet."""
    tweet_id: Optional[str]
    tweet_url: Optional[str]
    video_url: str
    video_url_hash: str
    caption: str
    timestamp: str  # ISO format
    topic: str


class PostTracker:
    """Track posted content to avoid duplicates and enforce posting limits."""

    def __init__(self, log_path: Path, duplicate_check_hours: int, max_posts_24h: int, logger: logging.Logger):
        self.log_path = log_path
        self.duplicate_check_hours = duplicate_check_hours
        self.max_posts_24h = max_posts_24h
        self.logger = logger
        self.records: List[PostRecord] = []
        self._load()

    def _load(self) -> None:
        """Load post history from disk."""
        if not self.log_path.exists():
            self.logger.debug("No existing post log found at %s", self.log_path)
            return

        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.records = [PostRecord(**r) for r in data]
                self.logger.debug("Loaded %d post records from history", len(self.records))
        except Exception as exc:
            self.logger.warning("Could not load post history from %s: %s", self.log_path, exc)

    def _save(self) -> None:
        """Save post history to disk."""
        try:
            with open(self.log_path, "w", encoding="utf-8") as f:
                data = [asdict(r) for r in self.records]
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            self.logger.warning("Could not save post history to %s: %s", self.log_path, exc)

    @staticmethod
    def _hash_url(url: str) -> str:
        """Create a hash of the video URL for duplicate detection."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def is_duplicate(self, video_url: str) -> bool:
        """Check if this video URL was posted recently (within duplicate_check_hours)."""
        cutoff = datetime.now() - timedelta(hours=self.duplicate_check_hours)
        url_hash = self._hash_url(video_url)

        for record in self.records:
            try:
                posted_at = datetime.fromisoformat(record.timestamp)
                if posted_at >= cutoff and record.video_url_hash == url_hash:
                    self.logger.info(
                        "⚠️  Duplicate detected: video %s was posted at %s (within %dh window)",
                        video_url,
                        record.timestamp,
                        self.duplicate_check_hours,
                    )
                    return True
            except ValueError:
                continue

        return False

    def can_post_now(self) -> bool:
        """Check if posting is allowed based on 24h rate limit."""
        cutoff = datetime.now() - timedelta(hours=24)
        recent_posts = 0

        for record in self.records:
            try:
                posted_at = datetime.fromisoformat(record.timestamp)
                if posted_at >= cutoff:
                    recent_posts += 1
            except ValueError:
                continue

        if recent_posts >= self.max_posts_24h:
            self.logger.warning(
                "⚠️  24-hour posting limit reached (%d/%d posts). Cannot post now.",
                recent_posts,
                self.max_posts_24h,
            )
            return False

        self.logger.debug("✔ Posting allowed: %d/%d posts in last 24h", recent_posts, self.max_posts_24h)
        return True

    def record_post(
        self,
        video_url: str,
        caption: str,
        topic: str,
        tweet_url: Optional[str] = None,
    ) -> None:
        """Record a successful post."""
        tweet_id = None
        if tweet_url and "/status/" in tweet_url:
            tweet_id = tweet_url.split("/status/")[-1].split("?")[0]

        record = PostRecord(
            tweet_id=tweet_id,
            tweet_url=tweet_url,
            video_url=video_url,
            video_url_hash=self._hash_url(video_url),
            caption=caption,
            timestamp=datetime.now().isoformat(),
            topic=topic,
        )

        self.records.append(record)
        self._save()

        self.logger.info(
            "📝 Recorded post: tweet_id=%s, topic=%s, video=%s",
            tweet_id or "unknown",
            topic,
            video_url[:60] + "..." if len(video_url) > 60 else video_url,
        )

    def cleanup_old_records(self, keep_days: int = 30) -> None:
        """Remove post records older than keep_days to prevent unbounded growth."""
        if not self.records:
            return

        cutoff = datetime.now() - timedelta(days=keep_days)
        original_count = len(self.records)

        self.records = [
            r for r in self.records
            if datetime.fromisoformat(r.timestamp) >= cutoff
        ]

        if len(self.records) < original_count:
            self.logger.info(
                "Cleaned up %d old post records (kept last %d days)",
                original_count - len(self.records),
                keep_days,
            )
            self._save()


__all__ = ["PostTracker", "PostRecord"]
