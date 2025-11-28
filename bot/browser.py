"""Browser management with support for CDP connection to real Chrome."""
from __future__ import annotations

import logging
import os
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


class BrowserSession:
    """Wrapper for browser session with auto-save of auth state."""

    def __init__(
        self,
        playwright: Playwright,
        browser: Browser,
        context: BrowserContext,
        page: Page,
        logger: logging.Logger,
        is_cdp: bool = False,
    ):
        self.playwright = playwright
        self.browser = browser
        self.context = context
        self.page = page
        self.logger = logger
        self.is_cdp = is_cdp

    def close(self) -> None:
        """Close browser session. For CDP, only closes page/context, not browser."""
        try:
            if not self.is_cdp:
                self.logger.debug("Closing browser session")
                try:
                    self.context.close()
                except PlaywrightError:
                    pass
                try:
                    self.browser.close()
                except PlaywrightError:
                    pass
            else:
                self.logger.debug("CDP session - leaving browser open")
                # For CDP, just close the page we created
                try:
                    if not self.page.is_closed():
                        self.page.close()
                except PlaywrightError:
                    pass
        except Exception as exc:
            self.logger.warning("Error while closing browser: %s", exc)


class BrowserManager:
    """Manages browser connection - supports both CDP and regular launch."""

    def __init__(self, playwright: Playwright, logger: logging.Logger):
        self.playwright = playwright
        self.logger = logger

    def _is_logged_in(self, page: Page) -> bool:
        """Check if user is logged into X."""
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

    def start_cdp(self, cdp_url: str = "http://localhost:9222") -> Optional[BrowserSession]:
        """
        Connect to real Chrome via CDP.

        Chrome must be started with:
        /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
          --remote-debugging-port=9222 \\
          --user-data-dir=$HOME/.real_x_profile \\
          --no-first-run \\
          --no-default-browser-check
        """
        self.logger.info("Attempting CDP connection to %s", cdp_url)
        try:
            browser = self.playwright.chromium.connect_over_cdp(cdp_url)
            self.logger.info("Connected to Chrome via CDP")

            # Use the existing context (real Chrome profile)
            contexts = browser.contexts
            if not contexts:
                self.logger.error("No browser contexts found. Is Chrome running with a profile?")
                return None

            context = contexts[0]
            self.logger.info("Using existing Chrome context with %d pages", len(context.pages))

            # Create a new page in the existing context
            page = context.new_page()
            self.logger.info("Created new page in CDP session")

            # Navigate to X home to verify login
            try:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)
            except PlaywrightError as exc:
                self.logger.warning("Initial navigation to /home: %s", exc)

            if not self._is_logged_in(page):
                self.logger.warning("Not logged in. Please log into X in the Chrome window.")
                return None

            self.logger.info("Authenticated X session ready via CDP")
            return BrowserSession(self.playwright, browser, context, page, self.logger, is_cdp=True)

        except Exception as exc:
            self.logger.error("CDP connection failed: %s", exc)
            self.logger.error(
                "Make sure Chrome is running with: "
                "google-chrome --remote-debugging-port=9222 --user-data-dir=$HOME/.real_x_profile"
            )
            return None

    def start_regular(self, headless: bool = False) -> Optional[BrowserSession]:
        """
        Launch regular Playwright Chromium (fallback).
        Note: This may be detected as automation by X.
        """
        self.logger.info("Launching Playwright Chromium (headless=%s)", headless)
        try:
            browser = self.playwright.chromium.launch(
                headless=headless,
                args=[
                    "--start-maximized",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
        except PlaywrightError as exc:
            self.logger.error("Unable to launch Chromium: %s", exc)
            return None

        # Try to restore auth from auth.json
        auth_path = Path("auth.json")
        context: BrowserContext
        page: Page

        if auth_path.exists():
            self.logger.info("Restoring login session from %s", auth_path)
            try:
                context = browser.new_context(storage_state=str(auth_path))
            except PlaywrightError as exc:
                self.logger.error("Could not load saved auth state: %s", exc)
                browser.close()
                return None
            page = context.new_page()
            try:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)
            except PlaywrightError as exc:
                self.logger.warning("Home load after state restore failed: %s", exc)
        else:
            context = browser.new_context()
            page = context.new_page()
            self.logger.warning("No auth.json found - you'll need to log in manually")
            try:
                page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            except PlaywrightError:
                pass

        if not self._is_logged_in(page):
            self.logger.warning("Not logged in. Please log into X manually.")
            return None

        self.logger.info("Authenticated X session ready")
        return BrowserSession(self.playwright, browser, context, page, self.logger, is_cdp=False)


__all__ = ["BrowserManager", "BrowserSession"]
