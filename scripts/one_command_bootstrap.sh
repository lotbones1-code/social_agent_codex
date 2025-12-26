#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${SOCIAL_AGENT_REPO:-https://github.com/social-agent-codex/social_agent_codex.git}"
INSTALL_DIR="${SOCIAL_AGENT_HOME:-$HOME/social_agent_codex}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PROFILE_DIR="${SOCIAL_AGENT_PROFILE:-$HOME/.social_agent/browser}"
LAUNCHER_PATH="$HOME/.local/bin/run-bot"

command -v git >/dev/null 2>&1 || { echo "git is required" >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
command -v curl >/dev/null 2>&1 || { echo "curl is required" >&2; exit 1; }

mkdir -p "$INSTALL_DIR"

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  git -C "$INSTALL_DIR" fetch --depth 1 origin main || true
  if git -C "$INSTALL_DIR" rev-parse --verify origin/main >/dev/null 2>&1; then
    git -C "$INSTALL_DIR" reset --hard origin/main
  fi
fi

cd "$INSTALL_DIR"

# virtual env
if [[ ! -d "venv" ]]; then
  "$PYTHON_BIN" -m venv venv
fi
source venv/bin/activate

python -m pip install -U pip wheel setuptools
python -m pip install -r requirements.txt
python -m playwright install chromium

# ensure runtime directories
mkdir -p "$PROFILE_DIR" logs downloads auth

# quick import test (mocked)
SOCIAL_AGENT_MOCK_LOGIN=1 HEADLESS=0 USER_DATA_DIR="$PROFILE_DIR" python - <<'PY'
from social_agent import run_bot  # noqa: F401
print("bootstrap-ok")
PY

target_dir=$(dirname "$LAUNCHER_PATH")
mkdir -p "$target_dir"
cat > "$LAUNCHER_PATH" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
INSTALL_DIR="${SOCIAL_AGENT_HOME:-$HOME/social_agent_codex}"
PROFILE_DIR="${SOCIAL_AGENT_PROFILE:-$HOME/.social_agent/browser}"
cd "$INSTALL_DIR"
source venv/bin/activate
export HEADLESS=0
export USER_DATA_DIR="$PROFILE_DIR"
python social_agent.py
EOS
chmod +x "$LAUNCHER_PATH"

# start immediately once installed
"$LAUNCHER_PATH" &

cat <<'MSG'
------------------------------------------------------------
Setup complete. Your persistent launcher is available as `run-bot`.
The bot has been started in the background with a visible browser.
MSG
