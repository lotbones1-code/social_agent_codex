#!/bin/bash

echo "=========================================="
echo "  Social Agent Codex - Auto Setup & Run  "
echo "=========================================="
echo ""

# Check Python version
echo "[1/5] Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo "❌ Python not found. Please install Python 3.9+ first:"
    echo "   - Windows: https://www.python.org/downloads/"
    echo "   - Mac: brew install python3"
    echo "   - Linux: sudo apt install python3 python3-pip"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+')
echo "✅ Found $PYTHON_CMD (version $PYTHON_VERSION)"

# Install pip dependencies
echo ""
echo "[2/5] Installing Python dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt --quiet --disable-pip-version-check
if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi

# Install Playwright browsers
echo ""
echo "[3/5] Installing Playwright Chromium browser..."
$PYTHON_CMD -m playwright install chromium
if [ $? -eq 0 ]; then
    echo "✅ Playwright browser installed"
else
    echo "❌ Failed to install Playwright browser"
    exit 1
fi

# Check .env file
echo ""
echo "[4/5] Checking configuration..."
if [ -f ".env" ]; then
    echo "✅ Configuration file found (.env)"
else
    echo "❌ .env file not found!"
    exit 1
fi

# Run the bot
echo ""
echo "[5/5] Starting the bot..."
echo ""
echo "=========================================="
echo "  Bot is now running! Press Ctrl+C to stop"
echo "=========================================="
echo ""

$PYTHON_CMD social_agent.py
