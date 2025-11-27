"""Browser utilities for Playwright sessions."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import BrowserContext, Error, Page, sync_playwright

from .config import BotSettings

LOGIN_SELECTORS = [
    "div[data-testid='SideNav_AccountSwitcher_Button']",
    "a[aria-label='Profile']",
    "a[href='/compose/post']",
]


class BrowserSession:
    """Manage a persistent Playwright session with login preservation."""

    def __init__(self, config: BotSettings, logger: logging.Logger) -> None:
        self.config = config
        self.logger = logger
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def __enter__(self) -> "BrowserSession":
        self.playwright = sync_playwright().start()
        chromium = self.playwright.chromium
        self.context = chromium.launch_persistent_context(
            user_data_dir=str(self.config.user_data_dir),
            headless=self.config.headless,
            args=["--start-maximized", "--no-sandbox"],
        )
        self.page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.context:
                self.context.close()
        finally:
            if self.playwright:
                self.playwright.stop()

    # Login helpers -----------------------------------------------------
    def is_logged_in(self) -> bool:
        if not self.page:
            return False
        try:
            for selector in LOGIN_SELECTORS:
                locator = self.page.locator(selector)
                if locator.is_visible(timeout=1500):
                    return True
            current = self.page.url
            return "x.com/home" in current or "twitter.com/home" in current
        except Error:
            return False

    def wait_for_manual_login(self, timeout: int = 600) -> bool:
        assert self.page is not None
        deadline = time.time() + timeout
        self.logger.info("No stored session detected. Please sign in within the browser window.")
        while time.time() < deadline:
            if self.is_logged_in():
                self.logger.info("Login detected. Persisting session in %s", self.config.user_data_dir)
                time.sleep(3)
                return True
            time.sleep(3)
        self.logger.error("Timed out waiting for manual login.")
        return False

    def ensure_login(self) -> bool:
        assert self.page is not None
        try:
            self.page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        except Error as exc:
            self.logger.warning("Failed to load home timeline while checking login: %s", exc)
        if self.is_logged_in():
            return True
        try:
            self.page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        except Error as exc:
            self.logger.error("Unable to open login page: %s", exc)
            return False
        return self.wait_for_manual_login()


def start_session(config: BotSettings, logger: logging.Logger) -> Optional[BrowserSession]:
    try:
        session = BrowserSession(config, logger)
        session.__enter__()
    except Error as exc:
        logger.error("Unable to start Playwright session: %s", exc)
        return None
    return session
