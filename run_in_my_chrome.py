#!/usr/bin/env python3
"""Connect to your existing Chrome browser and run the social agent."""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

# Import from social_agent.py
from social_agent import (
    BotConfig,
    MessageRegistry,
    VideoService,
    is_logged_in,
    load_config,
    run_engagement_loop,
    MESSAGE_LOG_PATH,
)


def run_with_existing_chrome():
    """Run the social agent using your existing Chrome session."""
    load_dotenv()
    config = load_config()

    logging.basicConfig(
        level=logging.DEBUG if config.debug else logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("social_agent")

    logger.info("=" * 60)
    logger.info("Running Social Agent with your existing Chrome browser")
    logger.info("=" * 60)
    logger.info("Search topics: %s", ", ".join(config.search_topics))
    logger.info("HEADLESS=%s, DEBUG=%s", config.headless, config.debug)

    registry = MessageRegistry(MESSAGE_LOG_PATH)
    video_service = VideoService(config)

    # Get CDP endpoint from environment or use default
    cdp_url = os.getenv("CHROME_CDP_URL", "http://localhost:9222")

    logger.info(f"[INFO] Attempting to connect to Chrome at {cdp_url}")
    logger.info("[INFO] Make sure Chrome is running with: --remote-debugging-port=9222")

    try:
        with sync_playwright() as p:
            # Connect to existing Chrome instance
            browser = p.chromium.connect_over_cdp(cdp_url)

            # Get the default context (existing Chrome session)
            contexts = browser.contexts
            if not contexts:
                logger.error("No browser contexts found. Make sure Chrome is running.")
                sys.exit(1)

            context = contexts[0]

            # Try to find an existing x.com tab or create a new one
            pages = context.pages
            x_page = None

            for page in pages:
                try:
                    url = page.url
                    if "x.com" in url or "twitter.com" in url:
                        x_page = page
                        logger.info(f"[INFO] Found existing x.com tab: {url}")
                        break
                except Exception:
                    continue

            if not x_page:
                logger.info("[INFO] No x.com tab found, creating a new one...")
                x_page = context.new_page()
                x_page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)

            # Verify we're logged in
            if not is_logged_in(x_page):
                logger.error("[ERROR] Not logged into X. Please log in manually in Chrome first.")
                sys.exit(1)

            logger.info("[INFO] Successfully connected to Chrome and verified X login!")

            # Run the engagement loop
            try:
                logger.info("[INFO] Starting engagement loop...")
                run_engagement_loop(config, registry, x_page, video_service, logger)
            except KeyboardInterrupt:
                logger.info("[INFO] Shutdown requested by user.")
            finally:
                logger.info("[INFO] Disconnecting from Chrome (browser will stay open)...")

    except Exception as exc:
        logger.error(f"[ERROR] Failed to connect to Chrome: {exc}")
        logger.error("\nTo fix this, start Chrome with remote debugging enabled:")
        logger.error("  macOS: /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222")
        logger.error("  Linux: google-chrome --remote-debugging-port=9222")
        logger.error("  Windows: chrome.exe --remote-debugging-port=9222")
        sys.exit(1)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("IMPORTANT: Start Chrome with remote debugging first!")
    print("=" * 60)
    print("\nRun this command in a separate terminal:")
    print("\nmacOS:")
    print('  /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\')
    print('    --remote-debugging-port=9222 \\')
    print('    --user-data-dir="$HOME/chrome-debug-profile"')
    print("\nLinux:")
    print('  google-chrome --remote-debugging-port=9222 \\')
    print('    --user-data-dir="$HOME/chrome-debug-profile"')
    print("\nThen log into x.com in that Chrome window.")
    print("=" * 60)

    input("\nPress ENTER when Chrome is running and you're logged into x.com...")

    try:
        run_with_existing_chrome()
    except KeyboardInterrupt:
        print("\n[INFO] Shutdown complete.")
        sys.exit(0)
