#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -f .env.replicate ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.replicate
  set +a
fi

export HEADLESS="${HEADLESS:-1}"

python3 --version
echo "HEADLESS=${HEADLESS}  MEDIA_ATTACH_RATE=${MEDIA_ATTACH_RATE:-0.30}"
python3 generators/image_gen.py --topic "smoke test" --out media/images/check.png || true
python3 social_agent.py
