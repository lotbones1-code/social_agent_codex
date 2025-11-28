#!/bin/bash
# One-time setup script for the X Influencer Bot

echo "=========================================="
echo "🚀 X Influencer Bot - Setup"
echo "=========================================="
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv || {
        echo "❌ Failed to create virtual environment"
        exit 1
    }
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate || {
    echo "❌ Failed to activate virtual environment"
    exit 1
}

# Upgrade pip
echo "📦 Upgrading pip..."
python -m pip install --upgrade pip -q

# Install dependencies
echo "📥 Installing dependencies (this may take a minute)..."
pip install -r requirements.txt -q || {
    echo "❌ Failed to install dependencies"
    exit 1
}
echo "✓ Dependencies installed"

# Install Playwright browsers
echo "🌐 Installing Playwright Chromium..."
playwright install chromium || {
    echo "⚠️  Playwright install had issues, but continuing..."
}
echo "✓ Playwright installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "✓ Created .env from template"
    else
        echo "⚠️  .env.example not found, creating minimal .env"
        cat > .env << 'EOF'
# Minimal configuration
OPENAI_API_KEY=sk-your-openai-api-key-here
HEADLESS=false
DRY_RUN=true
SEARCH_TOPICS=ai,automation,technology
EOF
    fi
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your OpenAI API key (optional)"
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
echo "1. (Optional) Edit .env and add your OPENAI_API_KEY"
echo "2. Start Chrome: ./start_chrome.sh"
echo "3. Run the bot: ./start_bot.sh"
echo ""
echo "Note: First run defaults to DRY_RUN=true (safe mode)"
echo ""
