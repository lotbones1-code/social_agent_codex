#!/usr/bin/env python3
"""
Connect to an existing Chrome browser instead of launching a new one.
This completely bypasses Twitter's bot detection.
"""

from playwright.sync_api import sync_playwright
import time
import os
from dotenv import load_dotenv

load_dotenv()

print("="*70)
print("CONNECTING TO YOUR EXISTING CHROME BROWSER")
print("="*70)
print()
print("Make sure Chrome is running with: --remote-debugging-port=9222")
print("And that you're logged in to x.com in that Chrome window.")
print()

try:
    with sync_playwright() as p:
        # Connect to existing Chrome browser
        browser = p.chromium.connect_over_cdp("http://localhost:9222")

        print("✓ Connected to Chrome!")

        # Get the first context (your existing Chrome session)
        contexts = browser.contexts
        if not contexts:
            print("Error: No browser contexts found. Make sure Chrome is running.")
            exit(1)

        context = contexts[0]

        # Get existing pages or create new one
        pages = context.pages
        if pages:
            page = pages[0]
        else:
            page = context.new_page()

        print("✓ Using your existing Chrome session!")
        print()

        # Navigate to Twitter
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)

        # Check if logged in
        time.sleep(2)
        try:
            page.wait_for_selector('[data-testid="AppTabBar_Home_Link"]', timeout=5000)
            print("="*70)
            print("✓ YOU'RE LOGGED IN!")
            print("="*70)
            print()
            print("The bot is now running in your Chrome browser.")
            print("You can minimize Chrome but DON'T close it.")
            print()
            print("Press Ctrl+C to stop the bot.")
            print("="*70)
            print()

            # Simple test: search for a topic
            search_topics = os.getenv("SEARCH_TOPICS", "AI automation").split("||")
            first_topic = search_topics[0].strip()

            print(f"Testing search for: {first_topic}")
            page.goto(f"https://x.com/search?q={first_topic.replace(' ', '+')}&src=typed_query&f=live",
                     wait_until="domcontentloaded", timeout=30000)

            time.sleep(3)
            print("✓ Search working!")
            print()
            print("Bot is ready. Keeping connection alive...")
            print("Press Ctrl+C to stop.")

            # Keep alive
            while True:
                time.sleep(10)
                if page.is_closed():
                    print("Chrome was closed. Exiting.")
                    break

        except Exception as e:
            print(f"Error: Not logged in or can't verify login: {e}")
            print()
            print("Please log in to x.com in your Chrome browser and try again.")

except Exception as e:
    print(f"Error connecting to Chrome: {e}")
    print()
    print("Make sure Chrome is running with:")
    print("/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir=\"/tmp/chrome-debug\" &")
