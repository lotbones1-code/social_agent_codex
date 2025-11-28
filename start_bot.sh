#!/bin/bash
# Start the X Influencer Bot with pre-flight checks

echo "=========================================="
echo "🤖 X Influencer Bot - Starting"
echo "=========================================="
echo ""

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Run ./setup.sh first!"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from template..."
    cp .env.example .env
    echo "✓ Created .env - you may want to edit it and add your OPENAI_API_KEY"
    echo ""
fi

# Check if Chrome is running on port 9222 (simplified check)
echo "🔍 Checking if Chrome is running on port 9222..."
CHECK_CHROME=false
if command -v lsof &> /dev/null; then
    lsof -i:9222 >/dev/null 2>&1 && CHECK_CHROME=true
elif command -v netstat &> /dev/null; then
    netstat -an 2>/dev/null | grep -q ":9222.*LISTEN" && CHECK_CHROME=true
elif command -v ss &> /dev/null; then
    ss -ln 2>/dev/null | grep -q ":9222" && CHECK_CHROME=true
else
    # If no port checking tool, try to connect
    (echo > /dev/tcp/localhost/9222) >/dev/null 2>&1 && CHECK_CHROME=true
fi

if [ "$CHECK_CHROME" = false ]; then
    echo "⚠️  Warning: Could not detect Chrome on port 9222"
    echo "   If Chrome is not running, the bot will fail to connect."
    echo ""
    echo "Start Chrome with:"
    echo "   ./start_chrome.sh"
    echo ""
    echo "Or manually (Mac/Linux):"
    echo "   google-chrome --remote-debugging-port=9222 --user-data-dir=\$HOME/.real_x_profile"
    echo ""
    read -p "Continue anyway? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "✓ Chrome appears to be running on port 9222"
fi

# Check for OPENAI_API_KEY
if grep -q "sk-your-openai-api-key-here" .env 2>/dev/null; then
    echo "⚠️  OpenAI API key not set in .env"
    echo "   The bot will use simple caption templates."
    echo ""
fi

# Check dry-run mode
if grep -q "^DRY_RUN=true" .env 2>/dev/null || [ "$DRY_RUN" = "true" ]; then
    echo "🔍 DRY-RUN MODE ENABLED - No posts will be submitted!"
    echo ""
fi

echo "🚀 Starting bot..."
echo "=========================================="
echo ""

# Run the bot
python social_agent.py

echo ""
echo "=========================================="
echo "Bot stopped."
echo "=========================================="
