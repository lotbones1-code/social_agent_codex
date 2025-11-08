#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
VENV_DIR="$REPO_DIR/.venv"
PYTHON_BIN="${PYTHON:-python3}"

if [ "${RUN:-}" != "1" ]; then
  echo "Refusing to start; set RUN=1"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$REPO_DIR/requirements.txt"
python -m pip install playwright==1.49.0
python -m playwright install chromium

PROFILE_DIR="${PW_PROFILE_DIR:-$REPO_DIR/.pwprofile_live}"
case "$PROFILE_DIR" in
  /*) ;;
  *) PROFILE_DIR="$REPO_DIR/$PROFILE_DIR" ;;
esac

mkdir -p "$(dirname "$PROFILE_DIR")"
mkdir -p "$PROFILE_DIR"

"$REPO_DIR/scripts/kill_profile.sh" "$PROFILE_DIR" || true

ln -sfn "$PROFILE_DIR" "$HOME/.pw-chrome-referral"

mkdir -p "$REPO_DIR/logs"
touch "$REPO_DIR/logs/session.log"

nohup env PW_PROFILE_DIR="$PROFILE_DIR" "$VENV_DIR/bin/python" "$REPO_DIR/social_agent.py" >> "$REPO_DIR/logs/session.log" 2>&1 &
APP_PID=$!

echo "Started social_agent.py with PID $APP_PID using profile $PROFILE_DIR"
echo "$APP_PID" > "$REPO_DIR/.agent.pid"

sleep 2
echo "Last 160 log lines:"
tail -n 160 "$REPO_DIR/logs/session.log"
