#!/usr/bin/env python3
"""
Simple test script to verify the bot setup is correct.
Run this before starting the bot to check for common issues.
"""

import sys
from pathlib import Path

def check_python_version():
    """Check Python version is 3.11+"""
    if sys.version_info < (3, 11):
        print("❌ Python 3.11+ required (you have {}.{})".format(
            sys.version_info.major, sys.version_info.minor
        ))
        return False
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True

def check_imports():
    """Check all required packages are installed"""
    missing = []

    packages = [
        ('playwright', 'playwright'),
        ('dotenv', 'python-dotenv'),
        ('openai', 'openai'),
        ('requests', 'requests'),
    ]

    for module, package in packages:
        try:
            __import__(module)
            print(f"✓ {package}")
        except ImportError:
            print(f"❌ {package} not installed")
            missing.append(package)

    return len(missing) == 0

def check_files():
    """Check required files exist"""
    required = [
        'social_agent.py',
        'bot/config.py',
        'bot/poster.py',
        'bot/captioner.py',
        'bot/browser.py',
        'requirements.txt',
    ]

    missing = []
    for file in required:
        if Path(file).exists():
            print(f"✓ {file}")
        else:
            print(f"❌ {file} missing")
            missing.append(file)

    return len(missing) == 0

def check_env():
    """Check .env file"""
    if not Path('.env').exists():
        print("⚠️  .env file not found (will be created from .env.example)")
        return True

    print("✓ .env exists")

    # Check for placeholder API key
    with open('.env', 'r') as f:
        content = f.read()
        if 'sk-your-openai-api-key-here' in content:
            print("⚠️  OpenAI API key is placeholder (AI captions disabled)")
        else:
            print("✓ OpenAI API key configured")

    return True

def main():
    print("=" * 50)
    print("🔍 Bot Setup Verification")
    print("=" * 50)
    print()

    checks = [
        ("Python version", check_python_version),
        ("Required packages", check_imports),
        ("Required files", check_files),
        ("Configuration", check_env),
    ]

    all_passed = True
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        if not check_func():
            all_passed = False

    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All checks passed! You're ready to run the bot.")
        print("\nNext steps:")
        print("1. ./start_chrome.sh (in one terminal)")
        print("2. ./start_bot.sh (in another terminal)")
    else:
        print("❌ Some checks failed. Run ./setup.sh to fix issues.")
    print("=" * 50)

    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
