"""Download helpers for media assets."""
from __future__ import annotations

import logging
import os
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

from .scraper import VideoItem


class VideoDownloader:
    def __init__(self, download_dir: Path, logger: logging.Logger) -> None:
        self.download_dir = download_dir
        self.logger = logger

    def _safe_name(self, url: str) -> str:
        filename = url.split("/")[-1].split("?")[0]
        if not filename.endswith(".mp4"):
            filename = f"video_{abs(hash(url))}.mp4"
        return filename

    def download(self, item: VideoItem) -> Optional[Path]:
        target = self.download_dir / self._safe_name(item.url)
        if target.exists():
            self.logger.debug("Reusing cached download: %s", target)
            return target
        try:
            with urllib.request.urlopen(item.url, timeout=30) as response:
                with open(target, "wb") as handle:
                    shutil.copyfileobj(response, handle)
            self.logger.info("Downloaded %s", target)
            return target
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Failed to download %s: %s", item.url, exc)
            if target.exists():
                try:
                    os.remove(target)
                except OSError:
                    pass
            return None
