#!/bin/bash
# Simple script to start Chrome with remote debugging for the bot

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9223 \
    --user-data-dir="$HOME/.chrome-debug-dub" \
    --no-first-run \
    --no-default-browser-check \
    > /dev/null 2>&1 &

echo "✅ Chrome started in background on port 9223"
echo "📁 Profile: ~/.chrome-debug-dub"
echo ""
echo "Now run the bot: bash run_agent.sh"

