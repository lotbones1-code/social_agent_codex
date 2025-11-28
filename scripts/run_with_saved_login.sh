#!/usr/bin/env bash
set -euo pipefail

# Simple launcher for people who already saved an X login in auth.json.
# - Keeps the browser headful by default so you can confirm the session.
# - Reuses the saved storage state; no username/password env vars needed.

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

AUTH_FILE=${AUTH_FILE:-$ROOT_DIR/auth.json}
HEADLESS=${HEADLESS:-0}
RUN=${RUN:-1}

export AUTH_FILE HEADLESS RUN

echo "[run_with_saved_login] Using AUTH_FILE=$AUTH_FILE (HEADLESS=$HEADLESS)"
bash ./run_agent.sh
