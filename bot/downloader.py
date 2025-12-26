from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Optional

import requests

try:  # Optional dependency; used when direct downloads fail.
    from yt_dlp import YoutubeDL
except Exception:  # pragma: no cover - handled gracefully at runtime
    YoutubeDL = None


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

    def _cookie_header(self) -> str:
        return "; ".join(
            f"{cookie.name}={cookie.value}" for cookie in self.session.cookies
        )

    def _download_direct(self, url: str, target: Path) -> Optional[Path]:
        try:
            response = self.session.get(url, stream=True, timeout=90)
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
            return target
        except requests.RequestException as exc:
            self.logger.debug("Direct download failed for %s: %s", url, exc)
            return None

    def _download_with_yt_dlp(self, tweet_url: str, filename_hint: str) -> Optional[Path]:
        if YoutubeDL is None:
            self.logger.debug("yt_dlp unavailable; skipping fallback download for %s", tweet_url)
            return None

        output_tmpl = str(self.download_dir / f"{filename_hint}.%(ext)s")
        headers = {}
        cookie_header = self._cookie_header()
        if cookie_header:
            headers["Cookie"] = cookie_header

        opts = {
            "outtmpl": output_tmpl,
            "quiet": True,
            "noplaylist": True,
            "retries": 2,
            "nocheckcertificate": True,
            "http_headers": headers,
        }

        try:  # pragma: no cover - network dependent
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(tweet_url, download=True)
                path = Path(ydl.prepare_filename(info))
                return path
        except Exception as exc:  # pragma: no cover - network dependent
            self.logger.warning("yt_dlp failed for %s: %s", tweet_url, exc)
            return None

    def download(self, *, tweet_url: str, video_url: Optional[str], filename_hint: str) -> Optional[Path]:
        target = self.download_dir / f"{filename_hint}.mp4"
        self.logger.info("Downloading video: %s", tweet_url)
        if video_url:
            direct = self._download_direct(video_url, target)
            if direct:
                self.logger.info("Saved video to: %s", direct)
                return direct

        fallback = self._download_with_yt_dlp(tweet_url, filename_hint)
        if fallback:
            self.logger.info("Saved video to: %s", fallback)
            return fallback

        self.logger.warning("Failed to download video from %s", tweet_url)
        return None


__all__ = ["VideoDownloader"]
