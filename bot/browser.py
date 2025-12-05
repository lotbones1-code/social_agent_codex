from __future__ import annotations

import logging
import time
from typing import Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Page,
    Playwright,
)

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    Stealth = None

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

    def _launch_persistent_context(self, chromium) -> Optional[BrowserContext]:
        self.config.user_data_dir.mkdir(parents=True, exist_ok=True)
        # Stealth browser args to avoid bot detection
        stealth_args = [
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]
        launch_kwargs = {
            "user_data_dir": str(self.config.user_data_dir),
            "headless": self.config.headless,
            "args": stealth_args,
            "ignore_default_args": ["--enable-automation"],
            "viewport": {"width": 1280, "height": 900},
        }

        storage_state = None
        if self.config.auth_state.exists():
            storage_state = str(self.config.auth_state)
            self.logger.info("Restoring login session from %s", storage_state)

        try:
            return chromium.launch_persistent_context(**launch_kwargs)
        except PlaywrightError as exc:
            self.logger.error("Unable to launch persistent context: %s", exc)
            return None

    def _ensure_logged_in(self, page: Page, context: BrowserContext) -> bool:
        if self._is_logged_in(page):
            return True

        try:
            page.goto("https://x.com/login", wait_until="networkidle", timeout=60000)
        except PlaywrightError:
            self.logger.warning("Could not navigate to login page for re-authentication.")

        if not self._prompt_manual_login(page):
            return False

        try:
            context.storage_state(path=str(self.config.auth_state))
        except PlaywrightError as exc:
            self.logger.warning("Failed to persist storage state: %s", exc)
        return True

    def start(self) -> Optional[BrowserSession]:
        chromium = self.playwright.chromium
        context = self._launch_persistent_context(chromium)
        if context is None:
            return None

        page: Page = context.new_page()

        # Apply stealth mode to avoid bot detection
        if HAS_STEALTH and Stealth:
            try:
                stealth = Stealth()
                stealth.apply_stealth_sync(page)
                self.logger.info("Stealth mode applied to browser page")
            except Exception as exc:
                self.logger.warning("Could not apply stealth mode: %s", exc)
        else:
            self.logger.debug("playwright-stealth not installed; skipping stealth mode")

        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        except PlaywrightError:
            self.logger.debug("Initial home navigation failed; continuing to login check.")

        if not self._ensure_logged_in(page, context):
            try:
                context.close()
            except PlaywrightError:
                pass
            return None

        self.logger.info("Authenticated X session ready (persistent profile: %s)", self.config.user_data_dir)
        return BrowserSession(context.browser, context, page, self.config, self.logger)


__all__ = ["BrowserManager", "BrowserSession"]
