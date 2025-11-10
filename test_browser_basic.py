#!/usr/bin/env python3
"""Ultra-simple test to verify browser opens at all."""

import os
import time
from pathlib import Path

print("="*70)
print("BASIC BROWSER TEST")
print("="*70)
print()

# Test 1: Check Playwright is installed
print("Test 1: Checking if Playwright is installed...")
try:
    from playwright.sync_api import sync_playwright
    print("✓ Playwright is installed")
except ImportError as e:
    print(f"✗ Playwright is NOT installed: {e}")
    print("\nInstall it with: pip install playwright")
    print("Then run: playwright install chromium")
    exit(1)

# Test 2: Try to launch browser
print("\nTest 2: Launching browser in VISIBLE mode...")
print("A browser window should open now...")

user_data_dir = str(Path.home() / ".social_agent_codex/browser_test/")
os.makedirs(user_data_dir, exist_ok=True)
print(f"Using directory: {user_data_dir}")

try:
    with sync_playwright() as p:
        print("✓ Playwright started")

        print("✓ Launching browser context (visible)...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,  # ALWAYS visible for this test
            args=["--start-maximized", "--no-sandbox"],
        )
        print("✓ Browser context created!")

        print("✓ Creating page...")
        page = context.new_page()
        print("✓ Page created!")

        print("✓ Navigating to X/Twitter login page...")
        page.goto("https://x.com/login", wait_until="domcontentloaded", timeout=60000)
        print("✓ Page loaded!")

        print()
        print("="*70)
        print("SUCCESS! Browser is open and showing Twitter login page")
        print("="*70)
        print()
        print("The browser should be visible on your screen.")
        print("Press ENTER to close the browser and end the test...")

        input()

        print("\nClosing browser...")
        context.close()
        print("✓ Browser closed")

        print()
        print("="*70)
        print("ALL TESTS PASSED!")
        print("="*70)
        print()
        print("Your system can launch browsers correctly.")
        print("The manual login should work fine.")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    print("\nFull error details:")
    import traceback
    traceback.print_exc()
    print()
    print("="*70)
    print("TROUBLESHOOTING")
    print("="*70)
    print()
    print("If you see 'Executable doesn't exist' error:")
    print("  Run: playwright install chromium")
    print()
    print("If you see permission errors:")
    print("  Check that ~/.social_agent_codex/ is writable")
    print()
    print("If you see display errors:")
    print("  Make sure you're running with a display (not in SSH without X11)")
    exit(1)
