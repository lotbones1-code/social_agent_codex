from playwright.sync_api import TimeoutError as PlaywrightTimeoutError


class XLoginError(Exception):
    pass


def is_logged_in(page):
    """Return True if X appears logged in."""
    try:
        el = page.locator(
            'div[data-testid="SideNav_AccountSwitcher_Button"], '
            'a[data-testid="SideNav_NewTweet_Button"], '
            'a[href="/compose/tweet"]'
        )
        return el.first.is_visible(timeout=3000)
    except TimeoutError:
        return False
    except PlaywrightTimeoutError:
        return False


def ensure_x_logged_in(page):
    """
    Manual-login mode:
    - Uses the existing persistent profile.
    - If already logged in: print a message and return.
    - If not: open X login once, let ME log in manually in that window,
      poll up to 3 minutes for a logged-in state, then continue.
    - If still not logged in after timeout: raise XLoginError with a clear message.
    """
    page.goto("https://x.com/home", wait_until="networkidle")
    if is_logged_in(page):
        print("[X] Already logged in with existing session.")
        return

    print("[X] Not logged in. Opening login flow for manual sign-in.")
    page.goto("https://x.com/i/flow/login", wait_until="networkidle")

    total_wait_ms = 180000
    step_ms = 5000
    waited = 0

    while waited < total_wait_ms:
        if is_logged_in(page):
            print("[X] Manual login successful. Session saved. Continuing automation.")
            return
        page.wait_for_timeout(step_ms)
        waited += step_ms

    raise XLoginError("[X] Manual login not detected in time. Run again and finish logging in.")
