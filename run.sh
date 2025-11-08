#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# venv
if [[ -d "venv" ]]; then source venv/bin/activate; fi

# persistent profile for this repo
export PW_PROFILE_DIR="$PWD/.pwprofile_live"
mkdir -p "$PW_PROFILE_DIR" logs

# hard-close anything that could hold the profile
pkill -f 'social_agent.py' || true
osascript -e 'quit app "Google Chrome"' || true
pkill -9 -f 'Google Chrome Helper' || true
pkill -9 -f 'Chromium' || true
pkill -9 -f 'chrome(--type)?' || true
pkill -9 -f 'crashpad' || true
pkill -9 -f 'playwright' || true
rm -rf "$PW_PROFILE_DIR/Singlet*" 2>/dev/null || true
rm -rf "$HOME/Library/Application Support/Chromium/Singleton*" 2>/dev/null || true
rm -rf "$HOME/.config/chromium/Singleton*" 2>/dev/null || true

# start
nohup venv/bin/python3.11 social_agent.py >> logs/session.log 2>&1 &
sleep 4
tail -n 200 -f logs/session.log
