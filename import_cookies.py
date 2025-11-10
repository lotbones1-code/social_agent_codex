#!/usr/bin/env python3
"""
Import cookies from your regular browser to bypass Twitter's bot detection.

This tool lets you:
1. Log in to Twitter using your normal browser (Chrome/Firefox/Safari)
2. Export your cookies using a browser extension
3. Import those cookies into the social agent

This bypasses Twitter's aggressive bot detection entirely.
"""

import json
import os
import sys
from pathlib import Path

def import_cookies_to_playwright():
    print("="*70)
    print("COOKIE IMPORT TOOL")
    print("="*70)
    print()
    print("This tool will import cookies from your regular browser to bypass")
    print("Twitter's bot detection.")
    print()
    print("STEP 1: Install a cookie export extension in your browser")
    print("  Chrome/Edge: 'EditThisCookie' or 'Cookie-Editor'")
    print("  Firefox: 'Cookie-Editor' or 'Cookie Quick Manager'")
    print()
    print("STEP 2: Log in to Twitter in your regular browser")
    print("  - Open Chrome/Firefox/Safari")
    print("  - Go to https://x.com")
    print("  - Log in normally (Twitter won't block your regular browser)")
    print()
    print("STEP 3: Export cookies")
    print("  - Click the cookie extension icon")
    print("  - Click 'Export' or 'Export All'")
    print("  - Save as JSON format")
    print("  - Save the file somewhere you can find it")
    print()
    print("STEP 4: Enter the path to your exported cookies file below")
    print("="*70)
    print()

    cookie_file = input("Enter path to your exported cookies JSON file: ").strip()

    if not cookie_file:
        print("No file provided. Exiting.")
        return

    # Remove quotes if user pasted path with quotes
    cookie_file = cookie_file.strip('"').strip("'")

    if not os.path.exists(cookie_file):
        print(f"Error: File not found: {cookie_file}")
        return

    print()
    print("Reading cookies...")

    try:
        with open(cookie_file, 'r') as f:
            cookies = json.load(f)
    except Exception as e:
        print(f"Error reading cookie file: {e}")
        return

    # Filter for Twitter/X cookies only
    twitter_cookies = []
    for cookie in cookies:
        if isinstance(cookie, dict):
            domain = cookie.get('domain', '')
            if 'x.com' in domain or 'twitter.com' in domain:
                twitter_cookies.append(cookie)

    if not twitter_cookies:
        print("No Twitter/X cookies found in the file.")
        print("Make sure you:")
        print("  1. Are logged in to x.com in your browser")
        print("  2. Export cookies from x.com (not another site)")
        return

    print(f"Found {len(twitter_cookies)} Twitter/X cookies")

    # Save to Playwright storage state format
    user_data_dir = Path.home() / ".social_agent_codex/browser_session/"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    storage_state_file = user_data_dir / "storage_state.json"

    # Playwright storage state format
    storage_state = {
        "cookies": twitter_cookies,
        "origins": []
    }

    with open(storage_state_file, 'w') as f:
        json.dump(storage_state, f, indent=2)

    # Create session marker
    session_marker = user_data_dir / ".session_exists"
    session_marker.touch()

    print()
    print("="*70)
    print("✓ COOKIES IMPORTED SUCCESSFULLY!")
    print("="*70)
    print()
    print(f"Cookies saved to: {storage_state_file}")
    print()
    print("Next steps:")
    print("  1. Run: python social_agent.py")
    print("  2. The browser will open already logged in")
    print("  3. No manual login needed!")
    print()
    print("="*70)

if __name__ == "__main__":
    try:
        import_cookies_to_playwright()
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        sys.exit(0)
