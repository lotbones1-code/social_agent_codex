from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
)

from .config import AgentConfig


class BrowserSession:
    """Thin wrapper that ensures Playwright context, page, and login state."""

    def __init__(
        self,
        browser: Browser,
        context: BrowserContext,
        page: Page,
        config: AgentConfig,
        logger: logging.Logger,
    ):
        self.browser = browser
        self.context = context
        self.page = page
        self.config = config
        self.logger = logger

    def close(self) -> None:
        try:
            self.logger.debug("Closing browser context")
            self.context.storage_state(path=str(self.config.auth_state))
            self.context.close()
            self.browser.close()
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
            if self._is_logged_in(page) or page.url.startswith("https://x.com/home"):
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

        # Try to connect to Chrome via CDP with retries
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                self.logger.info("Connecting to Chrome via CDP (attempt %d/%d)...", attempt, max_retries)
                browser = chromium.connect_over_cdp("http://localhost:9222")
                self.logger.info("✔ Connected to Chrome successfully")
                break
            except PlaywrightError as exc:
                if attempt < max_retries:
                    self.logger.warning("CDP connection failed (attempt %d/%d): %s. Retrying in 2s...", attempt, max_retries, exc)
                    time.sleep(2)
                else:
                    self.logger.error("Unable to connect to Chrome over CDP after %d attempts: %s", max_retries, exc)
                    self.logger.error("Make sure Chrome is running with: google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.real_x_profile")
                    return None

        auth_path = self.config.auth_state
        has_auth_state = auth_path.exists()

        try:
            context: BrowserContext = browser.contexts[0]
        except IndexError:
            self.logger.error("No browser contexts available from the connected Chrome instance.")
            try:
                browser.close()
            except PlaywrightError:
                pass
            return None

        page: Page = context.new_page()

        if has_auth_state:
            self.logger.info("Restoring login session from %s", auth_path)
            try:
                self.logger.debug("Navigating to X home page...")
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
                self.logger.debug("Reloading page to ensure session is active...")
                page.reload(wait_until="domcontentloaded", timeout=60000)
                time.sleep(1)
            except PlaywrightError as exc:
                self.logger.warning("Home load after state restore failed: %s. Will attempt login.", exc)
        else:
            self.logger.info("No saved auth state found. Manual login required.")
            try:
                self.logger.debug("Loading X login page...")
                page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
                time.sleep(1)
            except PlaywrightError as exc:
                self.logger.warning("Login page load failed: %s. Waiting for manual input regardless.", exc)
            if not self._prompt_manual_login(page):
                try:
                    context.close()
                except PlaywrightError:
                    pass
                try:
                    browser.close()
                except PlaywrightError:
                    pass
                return None

        if not self._is_logged_in(page):
            self.logger.warning("Session validation failed. Attempting re-authentication...")
            try:
                self.logger.debug("Navigating to login page...")
                page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
                time.sleep(1)
            except PlaywrightError as exc:
                self.logger.warning("Could not navigate to login page: %s", exc)
            if not self._prompt_manual_login(page):
                try:
                    context.close()
                except PlaywrightError:
                    pass
                try:
                    browser.close()
                except PlaywrightError:
                    pass
                return None

        self.logger.info("Authenticated X session ready.")
        return BrowserSession(browser, context, page, self.config, self.logger)


__all__ = ["BrowserManager", "BrowserSession"]
