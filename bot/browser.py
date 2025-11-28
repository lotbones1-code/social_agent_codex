from __future__ import annotations

import logging
import shutil
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

    def __init__(
        self,
        context: BrowserContext,
        page: Page,
        config: AgentConfig,
        logger: logging.Logger,
    ):
        self.context = context
        self.page = page
        self.config = config
        self.logger = logger

    def close(self) -> None:
        try:
            self.logger.debug("Closing browser context")
            if self.config.auth_state.exists():
                self.context.storage_state(path=str(self.config.auth_state))
            self.context.close()
        except PlaywrightError as exc:
            self.logger.warning("Error while closing browser context: %s", exc)


class BrowserManager:
    def __init__(self, playwright: Playwright, config: AgentConfig, logger: logging.Logger):
        self.playwright = playwright
        self.config = config
        self.logger = logger
        self.profile_path = Path.home() / ".social_agent_x_profile"

    def _is_logged_in(self, page: Page) -> bool:
        try:
            if page.is_closed():
                return False
        except PlaywrightError:
            return False
        selectors = [
            "a[data-testid='SideNav_NewTweet_Button']",
            "a[aria-label='Profile']",
        ]
        for selector in selectors:
            try:
                if page.locator(selector).is_visible(timeout=3000):
                    return True
            except PlaywrightError:
                continue
        return False

    def _prompt_manual_login(self, page: Page) -> bool:
        self.logger.info(
            "Please complete the X login in the visible Chrome window."
        )
        deadline = time.time() + 600
        last_log = 0.0
        while time.time() < deadline:
            try:
                page.wait_for_selector(
                    "a[data-testid='SideNav_NewTweet_Button']",
                    timeout=5000,
                    state="visible"
                )
                self.logger.info("Login detected! Saving session...")
                time.sleep(2)
                try:
                    page.context.storage_state(path=str(self.config.auth_state))
                    self.logger.info("Session saved successfully.")
                except PlaywrightError as exc:
                    self.logger.warning("Could not save auth state: %s", exc)
                return True
            except PlaywrightError:
                pass

            if time.time() - last_log > 10:
                remaining = int(deadline - time.time())
                self.logger.info("Waiting for manual login... (%ss left)", remaining)
                last_log = time.time()
            time.sleep(3)
        self.logger.error("Timed out waiting for login.")
        return False

    def start(self) -> Optional[BrowserSession]:
        chromium = self.playwright.chromium

        # Ensure profile directory exists
        self.profile_path.mkdir(parents=True, exist_ok=True)

        # Check if profile is corrupted and reset if needed
        lock_file = self.profile_path / "SingletonLock"
        if lock_file.exists():
            self.logger.warning("Removing stale Chrome lock file...")
            try:
                lock_file.unlink()
            except Exception:
                pass

        auth_path = self.config.auth_state
        has_auth_state = auth_path.exists()

        # Launch persistent context with real Chrome
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if not Path(chrome_path).exists():
            self.logger.error("Chrome not found at %s", chrome_path)
            return None

        try:
            self.logger.info("Launching Chrome with persistent context...")
            context = chromium.launch_persistent_context(
                user_data_dir=str(self.profile_path),
                headless=False,
                executable_path=chrome_path,
                args=["--window-size=1280,900", "--no-sandbox"],
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            self.logger.info("✔ Chrome launched successfully")
        except PlaywrightError as exc:
            self.logger.error("Failed to launch Chrome: %s", exc)
            # Try cleaning profile and retry once
            self.logger.warning("Attempting to reset profile...")
            try:
                shutil.rmtree(self.profile_path)
                self.profile_path.mkdir(parents=True, exist_ok=True)
                context = chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_path),
                    headless=False,
                    executable_path=chrome_path,
                    args=["--window-size=1280,900", "--no-sandbox"],
                )
                self.logger.info("✔ Chrome launched after profile reset")
            except Exception as retry_exc:
                self.logger.error("Failed to launch Chrome after reset: %s", retry_exc)
                return None

        # Get or create page
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        # Load auth state if available
        if has_auth_state:
            self.logger.info("Loading saved session from %s", auth_path)
            try:
                import json
                with open(auth_path, 'r') as f:
                    state_data = json.load(f)
                    if 'cookies' in state_data:
                        context.add_cookies(state_data['cookies'])
            except Exception as exc:
                self.logger.warning("Could not load auth state: %s", exc)

        # Navigate to X
        try:
            self.logger.info("Navigating to X...")
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
        except PlaywrightError as exc:
            self.logger.warning("Could not load X home: %s", exc)

        # Check login status
        if not self._is_logged_in(page):
            self.logger.info("Not logged in. Opening login page...")
            try:
                page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
            except PlaywrightError:
                pass

            if not self._prompt_manual_login(page):
                try:
                    context.close()
                except PlaywrightError:
                    pass
                return None

        self.logger.info("✔ Authenticated X session ready")
        return BrowserSession(context, page, self.config, self.logger)


__all__ = ["BrowserManager", "BrowserSession"]
