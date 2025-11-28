#!/bin/bash
# Start the X Influencer Bot with pre-flight checks

set -e

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

# Check if Chrome is running on port 9222
echo "🔍 Checking if Chrome is running on port 9222..."
if ! lsof -i:9222 >/dev/null 2>&1 && ! netstat -an 2>/dev/null | grep -q ":9222.*LISTEN"; then
    echo "❌ Chrome is not running with remote debugging!"
    echo ""
    echo "Please start Chrome first:"
    echo "   ./start_chrome.sh"
    echo ""
    echo "Or manually:"
    echo "   google-chrome --remote-debugging-port=9222 --user-data-dir=\$HOME/.real_x_profile"
    echo ""
    exit 1
fi
echo "✓ Chrome is running on port 9222"

# Check for OPENAI_API_KEY
if grep -q "sk-your-openai-api-key-here" .env 2>/dev/null; then
    echo "⚠️  OpenAI API key not set in .env"
    echo "   The bot will use simple caption templates instead of AI-generated captions."
    echo "   To enable AI captions, edit .env and add your OpenAI API key."
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
