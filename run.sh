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

# pick the most appropriate Python executable (prefer the venv)
PYTHON_BIN=""
if [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
elif [[ -x "venv/bin/python3" ]]; then
  PYTHON_BIN="venv/bin/python3"
elif [[ -x "venv/bin/python3.11" ]]; then
  PYTHON_BIN="venv/bin/python3.11"
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "Unable to locate a Python interpreter. Run 'make deps' first." >&2
    exit 1
  fi
fi

# ensure dependencies are installed (covers fresh checkouts where `make deps` was skipped)
if ! "${PYTHON_BIN}" - <<'PYCHECK' >/dev/null 2>&1
import importlib.util
playwright_spec = importlib.util.find_spec("playwright")
raise SystemExit(0 if playwright_spec is not None else 1)
PYCHECK
then
  echo "[run.sh] Playwright missing — installing python dependencies..." >&2
  "${PYTHON_BIN}" -m pip install -U pip wheel setuptools
  if [[ -f requirements.txt ]]; then
    "${PYTHON_BIN}" -m pip install -r requirements.txt
  else
    echo "[run.sh] requirements.txt not found; unable to install dependencies." >&2
    exit 1
  fi
fi

if ! "${PYTHON_BIN}" -m playwright install --check >/dev/null 2>&1; then
  echo "[run.sh] Ensuring Playwright browsers are installed..." >&2
  "${PYTHON_BIN}" -m playwright install chromium
fi

# start
nohup "${PYTHON_BIN}" social_agent.py >> logs/session.log 2>&1 &
sleep 4
tail -n 200 -f logs/session.log
