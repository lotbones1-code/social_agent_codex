from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

from .downloader import VideoDownloader
from .influencer_scraper import InfluencerPost


class InfluencerMediaStore:
    """Manage influencer media lifecycle to avoid reposting duplicates."""

    def __init__(self, inbox: Path, posted: Path, logger: logging.Logger):
        self.inbox = inbox
        self.posted = posted
        self.logger = logger

    def _filename(self, post: InfluencerPost) -> str:
        safe_id = post.tweet_id or post.url.rsplit("/", 1)[-1]
        return f"{safe_id}.mp4"

    def is_posted(self, post: InfluencerPost) -> bool:
        filename = self._filename(post)
        return (self.posted / filename).exists()

    def staged_path(self, post: InfluencerPost) -> Path:
        return self.inbox / self._filename(post)

    def mark_posted(self, staged: Path) -> None:
        target = self.posted / staged.name
        try:
            staged.rename(target)
            self.logger.debug("Moved %s → %s", staged, target)
        except OSError as exc:
            self.logger.warning("Could not move %s to posted: %s", staged, exc)


class InfluencerDownloader:
    """Wrapper around VideoDownloader that enforces inbox/posted folders."""

    def __init__(
        self,
        download_dir: Path,
        posted_dir: Path,
        logger: logging.Logger,
        *,
        user_agent: str | None = None,
    ):
        self.logger = logger
        self.store = InfluencerMediaStore(download_dir, posted_dir, logger)
        self.downloader = VideoDownloader(download_dir, logger, user_agent=user_agent)

    def set_cookies(self, cookies: Iterable[dict]) -> None:
        self.downloader.set_cookies(cookies)

    def download(self, post: InfluencerPost) -> Optional[Path]:
        if self.store.is_posted(post):
            self.logger.info("Skipping %s (already posted)", post.url)
            return None
        target = self.store.staged_path(post)
        if target.exists():
            self.logger.info("Reusing existing download for %s", post.url)
            return target
        if not post.video_url:
            self.logger.debug("No video URL found for %s", post.url)
            return None
        saved = self.downloader.download(post.video_url, filename_hint=target.stem)
        return saved

    def mark_posted(self, staged: Path) -> None:
        self.store.mark_posted(staged)


__all__ = ["InfluencerDownloader", "InfluencerMediaStore"]
