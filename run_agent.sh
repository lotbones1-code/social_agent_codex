#!/usr/bin/env bash
set -euo pipefail
python3 --version

export HEADLESS="${HEADLESS:-0}"
export MEDIA_ATTACH_RATE="${MEDIA_ATTACH_RATE:-0.30}"
export STRICT_MODE="${STRICT_MODE:-0}"

echo "HEADLESS=${HEADLESS}  MEDIA_ATTACH_RATE=${MEDIA_ATTACH_RATE}  STRICT_MODE=${STRICT_MODE}"
python3 generators/image_gen.py --topic "smoke test" --out media/images/check.png || true
python3 social_agent.py
