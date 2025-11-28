#!/bin/bash
# Start Chrome with remote debugging for the bot

echo "🌐 Starting Chrome with remote debugging..."
echo ""
echo "Keep this window open while the bot runs!"
echo "The bot will connect to this Chrome instance."
echo ""

# Determine the Chrome executable path
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    if command -v google-chrome &> /dev/null; then
        CHROME="google-chrome"
    elif command -v chromium &> /dev/null; then
        CHROME="chromium"
    elif command -v chromium-browser &> /dev/null; then
        CHROME="chromium-browser"
    else
        echo "❌ Chrome/Chromium not found. Please install Google Chrome."
        exit 1
    fi
else
    echo "❌ Unsupported OS. Please start Chrome manually with:"
    echo "   chrome.exe --remote-debugging-port=9222 --user-data-dir=%USERPROFILE%\\.real_x_profile"
    exit 1
fi

# Start Chrome
"$CHROME" --remote-debugging-port=9222 --user-data-dir="$HOME/.real_x_profile" &

echo "✓ Chrome started on port 9222"
echo "✓ User data directory: $HOME/.real_x_profile"
echo ""
echo "You can now run the bot with: ./start_bot.sh"
