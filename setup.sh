#!/bin/bash
# One-time setup script for the X Influencer Bot

set -e

echo "=========================================="
echo "🚀 X Influencer Bot - Setup"
echo "=========================================="
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✓ Dependencies installed"

# Install Playwright browsers
echo "🌐 Installing Playwright Chromium..."
playwright install chromium
echo "✓ Playwright installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file..."
    cp .env.example .env
    echo "✓ Created .env (please edit it and add your OPENAI_API_KEY)"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your OpenAI API key!"
    echo "   Open .env in a text editor and replace 'sk-your-openai-api-key-here'"
else
    echo "✓ .env file already exists"
fi

# Create necessary directories
mkdir -p downloads
echo "✓ Created downloads directory"

echo ""
echo "=========================================="
echo "✅ Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Edit .env and add your OPENAI_API_KEY (optional but recommended)"
echo "2. Start Chrome with: ./start_chrome.sh"
echo "3. Run the bot with: ./start_bot.sh"
echo ""
echo "For testing without posting: DRY_RUN=true ./start_bot.sh"
echo ""
