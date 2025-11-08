# Social Agent Codex

This repository hosts the automation agent for posting via Playwright and Chrome.

## How to run
- `bash ./run.sh`
- `make restart`

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session. This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
