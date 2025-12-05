#!/usr/bin/env python3
"""Quick test script to verify the bot is working."""
import os
import sys

# Check environment
print("=" * 50)
print("COMMANDOS BOT - CONFIGURATION CHECK")
print("=" * 50)

from dotenv import load_dotenv
load_dotenv()

# Check critical settings
openai_key = os.getenv("OPENAI_API_KEY", "")
referral_link = os.getenv("REFERRAL_LINK", "")
headless = os.getenv("HEADLESS", "true")

issues = []

if not openai_key or openai_key == "sk-your-api-key-here":
    issues.append("OPENAI_API_KEY not set or is placeholder")
    print("[X] OPENAI_API_KEY: NOT SET")
else:
    print("[OK] OPENAI_API_KEY: SET (hidden)")

if not referral_link or referral_link == "https://example.com/my-referral":
    issues.append("REFERRAL_LINK not set or is placeholder")
    print("[X] REFERRAL_LINK: NOT SET (using placeholder)")
else:
    print(f"[OK] REFERRAL_LINK: {referral_link}")

print(f"[INFO] HEADLESS: {headless}")

# Check auth file
from pathlib import Path
auth_file = Path(os.getenv("AUTH_FILE", "auth.json"))
profile_dir = Path(os.getenv("USER_DATA_DIR", ".pwprofile"))

if auth_file.exists():
    print(f"[OK] AUTH_FILE: {auth_file} exists")
else:
    print(f"[X] AUTH_FILE: {auth_file} does NOT exist")
    issues.append("No saved login - you need to login first")

if profile_dir.exists():
    print(f"[OK] USER_DATA_DIR: {profile_dir} exists")
else:
    print(f"[INFO] USER_DATA_DIR: {profile_dir} will be created")

print()
print("=" * 50)

if issues:
    print("ISSUES FOUND:")
    for issue in issues:
        print(f"  - {issue}")
    print()
    print("TO FIX:")
    print("1. Add to your .env file:")
    print("   OPENAI_API_KEY=sk-your-real-key")
    print("   REFERRAL_LINK=https://your-real-link.com")
    print()
    print("2. If no login exists, run with HEADLESS=false first:")
    print("   HEADLESS=false python social_agent.py")
    print("   Then login manually in the browser window")
    print()
else:
    print("ALL CHECKS PASSED!")
    print()
    print("Run the bot with:")
    print("  python social_agent.py")

print("=" * 50)

# Test OpenAI connection if key exists
if openai_key and openai_key != "sk-your-api-key-here":
    print()
    print("Testing OpenAI connection...")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": "Say 'Bot ready!' in 2 words"}],
            max_tokens=10
        )
        print(f"[OK] OpenAI API working: {response.choices[0].message.content}")
    except Exception as e:
        print(f"[X] OpenAI API error: {e}")
