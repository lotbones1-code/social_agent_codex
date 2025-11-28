from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

import requests


class VideoDownloader:
    """Download remote video assets to the local filesystem.

    When running with a Premium+ session, cookies from the authenticated browser
    are injected into the requests session to unlock higher-quality video
    streams.
    """

    def __init__(self, download_dir: Path, logger: logging.Logger, *, user_agent: str | None = None):
        self.download_dir = download_dir
        self.logger = logger
        self.session = requests.Session()
        if user_agent:
            self.session.headers.update({"User-Agent": user_agent})

    def set_cookies(self, cookies: Iterable[dict]) -> None:
        count = 0
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            domain = cookie.get("domain")
            if name and value:
                self.session.cookies.set(name, value, domain=domain)
                count += 1
        if count:
            self.logger.info("Injected %d Premium+ cookies into downloader", count)

    def download(self, url: str, *, filename_hint: str) -> Optional[Path]:
        target = self.download_dir / f"{filename_hint}.mp4"
        self.logger.info("Downloading video %s -> %s", url, target)
        try:
            response = self.session.get(url, stream=True, timeout=90)
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
