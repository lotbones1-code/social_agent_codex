#!/usr/bin/env python3
"""Quick test script to verify the bot is working."""
import os
import sys

# Check environment
print("=" * 60)
print("COMMANDOS BOT - FULL CONFIGURATION CHECK")
print("=" * 60)

from dotenv import load_dotenv
load_dotenv()

issues = []
warnings = []

# === Login Credentials ===
print("\n--- Login Settings ---")
username = os.getenv("USERNAME", "") or os.getenv("X_USERNAME", "")
password = os.getenv("PASSWORD", "") or os.getenv("X_PASSWORD", "")

if not username or username == "changeme@example.com":
    warnings.append("USERNAME not set - manual login required")
    print("[!] USERNAME: NOT SET (manual login required)")
else:
    print("[OK] USERNAME: SET (hidden)")

if not password or password == "super-secret-password":
    warnings.append("PASSWORD not set - manual login required")
    print("[!] PASSWORD: NOT SET (manual login required)")
else:
    print("[OK] PASSWORD: SET (hidden)")

# === OpenAI Settings ===
print("\n--- OpenAI Settings ---")
openai_key = os.getenv("OPENAI_API_KEY", "")

if not openai_key or openai_key == "sk-your-api-key-here":
    warnings.append("OPENAI_API_KEY not set - using template replies")
    print("[!] OPENAI_API_KEY: NOT SET (will use templates)")
else:
    print("[OK] OPENAI_API_KEY: SET (hidden)")

gpt_model = os.getenv("GPT_CAPTION_MODEL", "gpt-4o-mini")
print(f"[INFO] GPT_CAPTION_MODEL: {gpt_model}")

# === Reply Bot Settings ===
print("\n--- Reply Bot Settings ---")
referral_link = os.getenv("REFERRAL_LINK", "")
enable_replies = os.getenv("ENABLE_REPLIES", "true").lower() == "true"

if not referral_link or referral_link == "https://example.com/my-referral":
    issues.append("REFERRAL_LINK not set - replies won't include promotion")
    print("[X] REFERRAL_LINK: NOT SET (placeholder)")
else:
    print(f"[OK] REFERRAL_LINK: {referral_link}")

print(f"[INFO] ENABLE_REPLIES: {enable_replies}")
print(f"[INFO] MAX_REPLIES_PER_TOPIC: {os.getenv('MAX_REPLIES_PER_TOPIC', '3')}")

reply_templates = os.getenv("REPLY_TEMPLATES", "")
template_count = len(reply_templates.split("||")) if reply_templates else 0
print(f"[INFO] REPLY_TEMPLATES: {template_count} configured")

# === DM Bot Settings ===
print("\n--- DM Bot Settings ---")
enable_dms = os.getenv("ENABLE_DMS", "false").lower() == "true"
print(f"[INFO] ENABLE_DMS: {enable_dms}")

dm_templates = os.getenv("DM_TEMPLATES", "")
dm_template_count = len(dm_templates.split("||")) if dm_templates else 0
print(f"[INFO] DM_TEMPLATES: {dm_template_count} configured")
print(f"[INFO] DM_INTEREST_THRESHOLD: {os.getenv('DM_INTEREST_THRESHOLD', '3.2')}")

# === Browser Settings ===
print("\n--- Browser Settings ---")
headless = os.getenv("HEADLESS", "true")
print(f"[INFO] HEADLESS: {headless}")
print(f"[INFO] DEBUG: {os.getenv('DEBUG', 'false')}")

# === Auth/Profile ===
print("\n--- Auth & Profile ---")
from pathlib import Path
auth_file = Path(os.getenv("AUTH_FILE", "auth.json"))
profile_dir = Path(os.getenv("USER_DATA_DIR", ".pwprofile"))

if auth_file.exists():
    print(f"[OK] AUTH_FILE: {auth_file} exists")
else:
    print(f"[!] AUTH_FILE: {auth_file} does NOT exist (will create on first login)")

if profile_dir.exists():
    print(f"[OK] USER_DATA_DIR: {profile_dir} exists")
else:
    print(f"[INFO] USER_DATA_DIR: {profile_dir} will be created")

# === Search Topics ===
print("\n--- Search Configuration ---")
search_topics = os.getenv("SEARCH_TOPICS", "ai, automation")
topics = [t.strip() for t in search_topics.replace("||", ",").split(",") if t.strip()]
print(f"[INFO] SEARCH_TOPICS: {len(topics)} configured")
for i, topic in enumerate(topics[:5], 1):
    print(f"       {i}. {topic}")
if len(topics) > 5:
    print(f"       ... and {len(topics) - 5} more")

# === Timing ===
print("\n--- Timing Settings ---")
print(f"[INFO] LOOP_DELAY_SECONDS: {os.getenv('LOOP_DELAY_SECONDS', '900')}")
print(f"[INFO] ACTION_DELAY_MIN: {os.getenv('ACTION_DELAY_MIN', '6')}")
print(f"[INFO] ACTION_DELAY_MAX: {os.getenv('ACTION_DELAY_MAX', '16')}")

# === Summary ===
print()
print("=" * 60)

if issues:
    print("CRITICAL ISSUES:")
    for issue in issues:
        print(f"  [X] {issue}")
    print()

if warnings:
    print("WARNINGS (bot will still run):")
    for warning in warnings:
        print(f"  [!] {warning}")
    print()

if not issues:
    print("STATUS: READY TO RUN")
    print()
    print("To start the bot:")
    print("  python social_agent.py")
    print()
    if not username or username == "changeme@example.com":
        print("NOTE: First run with HEADLESS=false to login manually:")
        print("  HEADLESS=false python social_agent.py")
else:
    print("STATUS: FIX ISSUES BEFORE RUNNING")
    print()
    print("Update your .env file with real values.")

print("=" * 60)

# Test OpenAI connection if key exists
if openai_key and openai_key != "sk-your-api-key-here":
    print()
    print("Testing OpenAI connection...")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        response = client.chat.completions.create(
            model=gpt_model,
            messages=[{"role": "user", "content": "Say 'Bot ready!' in 2 words"}],
            max_tokens=10
        )
        print(f"[OK] OpenAI API working: {response.choices[0].message.content}")
    except Exception as e:
        print(f"[X] OpenAI API error: {e}")
