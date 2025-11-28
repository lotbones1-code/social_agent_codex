#!/usr/bin/env bash
#
# Production launcher for X Influencer Bot
# Uses real Chrome with persistent profile for maximum reliability
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python3"
CHROME_PROFILE="${SCRIPT_DIR}/chrome_profile"
CDP_PORT="${CDP_PORT:-9222}"
HEADLESS="${HEADLESS:-0}"

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_venv() {
    if [[ ! -f "$VENV_PYTHON" ]]; then
        log_error "Python venv not found at: $VENV_PYTHON"
        log_info "Run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
    log_info "Found Python venv: $VENV_PYTHON"
}

check_chrome() {
    # Detect Chrome path based on OS
    local chrome_path=""

    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        chrome_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        if command -v google-chrome &> /dev/null; then
            chrome_path="google-chrome"
        elif command -v chromium-browser &> /dev/null; then
            chrome_path="chromium-browser"
        fi
    fi

    if [[ -z "$chrome_path" ]]; then
        log_warn "Chrome not detected. Make sure it's installed."
        log_warn "The bot will try to use Playwright's Chromium as fallback."
        return 1
    fi

    log_info "Chrome detected: $chrome_path"
    export CHROME_PATH="$chrome_path"
    return 0
}

start_chrome_cdp() {
    # Check if Chrome is already running on CDP port
    if lsof -Pi :$CDP_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
        log_info "Chrome already running on port $CDP_PORT"
        return 0
    fi

    if [[ -z "${CHROME_PATH:-}" ]]; then
        log_warn "Chrome path not set, skipping CDP launch"
        return 1
    fi

    log_info "Starting Chrome with CDP on port $CDP_PORT..."

    # Create profile directory
    mkdir -p "$CHROME_PROFILE"

    # Launch Chrome in background
    if [[ "$OSTYPE" == "darwin"* ]]; then
        "$CHROME_PATH" \
            --remote-debugging-port=$CDP_PORT \
            --user-data-dir="$CHROME_PROFILE" \
            --no-first-run \
            --no-default-browser-check \
            --disable-background-networking \
            --disable-sync \
            > /dev/null 2>&1 &
    else
        "$CHROME_PATH" \
            --remote-debugging-port=$CDP_PORT \
            --user-data-dir="$CHROME_PROFILE" \
            --no-first-run \
            --no-default-browser-check \
            --disable-background-networking \
            --disable-sync \
            > /dev/null 2>&1 &
    fi

    # Wait for Chrome to start
    log_info "Waiting for Chrome to start..."
    for i in {1..10}; do
        if lsof -Pi :$CDP_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
            log_info "Chrome started successfully"
            return 0
        fi
        sleep 1
    done

    log_warn "Chrome may not have started on port $CDP_PORT"
    return 1
}

check_openai_key() {
    if [[ -f "${SCRIPT_DIR}/.env" ]]; then
        source "${SCRIPT_DIR}/.env"
    fi

    if [[ -z "${OPENAI_API_KEY:-}" ]]; then
        log_warn "OPENAI_API_KEY not set in .env file"
        log_warn "Bot will use fallback captions (no AI generation)"
    else
        log_info "OpenAI API key found"
    fi
}

run_bot() {
    log_info "========================================"
    log_info "  X Influencer Bot - Production Mode"
    log_info "========================================"

    # Pre-flight checks
    check_venv
    check_openai_key

    # Try to start Chrome CDP
    if check_chrome; then
        start_chrome_cdp || log_warn "CDP not available, bot will use fallback"
    fi

    log_info "Starting bot..."
    log_info "Config file: ${SCRIPT_DIR}/config.yaml"
    log_info "HEADLESS mode: $HEADLESS"
    log_info ""

    # Run the bot
    cd "$SCRIPT_DIR"

    if [[ "$HEADLESS" == "1" ]]; then
        export HEADLESS=1
    else
        export HEADLESS=0
    fi

    # Run with full error output
    "$VENV_PYTHON" social_agent.py 2>&1 | tee -a logs/bot.log
}

cleanup() {
    log_info "Cleaning up..."
    # Don't kill Chrome - user might want to keep it running
    log_info "Chrome left running on port $CDP_PORT (use 'pkill -f chrome-debug' to stop)"
}

trap cleanup EXIT

# Create logs directory
mkdir -p "${SCRIPT_DIR}/logs"
mkdir -p "${SCRIPT_DIR}/downloads"

# Run the bot
run_bot
