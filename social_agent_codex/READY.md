# social_agent_codex — macOS setup & run guide

## 1. One-time environment prep (macOS, zsh)
```zsh
cd /path/to/social_agent_codex
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
cp .env.replicate.example .env.replicate  # edit and add your tokens
```

Edit `.env.replicate` with at least:
```
REPLICATE_API_TOKEN=your_replicate_token
REPL_IMAGE_MODEL=stability-ai/sdxl
```
(Optional) add `OPENAI_API_KEY` and `REPLY_MODE=codex` to let the agent draft replies with gpt-5-codex.

## 2. Load secrets for each terminal session
```zsh
cd /path/to/social_agent_codex
source .venv/bin/activate
set -a
source .env.replicate
set +a
```

## 3. Verify Replicate SDXL availability (expects HTTP 200)
```zsh
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Token ${REPLICATE_API_TOKEN}" \
  https://api.replicate.com/v1/models/stability-ai/sdxl
```
A `200` response confirms the model endpoint is reachable.

## 4. Smoke-test the image generator (>=100 KB output)
```zsh
python generators/image_gen.py --topic "smoke test" --out media/images/check.png
ls -lh media/images/check.png
```
Confirm the file size is at least 100 KB.

## 5. Headless persistent run with logging
```zsh
mkdir -p logs
MEDIA_ATTACH_RATE=0.30 HEADLESS=1 STRICT_MODE=1 \
  nohup ./run_agent.sh >> logs/session.log 2>&1 &
```
The automation removes Chrome singleton locks before launch. Playwright runs headless but keeps using the persistent profile under `~/.pw-chrome-referral`.

## 6. Monitor activity
```zsh
tail -f logs/run.log
# or grep for proof-of-life markers
rg "Running generator|Generator output ready|Attached media|Replied to" logs/run.log
```
Log entries show generator runs, media attachments, and successful replies. Filters automatically relax once if no replies arrive for 5–8 minutes, then return to the defaults.

## 7. Manual resume & cleanup
- To rerun after edits: `pkill -f social_agent.py` (if needed) and rerun the nohup command above.
- To reset the Chrome profile entirely: `rm -rf ~/.pw-chrome-referral` (will require logging in again).
- To update dependencies later: `pip install -r requirements.txt --upgrade`.

## 8. Next run shortcut
After the initial setup, each new shell session only needs:
```zsh
cd /path/to/social_agent_codex
source .venv/bin/activate
set -a; source .env.replicate; set +a
MEDIA_ATTACH_RATE=0.30 HEADLESS=1 ./run_agent.sh
```
