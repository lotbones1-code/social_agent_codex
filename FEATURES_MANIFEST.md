# 🚨 CRITICAL FEATURES MANIFEST - READ BEFORE ANY CODE CHANGES

**⚠️ WARNING TO ALL AI ASSISTANTS / DEVELOPERS:**

**NEVER DELETE OR DISABLE ANY FEATURE LISTED BELOW WITHOUT EXPLICIT USER APPROVAL**

This is a PRODUCTION bot generating REAL revenue. Your job is to ADD features, NOT remove them.

---

## 🛡️ AUTOMATIC PROTECTION SYSTEM

**The bot now has RUNTIME VALIDATION built-in!**

Function: `validate_critical_features()` (Lines ~863-917)

**What it does:**
- Runs AUTOMATICALLY at bot startup (before anything else)
- Checks that ALL critical features exist in the code
- **Bot REFUSES TO START if ANY feature is missing**
- Shows clear error message listing missing features

**This means:**
- If you accidentally delete a feature, the bot won't run
- You'll immediately know what's missing
- No more silent feature deletions
- Last line of defense against mistakes

**DO NOT REMOVE THIS FUNCTION!** It's protecting all the other features.

---

## ✅ CRITICAL FEATURES THAT MUST NEVER BE REMOVED

### 1. **OpenAI AI-Powered Replies** 🧠
**File:** `social_agent.py`
**Functions:**
- `generate_ai_reply()` - Lines ~512-587
- Called from `process_tweets()` - Lines ~652-661

**Config:**
- `BotConfig.openai_api_key` field
- `OPENAI_API_KEY` in `.env`
- `import requests` at top of file

**What it does:**
- Generates contextual, natural replies using GPT-4o-mini
- Falls back to templates if API fails
- Costs ~$0.15 per 1000 replies
- Makes replies sound HUMAN not robotic

**How to verify it exists:**
```bash
grep -n "def generate_ai_reply" social_agent.py
grep -n "import requests" social_agent.py
grep "OPENAI_API_KEY" .env
```

---

### 2. **Template-Based Reply System** 📝
**File:** `social_agent.py`
**Functions:**
- Template selection in `process_tweets()` - Lines ~664-671
- `DEFAULT_REPLY_TEMPLATES` constant

**Config:**
- `REPLY_TEMPLATES` in `.env`
- Supports placeholders: `{topic}`, `{focus}`, `{ref_link}`

**What it does:**
- Fallback when OpenAI unavailable
- 10 professional sales templates
- Includes referral links for conversions

---

### 3. **Session Persistence & Authentication** 🔐
**File:** `social_agent.py`
**Functions:**
- `prepare_authenticated_session()` - Lines ~676-750
- `ensure_logged_in()`
- `automated_login()`
- `wait_for_manual_login()`

**Critical paths:**
- Browser profile: `~/.social_agent_codex/browser_session/`
- Session file: `auth.json`

**What it does:**
- Three-tier login (session → automated → manual)
- Persistent browser context across restarts
- Never loses login state

**NEVER change these paths or login flow!**

---

### 4. **Smart Tweet Filtering Pipeline** 🎯
**File:** `social_agent.py`
**Function:** `process_tweets()` - Lines ~590-600

**Filters (in order):**
1. Self-tweet detection
2. Retweet filtering
3. Keyword matching
4. Spam keyword blocking
5. Minimum length check
6. Duplicate prevention (MessageRegistry)

**What it does:**
- Prevents replying to own tweets
- Blocks spam/NSFW content
- Ensures quality engagement
- Protects account from bans

**NEVER remove or weaken these filters!**

---

### 5. **Message Registry (Deduplication)** 🗂️
**File:** `social_agent.py`
**Class:** `MessageRegistry` - Lines ~202-230

**Storage:** `logs/replied.json`

**What it does:**
- Tracks every tweet replied to
- Prevents duplicate replies
- Persists across restarts

**NEVER remove or bypass this system!**

---

### 6. **Video Generation Hook** 🎥
**File:** `social_agent.py`
**Class:** `VideoService` - Lines ~232-280

**Called from:** `process_tweets()` after successful reply

**What it does:**
- Generates video content via Replicate API
- Optional feature (enabled via config)
- Framework for future video replies

---

### 7. **DM Framework** 💬
**File:** `social_agent.py`
**Function:** `maybe_send_dm()` - Lines ~484-502

**Config:**
- `ENABLE_DMS` in `.env`
- `DM_TEMPLATES` with placeholders

**What it does:**
- Framework for automated DMs to high-intent leads
- Not fully implemented yet, but structure MUST remain

---

### 8. **Image Generation** 🖼️
**File:** `generators/image_gen.py`

**What it does:**
- Generates images via Replicate or Pillow
- Free fallback options
- Called at startup as smoke test

**Not yet wired to replies, but DO NOT DELETE**

---

### 9. **Human-Like Behavior** 🤖→👤
**File:** `social_agent.py`

**Features:**
- Random delays: `ACTION_DELAY_MIN/MAX_SECONDS`
- Max replies per topic: `MAX_REPLIES_PER_TOPIC`
- Loop delays: `LOOP_DELAY_SECONDS`
- Randomized template selection

**What it does:**
- Prevents bot detection
- Avoids rate limits
- Mimics human patterns

---

### 10. **Playwright Selectors & Reply Flow** 🎭
**File:** `social_agent.py`
**Function:** `send_reply()` - Lines ~464-482

**Critical selectors:**
- `button[data-testid='reply']`
- `div[data-testid^='tweetTextarea_']`
- `button[data-testid='tweetButton']`

**What it does:**
- Clicks reply button
- Types message
- Posts reply
- Takes debug screenshots

**NEVER modify selectors without testing!**

---

## 🔧 HOW TO ADD NEW FEATURES SAFELY

1. **Read this manifest first**
2. **Check that your change doesn't remove/break existing features**
3. **Add to existing code, don't replace**
4. **Test that all features still work**
5. **Update this manifest if adding new critical feature**

---

## ✅ VERIFICATION CHECKLIST

Before committing ANY changes, verify:

- [ ] `grep "def generate_ai_reply" social_agent.py` returns result
- [ ] `grep "import requests" social_agent.py` returns result
- [ ] `grep "class MessageRegistry" social_agent.py` returns result
- [ ] `grep "def send_reply" social_agent.py` returns result
- [ ] `grep "OPENAI_API_KEY" .env` returns result
- [ ] `ls generators/image_gen.py` exists
- [ ] All template placeholders still work: `{topic}`, `{focus}`, `{ref_link}`

---

## 📜 COMMIT MESSAGE TEMPLATE

When committing changes:

```
[FEATURE ADD] <what you added>

✅ Added: <list new features>
🔒 Preserved: OpenAI replies, filters, auth, registry, templates
✓ Verified: All critical features still present
```

---

## 🚫 NEVER DO THIS

- ❌ Remove OpenAI integration
- ❌ Delete `generate_ai_reply()` function
- ❌ Remove `import requests`
- ❌ Simplify by removing features
- ❌ Disable safety filters
- ❌ Change browser profile path
- ❌ Break MessageRegistry
- ❌ Remove template system
- ❌ Delete placeholder support

---

**Last Updated:** 2025-11-14
**By:** User frustrated by repeated deletions - PLEASE RESPECT THIS
