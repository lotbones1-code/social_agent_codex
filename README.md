# Social Agent Codex

This repository hosts the automation agent for posting via Playwright and Chrome.

## Requirements
- Python **3.11.***
- Playwright **1.49.0** (installed via the provided Make target)

## Setup & usage
1. Install dependencies and browsers:
   ```bash
   make deps
   ```
2. (Optional) Stop any lingering Chrome/Chromium sessions that point at your Playwright profile:
   ```bash
   make kill
   ```
3. Export your X credentials before launching the agent **or** place them in a `.env` file in the project root:
   ```bash
   export X_USERNAME="your_handle"
   export X_PASSWORD="your_password"
   export X_ALT_ID="email_or_phone_optional"  # optional; falls back to X_EMAIL then X_USERNAME
   ```
   `X_ALT_ID` is used when X asks for an additional identity prompt. If it is unset, the helper will fall back to `X_EMAIL` and finally `X_USERNAME`. When using a `.env` file, be sure to set `X_USERNAME` and `X_PASSWORD`; the automation will raise a helpful error if either is missing.
4. Validate the login flow independently (headful) with:
   ```bash
   make x-login-test
   ```
5. Start the agent only when you are ready to post:
   ```bash
   RUN=1 make start
   ```
   You can also launch directly with the script:
   ```bash
   RUN=1 bash ./run.sh
   ```

## AI-Powered Features

This agent now supports AI-powered content generation for higher quality, more natural interactions.

### Supported AI Providers

**Choose your preferred AI provider:**

#### OpenAI (ChatGPT) - Recommended
- Use your existing ChatGPT API credits
- Models: `gpt-4o`, `gpt-4o-mini` (cheaper, faster), `gpt-4-turbo`
- Very affordable: ~$0.0001-0.0003 per reply with `gpt-4o-mini`
- Get API key at: https://platform.openai.com/api-keys

#### Anthropic (Claude)
- Alternative if you prefer Claude
- Models: `claude-3-5-sonnet-20241022`, `claude-3-haiku-20240307`
- Cost: ~$0.001-0.003 per reply
- Get API key at: https://console.anthropic.com/settings/keys

### AI Reply Generation
- **Enabled by default** - Set `ENABLE_AI_REPLIES=true` in your `.env`
- Choose provider with `AI_PROVIDER=openai` or `AI_PROVIDER=anthropic`
- Generates contextual, natural-sounding replies based on tweet content
- Falls back to template-based replies if AI is unavailable
- Configurable model via `AI_MODEL`

### Original Post Creation
- **Enable with** `ENABLE_POSTING=true` in your `.env`
- Creates AI-generated original posts/tweets each cycle
- Configure posts per cycle with `POSTS_PER_CYCLE` (default: 2)
- Set topics with `POST_TOPICS` (uses `SEARCH_TOPICS` by default)

### Configuration Examples

**Option 1: OpenAI (Recommended - use your ChatGPT credits)**
```bash
# AI Configuration
AI_PROVIDER=openai
OPENAI_API_KEY=sk-proj-your-key-here
AI_MODEL=gpt-4o-mini
ENABLE_AI_REPLIES=true

# Posting Configuration
ENABLE_POSTING=true
POSTS_PER_CYCLE=2
POST_TOPICS="AI automation||growth hacking||product launches"

# Activity Settings
LOOP_DELAY_SECONDS=300
MAX_REPLIES_PER_TOPIC=10
```

**Option 2: Anthropic (Claude)**
```bash
# AI Configuration
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-your-key-here
AI_MODEL=claude-3-5-sonnet-20241022
ENABLE_AI_REPLIES=true

# Posting and Activity Settings (same as above)
```

**Option 3: No AI (Free - uses improved templates)**
```bash
ENABLE_AI_REPLIES=false
ENABLE_POSTING=false
MAX_REPLIES_PER_TOPIC=10
```

### Benefits
- **Higher quality content**: AI generates natural, contextual responses instead of rigid templates
- **More engagement**: Post original content AND reply to others
- **Better conversion**: Authentic-sounding messages that naturally include your referral link
- **Increased activity**: Configurable to reply more frequently (10 replies per topic vs 3)
- **Cost effective**: Use gpt-4o-mini for ~$0.0001 per reply (incredibly cheap!)

## Sanity check
Set `SOCIAL_AGENT_MOCK_LOGIN=1` to run the bot in a mocked mode that exercises the startup flow without a real browser session. This prints the "Logged in & ready" banner once the initialization succeeds and is useful when credentials are unavailable.
