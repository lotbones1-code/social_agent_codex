#!/usr/bin/env python3
"""Run the full bot in your existing logged-in Chrome browser."""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from social_agent import (
    load_config, MessageRegistry, VideoService, run_engagement_loop,
    MESSAGE_LOG_PATH
)
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import logging

load_dotenv()
config = load_config()

logging.basicConfig(
    level=logging.DEBUG if config.debug else logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)
logger = logging.getLogger("social_agent_chrome")

logger.info("Search topics: %s", ", ".join(config.search_topics))
logger.info("Connecting to your Chrome browser...")

print()
print("="*70)
print("IMPORTANT: Make sure Chrome is running with:")
print("/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\")
print("  --remote-debugging-port=9222 \\")
print("  --user-data-dir=\"/tmp/chrome-debug\" &")
print()
print("And that you're logged in to x.com in that Chrome window.")
print("="*70)
print()

registry = MessageRegistry(MESSAGE_LOG_PATH)
video_service = VideoService(config)

try:
    with sync_playwright() as p:
        # Connect to your existing Chrome
        browser = p.chromium.connect_over_cdp("http://localhost:9222")

        contexts = browser.contexts
        if not contexts:
            print("Error: Chrome not found. Make sure it's running with --remote-debugging-port=9222")
            exit(1)

        context = contexts[0]
        pages = context.pages

        if pages:
            page = pages[0]
        else:
            page = context.new_page()

        logger.info("✓ Connected to Chrome!")
        logger.info("✓ Starting bot...")
        print()
        print("="*70)
        print("BOT IS RUNNING IN YOUR CHROME BROWSER")
        print("="*70)
        print("Press Ctrl+C to stop")
        print("="*70)
        print()

        # Run the full engagement loop
        run_engagement_loop(config, registry, page, video_service, logger)

except KeyboardInterrupt:
    logger.info("Bot stopped by user.")
except Exception as e:
    logger.error(f"Error: {e}")
    import traceback
    traceback.print_exc()
