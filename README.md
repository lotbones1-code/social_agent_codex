# Social Agent Codex

This repository hosts the automation agent for posting via Playwright and Chrome.

## How to run
- `bash ./run.sh`
- `make restart`

## X login setup
1. Export your credentials before launching the agent:
   ```bash
   export X_USERNAME="your_handle"
   export X_PASSWORD="your_password"
   export X_ALT_ID="email_or_phone_optional"  # optional; falls back to X_EMAIL then X_USERNAME
   ```
   `X_ALT_ID` is used when X asks for an additional identity prompt. If it is unset, the helper will fall back to `X_EMAIL` and finally `X_USERNAME`.
2. Validate the login flow independently with `make x-login-test`. The command opens the Playwright browser, signs in, and exits once the composer or profile is visible.

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session.
This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
