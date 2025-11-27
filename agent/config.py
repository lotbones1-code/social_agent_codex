"""Configuration helpers for the social agent."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from dotenv import load_dotenv


@dataclass(slots=True)
class BotSettings:
    """Runtime configuration for the bot."""

    topics: List[str]
    video_sources: List[str]
    download_dir: Path
    headless: bool
    debug: bool
    user_data_dir: Path
    captions: List[str]
    hashtags: List[str]
    max_videos: int
    like_limit: int
    follow_limit: int
    attach_rate: float
    wait_after_actions: int

    @classmethod
    def from_env(cls) -> "BotSettings":
        load_dotenv()

        def _bool(name: str, default: bool) -> bool:
            raw = (os.getenv(name) or "").strip().lower()
            if not raw:
                return default
            return raw in {"1", "true", "yes", "y", "on"}

        def _list(name: str, default: list[str]) -> list[str]:
            raw = os.getenv(name, "")
            if not raw:
                return default
            items: list[str] = []
            for part in raw.replace("||", "|").split("|"):
                for piece in part.split(","):
                    clean = piece.strip()
                    if clean:
                        items.append(clean)
            return items or default

        def _float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None:
                return default
            try:
                return float(raw)
            except ValueError:
                return default

        topics = _list("TOPICS", ["ai automation", "growth hacking"])
        video_sources = _list(
            "VIDEO_SOURCES",
            [
                "https://sample-videos.com/video321/mp4/720/big_buck_bunny_720p_1mb.mp4",
            ],
        )
        captions = _list(
            "CAPTION_TEMPLATES",
            [
                "{hook}\n\n{hashtags}",
                "{hook} — grabbed from {source}. {hashtags}",
            ],
        )
        hashtags = [f"#{tag.replace('#', '')}" for tag in _list("HASHTAGS", ["automation", "buildinpublic"])]
        download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads")).expanduser()
        user_data_dir = Path(os.getenv("USER_DATA_DIR", ".auth/x_profile")).expanduser()
        headless = _bool("HEADLESS", True)
        debug = _bool("DEBUG", False)
        max_videos = int(os.getenv("MAX_VIDEOS", "3"))
        like_limit = int(os.getenv("LIKE_LIMIT", "5"))
        follow_limit = int(os.getenv("FOLLOW_LIMIT", "2"))
        attach_rate = _float("MEDIA_ATTACH_RATE", 0.5)
        wait_after_actions = int(os.getenv("WAIT_AFTER_ACTIONS", "5"))

        download_dir.mkdir(parents=True, exist_ok=True)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            topics=topics,
            video_sources=video_sources,
            download_dir=download_dir,
            headless=headless,
            debug=debug,
            user_data_dir=user_data_dir,
            captions=captions,
            hashtags=hashtags,
            max_videos=max_videos,
            like_limit=like_limit,
            follow_limit=follow_limit,
            attach_rate=attach_rate,
            wait_after_actions=wait_after_actions,
        )
