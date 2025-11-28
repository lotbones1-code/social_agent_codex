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

# Note: Bot will launch Chrome automatically (no need to pre-start)
echo "ℹ️  Bot will launch Chrome automatically when started"
echo "   You'll be prompted to log in to X if needed"
echo ""

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
