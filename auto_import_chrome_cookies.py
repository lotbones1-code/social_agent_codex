#!/usr/bin/env python3
"""
Automatically extract Twitter cookies from Chrome and import them.
No manual steps required.
"""

import os
import json
import sqlite3
import shutil
from pathlib import Path

def find_chrome_cookies():
    """Find Chrome's cookies database on Mac."""
    possible_paths = [
        Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies",
        Path.home() / "Library/Application Support/Google/Chrome/Profile 1/Cookies",
        Path.home() / "Library/Application Support/Chromium/Default/Cookies",
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None

def extract_twitter_cookies():
    """Extract Twitter cookies from Chrome's database."""
    chrome_cookies = find_chrome_cookies()

    if not chrome_cookies:
        print("Error: Could not find Chrome cookies database.")
        print("Make sure Chrome is installed and you're logged into x.com")
        return None

    print(f"Found Chrome cookies at: {chrome_cookies}")

    # Copy to temp location (Chrome locks the file)
    temp_cookies = "/tmp/chrome_cookies_copy.db"
    try:
        shutil.copy2(chrome_cookies, temp_cookies)
    except Exception as e:
        print(f"Error copying cookies: {e}")
        print("Close Chrome completely and try again.")
        return None

    # Read cookies from database
    try:
        conn = sqlite3.connect(temp_cookies)
        cursor = conn.cursor()

        # Query Twitter cookies
        cursor.execute("""
            SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
            FROM cookies
            WHERE host_key LIKE '%x.com%' OR host_key LIKE '%twitter.com%'
        """)

        cookies = []
        for row in cursor.fetchall():
            name, value, domain, path, expires, secure, httponly = row

            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "expires": expires,
                "secure": bool(secure),
                "httpOnly": bool(httponly),
            }
            cookies.append(cookie)

        conn.close()
        os.remove(temp_cookies)

        return cookies

    except Exception as e:
        print(f"Error reading cookies: {e}")
        return None

def save_to_playwright():
    """Save cookies to Playwright format."""
    cookies = extract_twitter_cookies()

    if not cookies:
        print("\nNo Twitter cookies found.")
        print("Make sure you're logged in to x.com in Chrome.")
        return False

    print(f"\nFound {len(cookies)} Twitter cookies!")

    # Save to Playwright storage state
    user_data_dir = Path.home() / ".social_agent_codex/browser_session/"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    storage_state = {
        "cookies": cookies,
        "origins": []
    }

    storage_file = user_data_dir / "storage_state.json"
    with open(storage_file, 'w') as f:
        json.dump(storage_state, f, indent=2)

    # Create session marker
    session_marker = user_data_dir / ".session_exists"
    session_marker.touch()

    print("\n" + "="*70)
    print("✓ COOKIES IMPORTED SUCCESSFULLY!")
    print("="*70)
    print()
    print("Now run: python social_agent.py")
    print()
    return True

if __name__ == "__main__":
    print("="*70)
    print("AUTOMATIC CHROME COOKIE IMPORTER")
    print("="*70)
    print()
    print("This will automatically extract your Twitter login from Chrome.")
    print("Make sure you're logged in to x.com in Chrome first.")
    print()

    # Check if Chrome is running
    import subprocess
    try:
        result = subprocess.run(
            ["pgrep", "-i", "chrome"],
            capture_output=True,
            text=True
        )
        if result.stdout.strip():
            print("⚠️  WARNING: Chrome is running!")
            print("For best results, close Chrome completely, then run this again.")
            print()
            response = input("Continue anyway? (y/n): ").strip().lower()
            if response != 'y':
                print("Cancelled. Close Chrome and run again.")
                exit(0)
    except:
        pass

    print()
    if save_to_playwright():
        print("="*70)
        print("Ready to go! Run: python social_agent.py")
        print("="*70)
    else:
        print()
        print("Failed to import cookies.")
        print("Make sure you're logged in to x.com in Chrome.")
