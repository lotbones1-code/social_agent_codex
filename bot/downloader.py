from __future__ import annotations

import logging
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
