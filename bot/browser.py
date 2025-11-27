from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
)

from .config import AgentConfig


class BrowserSession:
    """Thin wrapper that ensures Playwright context, page, and login state."""

    def __init__(self, context: BrowserContext, page: Page, config: AgentConfig, logger: logging.Logger):
        self.context = context
        self.page = page
        self.config = config
        self.logger = logger

    def close(self) -> None:
        try:
            self.logger.debug("Closing browser context")
            self.context.storage_state(path=str(self.config.auth_state))
            self.context.close()
        except PlaywrightError as exc:
            self.logger.warning("Error while closing browser context: %s", exc)


class BrowserManager:
    def __init__(self, playwright: Playwright, config: AgentConfig, logger: logging.Logger):
        self.playwright = playwright
        self.config = config
        self.logger = logger

    def _is_logged_in(self, page: Page) -> bool:
        try:
            if page.is_closed():
                return False
        except PlaywrightError:
            return False
        selectors = [
            "div[data-testid='SideNav_NewTweet_Button']",
            "a[aria-label='Profile']",
            "a[href='/compose/post']",
        ]
        for selector in selectors:
            try:
                if page.locator(selector).is_visible(timeout=2000):
                    return True
            except PlaywrightError:
                continue
        return False

    def _prompt_manual_login(self, page: Page) -> bool:
        self.logger.info(
            "No saved login was available. Please complete the X login in the opened window."
        )
        deadline = time.time() + 600
        last_log = 0.0
        while time.time() < deadline:
            if self._is_logged_in(page):
                time.sleep(3)
                try:
                    page.context.storage_state(path=str(self.config.auth_state))
                except PlaywrightError as exc:
                    self.logger.error("Could not persist auth state: %s", exc)
                    return False
                self.logger.info("Login detected and saved. Continuing.")
                return True
            if time.time() - last_log > 10:
                remaining = int(deadline - time.time())
                self.logger.info("Waiting for manual login... (%ss left)", remaining)
                last_log = time.time()
            time.sleep(3)
        self.logger.error("Timed out waiting for login. Please retry.")
        return False

    def start(self) -> Optional[BrowserSession]:
        chromium = self.playwright.chromium
        try:
            context = chromium.launch_persistent_context(
                user_data_dir=str(self.config.user_data_dir),
                headless=self.config.headless,
                args=["--start-maximized", "--no-sandbox"],
            )
        except PlaywrightError as exc:
            self.logger.error("Unable to launch Chromium: %s", exc)
            return None

        page = context.new_page()
        if self.config.auth_state.exists():
            self.logger.info("Restoring login session from %s", self.config.auth_state)
            try:
                context.storage_state(path=str(self.config.auth_state))
            except PlaywrightError:
                self.logger.debug("Existing state file could not be read; proceeding without it.")

        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError:
            self.logger.debug("Home page check failed; continuing to login verification.")

        if not self._is_logged_in(page):
            try:
                page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            except PlaywrightError:
                self.logger.warning("Login page could not be loaded; attempting manual wait.")
            if not self._prompt_manual_login(page):
                try:
                    context.close()
                except PlaywrightError:
                    pass
                return None

        self.logger.info("Authenticated X session ready.")
        return BrowserSession(context, page, self.config, self.logger)


__all__ = ["BrowserManager", "BrowserSession"]
