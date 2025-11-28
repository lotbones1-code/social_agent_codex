#!/bin/bash
# Start Chrome with remote debugging for the bot

echo "🌐 Starting Chrome with remote debugging..."
echo ""
echo "Keep this window open while the bot runs!"
echo "The bot will connect to this Chrome instance."
echo ""

# Determine the Chrome executable path
CHROME=""

if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    if [ -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
        CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux" ]]; then
    # Linux - try multiple Chrome variants
    if command -v google-chrome &> /dev/null; then
        CHROME="google-chrome"
    elif command -v google-chrome-stable &> /dev/null; then
        CHROME="google-chrome-stable"
    elif command -v chromium &> /dev/null; then
        CHROME="chromium"
    elif command -v chromium-browser &> /dev/null; then
        CHROME="chromium-browser"
    fi
fi

if [ -z "$CHROME" ]; then
    echo "❌ Chrome/Chromium not found."
    echo ""
    echo "Please install Google Chrome or start it manually:"
    echo ""
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "  Mac:"
        echo "  \"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome\" --remote-debugging-port=9222 --user-data-dir=\"\$HOME/.real_x_profile\" &"
    elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux" ]]; then
        echo "  Linux:"
        echo "  google-chrome --remote-debugging-port=9222 --user-data-dir=\"\$HOME/.real_x_profile\" &"
    else
        echo "  Windows:"
        echo "  \"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" --remote-debugging-port=9222 --user-data-dir=\"%USERPROFILE%\\.real_x_profile\""
    fi
    echo ""
    exit 1
fi

# Start Chrome in background
"$CHROME" --remote-debugging-port=9222 --user-data-dir="$HOME/.real_x_profile" > /dev/null 2>&1 &
CHROME_PID=$!

sleep 2

# Check if it's still running
if ps -p $CHROME_PID > /dev/null 2>&1; then
    echo "✓ Chrome started successfully (PID: $CHROME_PID)"
else
    echo "✓ Chrome started on port 9222"
fi

echo "✓ User data directory: $HOME/.real_x_profile"
echo ""
echo "You can now run the bot with: ./start_bot.sh"
