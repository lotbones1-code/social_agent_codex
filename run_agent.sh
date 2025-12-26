#!/usr/bin/env bash
set -euo pipefail

# Activate virtual environment if it exists
if [ -d "venv311/bin" ]; then
    source venv311/bin/activate
fi

# API credentials
export OPENAI_API_KEY="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"

# Notion credentials (DISABLED - bot works without Notion)
# export NOTION_API_KEY="ntn_296794666657aHdsSarqjU764mMM1b0aQeIAFkX2uYvE3E6"
# export NOTION_DATABASE_ID="2d36e908b8a180a992abd323fddaf04f"

python3 --version
echo "HEADLESS=${HEADLESS:-1}  MEDIA_ATTACH_RATE=${MEDIA_ATTACH_RATE:-0.30}"
python3 generators/image_gen.py --topic "smoke test" --out media/images/check.png || true
python3 social_agent.py
