#!/bin/bash
# Helper script to start Chrome with remote debugging enabled
# This allows run_in_my_chrome.py to connect to your existing Chrome session

set -e

# Default debugging port
PORT="${CHROME_DEBUG_PORT:-9222}"

# Profile directory
PROFILE_DIR="${CHROME_PROFILE_DIR:-$HOME/chrome-debug-profile}"

echo "=================================================="
echo "Starting Chrome with Remote Debugging"
echo "=================================================="
echo "Port: $PORT"
echo "Profile: $PROFILE_DIR"
echo ""
echo "After Chrome starts:"
echo "1. Log into x.com"
echo "2. In another terminal, run: python run_in_my_chrome.py"
echo "=================================================="
echo ""

# Detect OS and start Chrome accordingly
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if [ ! -f "$CHROME_PATH" ]; then
        echo "Error: Chrome not found at: $CHROME_PATH"
        exit 1
    fi

    "$CHROME_PATH" \
        --remote-debugging-port="$PORT" \
        --user-data-dir="$PROFILE_DIR" \
        --no-first-run \
        --no-default-browser-check \
        "https://x.com"

elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v google-chrome &> /dev/null; then
        CHROME_CMD="google-chrome"
    elif command -v chromium-browser &> /dev/null; then
        CHROME_CMD="chromium-browser"
    elif command -v chromium &> /dev/null; then
        CHROME_CMD="chromium"
    else
        echo "Error: Chrome/Chromium not found"
        echo "Please install google-chrome or chromium-browser"
        exit 1
    fi

    "$CHROME_CMD" \
        --remote-debugging-port="$PORT" \
        --user-data-dir="$PROFILE_DIR" \
        --no-first-run \
        --no-default-browser-check \
        "https://x.com"

else
    echo "Error: Unsupported OS: $OSTYPE"
    echo ""
    echo "On Windows, run this in Command Prompt:"
    echo "\"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" --remote-debugging-port=$PORT --user-data-dir=\"%USERPROFILE%\\chrome-debug-profile\" https://x.com"
    exit 1
fi
