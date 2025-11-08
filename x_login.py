"""Automated X login helper."""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, Error as PlaywrightError

LOGIN_URL = "https://x.com/login"
SUCCESS_SELECTORS = (
    "[data-testid=\"SideNav_NewTweet_Button\"]",
    "a[aria-label=\"Profile\"]",
)
SCREEN_DIR = Path("logs/screens")


class XLoginError(RuntimeError):
    """Raised when automated X login fails."""


def ensure_x_logged_in(page: Page, user: str, pwd: str, alt_id: Optional[str] = None) -> None:
    """Ensure the provided page is authenticated on X."""

    if not user or not pwd:
        raise XLoginError("X_USERNAME and X_PASSWORD are required for automated login")

    if _is_signed_in(page):
        return

    alt_value = alt_id or user

    last_error: Optional[Exception] = None
    for attempt in range(2):
        try:
            _perform_login(page, user, pwd, alt_value)
            return
        except PlaywrightTimeout as exc:
            last_error = exc
            if attempt == 0:
                try:
                    page.reload(wait_until="domcontentloaded", timeout=45000)
                except PlaywrightError:
                    pass
                if _is_signed_in(page):
                    return
                continue
            break
        except Exception as exc:  # pragma: no cover - defensive guard
            last_error = exc
            break

    _capture_and_raise(page, last_error)


def _perform_login(page: Page, user: str, pwd: str, alt_value: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)

    if _is_signed_in(page):
        return

    if _is_signed_in(page):
        return

    username_input = _wait_for_input(
        page,
        preferred_labels=("Phone, email, or username",),
        fallback_selector="input[name=\"text\"]",
    )
    _type_slow(username_input, user)
    _click_button(page, "Next")

    if _needs_identity_confirmation(page):
        confirm_input = _wait_for_input(
            page,
            preferred_labels=(
                "Enter your phone number or email address",
                "Enter your phone number or username",
                "Phone, email, or username",
            ),
            fallback_selector="input[name=\"text\"]",
        )
        _type_slow(confirm_input, alt_value)
        _click_button(page, "Next")

    password_input = _wait_for_input(
        page,
        preferred_labels=("Password",),
        fallback_selector="input[name=\"password\"]",
    )
    _type_slow(password_input, pwd)
    _click_button(page, "Log in")

    for selector in SUCCESS_SELECTORS:
        try:
            page.wait_for_selector(selector, state="visible", timeout=30000)
            return
        except PlaywrightTimeout:
            continue

    raise PlaywrightTimeout("Login did not reach a signed-in state")


def _is_signed_in(page: Page) -> bool:
    try:
        if page.url.startswith("https://x.com/home"):
            return True
    except PlaywrightError:
        pass

    for selector in SUCCESS_SELECTORS:
        try:
            locator = page.locator(selector)
            if locator.count() and locator.first.is_visible():
                return True
        except PlaywrightTimeout:
            continue
        except PlaywrightError:
            continue
        except Exception:
            continue
    return False


def _wait_for_input(
    page: Page,
    preferred_labels: tuple[str, ...],
    fallback_selector: str,
    timeout: float = 20000,
):
    for label in preferred_labels:
        try:
            locator = page.get_by_label(label)
            locator.wait_for(state="visible", timeout=timeout)
            return locator
        except Exception:
            continue
    locator = page.locator(fallback_selector).first
    locator.wait_for(state="visible", timeout=timeout)
    return locator


def _click_button(page: Page, name: str) -> None:
    button = page.get_by_role("button", name=name)
    button.wait_for(state="visible", timeout=20000)
    button.click()
    time.sleep(0.5)


def _needs_identity_confirmation(page: Page) -> bool:
    hints = (
        "Enter your phone number or email address",
        "Enter your phone number or username",
    )
    for hint in hints:
        try:
            locator = page.get_by_text(hint, exact=False).first
            locator.wait_for(state="visible", timeout=1000)
            return True
        except PlaywrightTimeout:
            continue
        except PlaywrightError:
            continue
        except Exception:
            continue
    try:
        confirm_locator = page.locator("input[name=\"text\"]").nth(0)
        confirm_locator.wait_for(state="visible", timeout=1000)
        autocomplete = confirm_locator.get_attribute("autocomplete") or ""
        if "username" not in autocomplete.lower():
            return True
    except PlaywrightTimeout:
        pass
    except PlaywrightError:
        pass
    except Exception:
        pass
    return False


def _type_slow(locator, text: str, delay: float = 80) -> None:
    locator.click()
    try:
        locator.fill("")
    except PlaywrightError:
        pass
    locator.type(text, delay=delay)
    time.sleep(0.3)


def _capture_and_raise(page: Page, exc: Optional[Exception]) -> None:
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = SCREEN_DIR / f"{stamp}.png"
    try:
        page.screenshot(path=str(path))
    except PlaywrightError:
        pass
    message = "Automated X login failed"
    if exc is not None:
        message = f"{message}: {exc}"
    raise XLoginError(message)
