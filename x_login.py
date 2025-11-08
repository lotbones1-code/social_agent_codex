"""Manual X login helper using Playwright async API."""
from __future__ import annotations

import asyncio
import time
from typing import Iterable

from playwright.async_api import (
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeout,
)

HOME_URL = "https://x.com/home"
LOGIN_URL = "https://x.com/login"
SUCCESS_SELECTORS: Iterable[str] = (
    "div[data-testid=\"SideNav_AccountSwitcher_Button\"]",
    "a[data-testid=\"SideNav_NewTweet_Button\"]",
    "a[href=\"/compose/tweet\"]",
)
POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TIMEOUT_SECONDS = 300


class XLoginError(Exception):
    """Raised when X login state cannot be confirmed."""


async def is_logged_in(page: Page) -> bool:
    """Return True if the provided page appears to be logged in to X."""

    try:
        if page.url.startswith(HOME_URL):
            return True
    except PlaywrightError:
        # Ignore transient navigation issues when checking the URL.
        pass

    for selector in SUCCESS_SELECTORS:
        try:
            locator = page.locator(selector)
            if await locator.count():
                first = locator.first
                if await first.is_visible(timeout=0):
                    return True
        except PlaywrightTimeout:
            continue
        except PlaywrightError:
            continue
    return False


async def ensure_x_logged_in(page: Page, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> None:
    """Ensure the given page is logged in, prompting for manual login if needed."""

    try:
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        pass
    except PlaywrightError:
        pass

    if await is_logged_in(page):
        print("[X] Already logged in.")
        return

    print("[X] Manual login required. Waiting for you to sign in…")
    try:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeout:
        pass
    except PlaywrightError:
        pass

    start = time.time()
    while time.time() - start < timeout_seconds:
        if await is_logged_in(page):
            print("[X] Manual login detected. Continuing automation.")
            return
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

    raise XLoginError("[X] Manual login not detected. Please run again and finish logging in.")
