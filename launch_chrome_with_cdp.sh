#!/bin/bash
# Script to launch Chrome with remote debugging enabled
# This allows the social_agent script to connect to your existing browser

# Find Chrome executable (adjust if needed)
if [ -d "/Applications/Google Chrome.app" ]; then
    CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif [ -d "/Applications/Chromium.app" ]; then
    CHROME="/Applications/Chromium.app/Contents/MacOS/Chromium"
else
    echo "Chrome not found. Please specify the path to Chrome."
    exit 1
fi

# Launch Chrome with remote debugging on port 9222
# Using a custom user data directory so it doesn't interfere with your main Chrome
USER_DATA_DIR="$HOME/.chrome-debug"

echo "🚀 Launching Chrome with remote debugging on port 9222..."
echo "📁 User data directory: $USER_DATA_DIR"
echo ""
echo "✅ Once Chrome opens:"
echo "   1. Log into X/Twitter in the Chrome window"
echo "   2. Keep this terminal window open"
echo "   3. In another terminal, run: ./run_agent.sh"
echo ""
echo "The script will connect to THIS browser window (no new window will open)."
echo ""
echo "Press Ctrl+C to stop this script (which will close Chrome)."
echo ""

"$CHROME" \
    --remote-debugging-port=9222 \
    --user-data-dir="$USER_DATA_DIR" \
    --no-first-run \
    --no-default-browser-check

