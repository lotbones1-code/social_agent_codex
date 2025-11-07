#!/usr/bin/env bash
set -euo pipefail
python --version
echo "HEADLESS=${HEADLESS:-1}  MEDIA_ATTACH_RATE=${MEDIA_ATTACH_RATE:-0.30}"
python generators/image_gen.py --topic "smoke test" --out media/images/check.png || true
python social_agent.py
