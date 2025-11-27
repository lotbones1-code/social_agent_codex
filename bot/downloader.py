from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import requests


class VideoDownloader:
    """Download remote video assets to the local filesystem."""

    def __init__(self, download_dir: Path, logger: logging.Logger):
        self.download_dir = download_dir
        self.logger = logger

    def download(self, url: str, *, filename_hint: str) -> Optional[Path]:
        target = self.download_dir / f"{filename_hint}.mp4"

        # If it's an X/Twitter URL, use yt-dlp
        if "x.com" in url or "twitter.com" in url:
            return self._download_with_ytdlp(url, target)

        # Otherwise use direct download
        return self._download_direct(url, target)

    def _download_with_ytdlp(self, url: str, target: Path) -> Optional[Path]:
        """Download video from X/Twitter using yt-dlp."""
        self.logger.info("Downloading X video %s -> %s", url, target)
        try:
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--no-warnings",
                "-f", "best[ext=mp4]/best",
                "-o", str(target),
                url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and target.exists():
                self.logger.info("Successfully downloaded video with yt-dlp")
                return target
            else:
                self.logger.warning("yt-dlp failed: %s", result.stderr)
                return None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as exc:
            self.logger.warning("Failed to download with yt-dlp: %s", exc)
            return None

    def _download_direct(self, url: str, target: Path) -> Optional[Path]:
        """Direct download for video URLs."""
        self.logger.info("Downloading video %s -> %s", url, target)
        try:
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
            return target
        except requests.RequestException as exc:
            self.logger.warning("Failed to download %s: %s", url, exc)
            return None


__all__ = ["VideoDownloader"]
