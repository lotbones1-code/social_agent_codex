#!/usr/bin/env python3
"""Test script to verify manual login works correctly."""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout, Error as PlaywrightError

# Load environment
load_dotenv()

def is_logged_in(page) -> bool:
    """Check if user is logged in to X/Twitter."""
    try:
        if page.is_closed():
            return False
    except PlaywrightError:
        return False

    # Check for logged-in indicators
    selectors = [
        "div[data-testid='SideNav_AccountSwitcher_Button']",
        "a[aria-label='Profile']",
        "a[href='/compose/post']",
    ]
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.is_visible(timeout=2000):
                return True
        except PlaywrightError:
            continue

    # Check URL
    try:
        current_url = page.url
        return "x.com/home" in current_url or "twitter.com/home" in current_url
    except PlaywrightError:
        return False


def test_manual_login():
    """Test the manual login flow."""
    print("="*70)
    print("TESTING MANUAL LOGIN FLOW")
    print("="*70)
    print()

    user_data_dir = str(Path.home() / ".social_agent_codex/browser_session/")
    os.makedirs(user_data_dir, exist_ok=True)

    with sync_playwright() as p:
        print("✓ Launching browser (visible mode)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # Always visible for testing
            args=["--start-maximized", "--no-sandbox"],
        )

        print("✓ Creating page...")
        page = context.new_page()

        # Check if session already exists
        session_marker = Path(user_data_dir) / ".session_exists"
        if session_marker.exists():
            print("✓ Found existing session, testing restore...")
            try:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
                if is_logged_in(page):
                    print("✓ Session restored successfully!")
                    print()
                    print("="*70)
                    print("TEST PASSED: Existing session works")
                    print("="*70)
                    context.close()
                    return True
                else:
                    print("⚠ Session expired, need to login again")
            except (PlaywrightTimeout, PlaywrightError) as e:
                print(f"⚠ Error restoring session: {e}")

        # Navigate to login page
        print("✓ Navigating to X/Twitter login page...")
        try:
            page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)  # Let page settle
            print("✓ Login page loaded")
        except PlaywrightTimeout:
            print("✗ Timeout loading login page")
            context.close()
            return False

        # Wait for manual login
        print()
        print("="*70)
        print("MANUAL LOGIN TIME")
        print("="*70)
        print()
        print("The browser is open at the login page.")
        print("THE SCRIPT WILL NOT TOUCH ANYTHING.")
        print()
        print("Please:")
        print("  1. Log in to your X/Twitter account")
        print("  2. Complete any 2FA or security checks")
        print("  3. Wait until you see your home feed")
        print("  4. Come back here and press ENTER")
        print()
        print("="*70)
        print()

        try:
            input("Press ENTER after you've logged in: ")
        except (KeyboardInterrupt, EOFError):
            print("\n✗ Login cancelled")
            context.close()
            return False

        # Verify login
        print()
        print("✓ Verifying login...")
        time.sleep(2)

        max_retries = 3
        for attempt in range(max_retries):
            if is_logged_in(page):
                print("✓ Login verified!")
                time.sleep(3)  # Let session stabilize

                # Mark session as existing
                session_marker.touch()
                print(f"✓ Session marker created: {session_marker}")

                print()
                print("="*70)
                print("TEST PASSED: Manual login successful!")
                print("="*70)
                print()
                print(f"Session saved to: {user_data_dir}")
                print("Next run will restore this session automatically.")
                print()

                context.close()
                return True
            else:
                if attempt < max_retries - 1:
                    print(f"⚠ Login not detected yet, retrying... ({attempt + 1}/{max_retries})")
                    time.sleep(2)

        # Login verification failed
        print()
        print("="*70)
        print("WARNING: Login verification failed")
        print("="*70)
        print()
        print("Could not verify that you're logged in.")
        print("This might mean:")
        print("  - You're not on the home feed yet")
        print("  - You're stuck on a security check")
        print("  - The login didn't complete")
        print()
        print("You can:")
        print("  1. Press ENTER to save anyway (if you're sure you're logged in)")
        print("  2. Press Ctrl+C to cancel")
        print()

        try:
            input("Press ENTER to save anyway, or Ctrl+C to cancel: ")
            session_marker.touch()
            print(f"✓ Session marker created: {session_marker}")
            print()
            print("="*70)
            print("TEST COMPLETED (with warnings)")
            print("="*70)
            context.close()
            return True
        except (KeyboardInterrupt, EOFError):
            print("\n✗ Cancelled")
            context.close()
            return False


if __name__ == "__main__":
    try:
        success = test_manual_login()
        exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        exit(1)
    except Exception as e:
        print(f"\n\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
