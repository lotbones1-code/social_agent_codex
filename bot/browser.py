from __future__ import annotations

import logging
import time
from typing import Optional

from playwright.sync_api import (
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
    """Simple wrapper for browser context and page."""

    def __init__(self, context: BrowserContext, page: Page, config: AgentConfig, logger: logging.Logger):
        self.context = context
        self.page = page
        self.config = config
        self.logger = logger

    def close(self) -> None:
        try:
            self.logger.info("Saving session and closing browser...")
            self.context.storage_state(path=str(self.config.auth_state))
            self.context.close()
        except PlaywrightError as exc:
            self.logger.warning("Error closing browser: %s", exc)


class BrowserManager:
    def __init__(self, playwright: Playwright, config: AgentConfig, logger: logging.Logger):
        self.playwright = playwright
        self.config = config
        self.logger = logger

    def _is_logged_in(self, page: Page) -> bool:
        """Check if we're logged into X."""
        try:
            # Check URL first
            if "x.com/home" in page.url or "twitter.com/home" in page.url:
                return True

            # Check for logged-in elements
            selectors = [
                "[data-testid='SideNav_NewTweet_Button']",
                "[aria-label='Profile']",
                "[href='/compose/post']",
                "[data-testid='AppTabBar_Home_Link']",
            ]
            for sel in selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=1500):
                        return True
                except:
                    continue
        except:
            pass
        return False

    def _wait_for_manual_login(self, page: Page) -> bool:
        """Wait for user to complete login manually."""
        self.logger.info("")
        self.logger.info("=" * 50)
        self.logger.info("MANUAL LOGIN REQUIRED")
        self.logger.info("Please log in to X in the browser window.")
        self.logger.info("You have 10 minutes to complete login.")
        self.logger.info("=" * 50)
        self.logger.info("")

        deadline = time.time() + 600  # 10 minutes
        last_log = 0.0

        while time.time() < deadline:
            # Check if logged in
            if self._is_logged_in(page):
                self.logger.info("Login detected! Saving session...")
                time.sleep(2)
                try:
                    self.context.storage_state(path=str(self.config.auth_state))
                    self.logger.info("Session saved to %s", self.config.auth_state)
                except Exception as e:
                    self.logger.warning("Could not save session: %s", e)
                return True

            # Log progress every 15 seconds
            if time.time() - last_log > 15:
                remaining = int(deadline - time.time())
                self.logger.info("Waiting for login... (%d seconds left)", remaining)
                last_log = time.time()

            time.sleep(2)

        self.logger.error("Login timed out after 10 minutes.")
        return False

    def start(self) -> Optional[BrowserSession]:
        """Start browser and ensure login."""
        self.logger.info("Launching browser...")

        # Create profile directory
        self.config.user_data_dir.mkdir(parents=True, exist_ok=True)

        # Browser args for stealth
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

        try:
            # Launch persistent context (keeps login across restarts)
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.config.user_data_dir),
                headless=self.config.headless,
                args=args,
                ignore_default_args=["--enable-automation"],
                viewport={"width": 1280, "height": 900},
            )
        except PlaywrightError as exc:
            self.logger.error("Failed to launch browser: %s", exc)
            return None

        # Get or create page
        if self.context.pages:
            page = self.context.pages[0]
            self.logger.info("Using existing browser page")
        else:
            page = self.context.new_page()
            self.logger.info("Created new browser page")

        # Apply stealth if available
        if HAS_STEALTH and Stealth:
            try:
                stealth = Stealth()
                stealth.apply_stealth_sync(page)
                self.logger.info("Stealth mode applied")
            except Exception as e:
                self.logger.debug("Stealth mode failed: %s", e)

        # Navigate to X
        try:
            self.logger.info("Navigating to X...")
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
        except PlaywrightError:
            self.logger.info("Navigation timeout, checking login status...")

        # Check if already logged in
        if self._is_logged_in(page):
            self.logger.info("Already logged in!")
            return BrowserSession(self.context, page, self.config, self.logger)

        # Need to login - go to login page
        try:
            self.logger.info("Not logged in, going to login page...")
            page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
        except PlaywrightError:
            pass

        # Wait for manual login
        if self._wait_for_manual_login(page):
            return BrowserSession(self.context, page, self.config, self.logger)

        # Login failed - cleanup
        try:
            self.context.close()
        except:
            pass
        return None


__all__ = ["BrowserManager", "BrowserSession"]
