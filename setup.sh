#!/bin/bash

echo "======================================================================"
echo "SOCIAL AGENT SETUP SCRIPT"
echo "======================================================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.template .env
    echo "✓ .env file created"
else
    echo "✓ .env file already exists"
fi

# Verify FORCE_MANUAL_LOGIN is set
if grep -q "^FORCE_MANUAL_LOGIN=true" .env; then
    echo "✓ FORCE_MANUAL_LOGIN is enabled"
else
    echo "⚠ FORCE_MANUAL_LOGIN is not set to true"
    echo "  Setting it now..."
    if grep -q "^FORCE_MANUAL_LOGIN=" .env; then
        sed -i 's/^FORCE_MANUAL_LOGIN=.*/FORCE_MANUAL_LOGIN=true/' .env
    else
        echo "FORCE_MANUAL_LOGIN=true" >> .env
    fi
    echo "✓ FORCE_MANUAL_LOGIN set to true"
fi

# Check Python
echo ""
echo "Checking Python installation..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ $PYTHON_VERSION found"
else
    echo "✗ Python 3 not found"
    exit 1
fi

# Check Playwright
echo ""
echo "Checking Playwright installation..."
if python3 -c "import playwright" 2>/dev/null; then
    echo "✓ Playwright Python package is installed"
else
    echo "✗ Playwright Python package NOT installed"
    echo ""
    echo "Install with:"
    echo "  pip install playwright python-dotenv"
    exit 1
fi

# Check Playwright browsers
echo ""
echo "Checking Playwright browsers..."
if playwright --help &> /dev/null; then
    echo "✓ Playwright CLI is available"
    echo ""
    echo "Checking if Chromium is installed..."
    # This will show if browsers are installed
    playwright install --dry-run chromium 2>&1 | grep -q "is already installed" && echo "✓ Chromium is already installed" || {
        echo "⚠ Chromium may not be installed"
        echo ""
        echo "Installing Chromium browser..."
        playwright install chromium
    }
else
    echo "⚠ Playwright CLI not found in PATH"
    echo "  Installing browsers anyway..."
    python3 -m playwright install chromium
fi

echo ""
echo "======================================================================"
echo "SETUP COMPLETE!"
echo "======================================================================"
echo ""
echo "Configuration summary:"
echo "  .env file: exists"
echo "  FORCE_MANUAL_LOGIN: true"
echo "  Python: installed"
echo "  Playwright: installed"
echo "  Chromium: installed"
echo ""
echo "Next steps:"
echo "  1. Run basic browser test:"
echo "     python3 test_browser_basic.py"
echo ""
echo "  2. If that works, test login:"
echo "     python3 test_login.py"
echo ""
echo "  3. If login works, run the agent:"
echo "     python3 social_agent.py"
echo ""
echo "======================================================================"
