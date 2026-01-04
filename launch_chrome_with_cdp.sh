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

# Launch Chrome with remote debugging on port 9223 (separate from other bots on 9222)
# Using a custom user data directory so it doesn't interfere with your main Chrome or other bots
USER_DATA_DIR="$HOME/.chrome-debug-dub"
CDP_PORT="${CDP_PORT:-9223}"

echo "🚀 Launching Chrome with remote debugging on port $CDP_PORT..."
echo "📁 User data directory: $USER_DATA_DIR"
echo "🔌 CDP port: $CDP_PORT (separate from other bots)"
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
    --remote-debugging-port="$CDP_PORT" \
    --user-data-dir="$USER_DATA_DIR" \
    --no-first-run \
    --no-default-browser-check

