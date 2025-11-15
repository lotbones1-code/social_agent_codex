# 🚨 CRITICAL FEATURES MANIFEST 🚨

**DO NOT DELETE ANY FEATURES FROM THIS LIST**

This file is the source of truth for ALL features that MUST exist in the bot.
If you're an AI assistant working on this code, READ THIS FIRST before making changes.

---

## 🛡️ TRIPLE-LAYER PROTECTION SYSTEM

### Layer 1: Startup Validation
- **Function**: `validate_critical_features()` (line ~1471)
- **Runs**: Every time bot starts (BEFORE doing anything)
- **Effect**: Bot REFUSES TO START if any feature is missing
- **Output**: Shows exactly what's missing and exits with error code 1

### Layer 2: Inline Comments
- **Pattern**: `# CRITICAL: DO NOT REMOVE - <description>`
- **Count**: 33 protected items throughout codebase
- **Purpose**: Warns AI assistants before they delete code

### Layer 3: This Manifest
- **File**: `FEATURES_MANIFEST.md`
- **Purpose**: Complete documentation of all features
- **Rule**: READ THIS BEFORE ANY CODE CHANGES

**If you think code is "unused" or "can be simplified" - STOP and read this file first!**

---

## 🎯 THE 7 REVENUE-GENERATING FEATURES (v4.0)

### 1. **AI-Powered Replies** (ChatGPT Integration) 🧠
- **Function**: `generate_ai_reply()` (line ~1147)
- **Config Field**: `openai_api_key: Optional[str]` (line 106)
- **Env Var**: `OPENAI_API_KEY`
- **Import**: `import requests` (line 43)
- **Status**: ✅ PROTECTED (validated on startup)
- **What it does**:
  - Calls OpenAI GPT-4o-mini API
  - Generates unique, contextual replies
  - Temperature 0.9 for variety
  - Max 280 chars (Twitter limit)
  - Falls back to templates if API fails
- **Why critical**: Makes bot sound human, not robotic
- **Cost**: ~$0.001 per reply
- **Validation check**: Function exists + requests module imported

### 2. **Auto-Follow System** 👥
- **Class**: `FollowTracker` (line ~287)
- **Functions**:
  - `follow_user()` (line ~1015)
  - Called after every reply (line ~1354)
- **Storage**: `logs/follows.json`
- **Config**: Always enabled (no toggle)
- **Status**: ✅ PROTECTED (validated on startup)
- **What it does**:
  - Automatically follows user after replying
  - Tracks follow timestamp
  - Logs follow count to analytics
  - Builds network and visibility
- **Why critical**: Network growth = more reach = more sales
- **Validation check**: FollowTracker class exists + follow_user() exists

### 3. **Auto-Unfollow System** 🔄
- **Class**: `FollowTracker` (line ~287)
- **Functions**:
  - `unfollow_user()` (line ~1082)
  - `process_unfollows()` (line ~1117)
  - Called at loop start (line ~1423)
- **Logic**: Unfollow after 72 hours if they didn't follow back
- **Storage**: `logs/follows.json`
- **Status**: ✅ PROTECTED (validated on startup)
- **What it does**:
  - Monitors all follows
  - Checks if they followed back
  - Unfollows stale follows after 72h
  - Maintains healthy follower ratio
- **Why critical**: Prevents looking like spam account
- **Validation check**: process_unfollows() exists

### 4. **Image Attachments** 🖼️
- **Function**: `generate_reply_image()` (line ~1249)
- **Config**:
  - `IMAGE_ATTACH_RATE=0.6` (60% of replies get images)
  - `REPLICATE_API_TOKEN`
  - `REPL_IMAGE_MODEL=black-forest-labs/flux-schnell`
- **Called**: Before sending reply (line ~1341)
- **Attachment**: In `send_reply()` (line ~717-750)
- **Storage**: `logs/images/reply_*.png`
- **Status**: ✅ PROTECTED (validated on startup)
- **What it does**:
  - Generates AI image using Replicate API
  - Attaches to 60% of replies
  - Uses tweet topic as image prompt
  - Detailed logging for debugging
- **Why critical**: 2-3x engagement boost with images
- **Validation check**: generate_reply_image() exists

### 5. **Like-Before-Reply** ❤️
- **Function**: `like_tweet()` (line ~806)
- **Called**: Before every reply (line ~1335)
- **Config**: Always enabled (no toggle)
- **Status**: ✅ PROTECTED (validated on startup)
- **What it does**:
  - Likes tweet before replying
  - Looks more human
  - Boosts engagement
  - Logs to analytics
- **Why critical**: Human-like behavior prevents bot detection
- **Validation check**: like_tweet() exists

### 6. **Smart DM System** 💬
- **Class**: `DMTracker` (line ~369)
- **Function**: `maybe_send_dm()` (line ~920)
- **Config**:
  - `ENABLE_DMS=true`
  - `DM_TRIGGER_LENGTH=220` (min tweet length)
  - `DM_INTEREST_THRESHOLD=3.2` (interest score needed)
  - `DM_QUESTION_WEIGHT=0.75` (question importance)
  - `DM_TEMPLATES="..."` (5 personalized templates)
- **Field**: `dm_trigger_length: int` (line 101)
- **Called**: After successful reply (line ~1367)
- **Storage**: `logs/dms.json`
- **Status**: ✅ PROTECTED (validated on startup)
- **What it does**:
  - Detects high-intent leads (long tweets, questions, keywords)
  - Sends personalized DM with product link
  - Tracks DMs to avoid spam
  - Uses templates with placeholders
- **Why critical**: Directly converts interested leads
- **Validation check**: DMTracker class + maybe_send_dm() + dm_trigger_length field

### 7. **Analytics Tracking** 📊
- **Class**: `AnalyticsTracker` (line ~411)
- **Storage**: `logs/analytics.json`
- **Status**: ✅ PROTECTED (validated on startup)
- **Metrics tracked**:
  - `total_replies` - Total replies posted
  - `total_follows` - Total follows executed
  - `total_unfollows` - Total unfollows executed
  - `total_dms` - Total DMs sent
  - `total_likes` - Total likes performed
  - `total_images_attached` - Total images attached
  - `reply_failures` - Failed reply attempts
  - `first_run` - Timestamp of first run
  - `last_run` - Timestamp of last run
- **What it does**:
  - Logs every action
  - Tracks conversions
  - Performance monitoring
  - Visible in logs
- **Why critical**: Can't optimize what you don't measure
- **Validation check**: AnalyticsTracker class exists

---

## 🛠️ CORE INFRASTRUCTURE (MUST NEVER BE REMOVED)

### Session Persistence
- **Function**: `prepare_authenticated_session()` (line ~1549)
- **Browser**: Chromium with persistent context
- **Session Dir**: `~/.social_agent_codex/browser_session/`
- **Auth File**: `auth.json`
- **Stealth**:
  - `--disable-blink-features=AutomationControlled`
  - `ignore_default_args=["--enable-automation"]`
  - Real Chrome user agent
- **Status**: ✅ PROTECTED
- **Why**: Prevents re-login, avoids bot detection

### Deduplication System
- **Class**: `MessageRegistry` (line ~53)
- **Storage**: `logs/replied.json`
- **Status**: ✅ PROTECTED
- **Why**: Prevents replying to same tweet twice

### Tweet Filtering Pipeline
- **Function**: `process_tweets()` (line ~1264)
- **Filters**:
  1. Self-tweet detection
  2. Retweet filtering
  3. Keyword matching (`RELEVANT_KEYWORDS`)
  4. Spam keyword blocking (`SPAM_KEYWORDS`)
  5. Minimum length (`MIN_TWEET_LENGTH=40`)
  6. Already-replied check (MessageRegistry)
- **Status**: ✅ PROTECTED
- **Why**: Protects account from bans, ensures quality

### Template Fallback System
- **Config**: `REPLY_TEMPLATES` (10 templates)
- **Format**: `{topic}`, `{focus}`, `{ref_link}` placeholders
- **Used when**: OpenAI API fails or times out
- **Status**: ✅ PROTECTED
- **Why**: Bot never stops working, even if AI fails

### Video Framework
- **Class**: `VideoService` (line ~83)
- **Status**: ✅ PROTECTED (even though not actively used)
- **Why**: Future expansion framework

---

## 🔧 REQUIRED CONFIG FIELDS (.env)

**DO NOT REMOVE ANY OF THESE - Each one is critical:**

```bash
# Core Settings
HEADLESS=false                          # Browser visibility
USERNAME=changeme@example.com           # Login (not used with persistent session)
PASSWORD=super-secret-password          # Login (not used with persistent session)

# AI Features
OPENAI_API_KEY=sk-...                   # CRITICAL: AI reply generation
REPLICATE_API_TOKEN=r8_...              # CRITICAL: Image generation
REPL_IMAGE_MODEL=black-forest-labs/flux-schnell

# Revenue
REFERRAL_LINK=https://...               # CRITICAL: Your product link

# Image Feature
IMAGE_ATTACH_RATE=0.6                   # CRITICAL: 60% of replies get images

# DM Feature
ENABLE_DMS=true                         # CRITICAL: Enable/disable DM system
DM_TRIGGER_LENGTH=220                   # CRITICAL: Min tweet length for DM
DM_INTEREST_THRESHOLD=3.2               # CRITICAL: Interest score threshold
DM_QUESTION_WEIGHT=0.75                 # CRITICAL: Question importance weight
DM_TEMPLATES="..."                      # CRITICAL: DM message templates (5 variations)

# Reply Templates (Fallback)
REPLY_TEMPLATES="..."                   # CRITICAL: 10 templates for fallback

# Search & Filtering
SEARCH_TOPICS="AI automation||growth hacking||product launches"  # CRITICAL
RELEVANT_KEYWORDS="AI||automation||growth||launch||community||creator economy"  # CRITICAL
SPAM_KEYWORDS="giveaway||airdrop||pump||casino||xxx||nsfw"  # CRITICAL

# Quality Filters
MIN_TWEET_LENGTH=40                     # CRITICAL: Prevents short/spam tweets
MIN_KEYWORD_MATCHES=1                   # CRITICAL: Relevance threshold
MAX_REPLIES_PER_TOPIC=12                # CRITICAL: Rate limiting

# Timing
LOOP_DELAY_SECONDS=600                  # CRITICAL: 10 min between cycles
```

---

## 🚨 RULES FOR AI ASSISTANTS

### ✅ ALWAYS DO THIS:
1. Read this manifest BEFORE making any changes
2. Add new features WITHOUT removing existing ones
3. Update this manifest when adding critical features
4. Add new features to `validate_critical_features()` dict
5. Use `# CRITICAL: DO NOT REMOVE` comments for important code
6. Test that all 7 features still work after changes

### ❌ NEVER DO THIS:
1. Delete any function, class, or config field listed above
2. Remove "CRITICAL: DO NOT REMOVE" comments
3. Disable `validate_critical_features()` function
4. Remove `import requests` (needed for OpenAI)
5. Change file paths (browser_session, auth.json, logs/)
6. Simplify by removing features
7. Assume code is "unused" without asking user first

### 🤔 IF YOU'RE UNSURE:
- **ASK THE USER FIRST** before removing anything
- If code looks unused, it probably has a purpose
- Complexity = features = revenue (don't oversimplify)

---

## ✅ VERIFICATION COMMANDS

Before committing changes, run these:

```bash
# Check all 7 features exist
grep -c "def generate_ai_reply" social_agent.py    # Should be 1
grep -c "class FollowTracker" social_agent.py      # Should be 1
grep -c "def process_unfollows" social_agent.py    # Should be 1
grep -c "def generate_reply_image" social_agent.py # Should be 1
grep -c "def like_tweet" social_agent.py           # Should be 1
grep -c "class DMTracker" social_agent.py          # Should be 1
grep -c "class AnalyticsTracker" social_agent.py   # Should be 1

# Check protection count
grep -c "CRITICAL: DO NOT REMOVE" social_agent.py  # Should be 33+

# Check imports
grep -c "import requests" social_agent.py          # Should be 1

# Verify startup validation exists
grep -c "def validate_critical_features" social_agent.py  # Should be 1

# Test that bot starts
./run_agent.sh  # Should show "✅ All critical features validated"
```

---

## 📊 FEATURE SUMMARY TABLE

| # | Feature | Function/Class | Config | Protected | Active |
|---|---------|---------------|--------|-----------|--------|
| 1 | AI Replies | `generate_ai_reply()` | `OPENAI_API_KEY` | ✅ | ✅ |
| 2 | Auto-Follow | `follow_user()`, `FollowTracker` | Always on | ✅ | ✅ |
| 3 | Auto-Unfollow | `process_unfollows()` | Always on | ✅ | ✅ |
| 4 | Image Attachments | `generate_reply_image()` | `IMAGE_ATTACH_RATE` | ✅ | ✅ |
| 5 | Like-Before-Reply | `like_tweet()` | Always on | ✅ | ✅ |
| 6 | Smart DMs | `maybe_send_dm()`, `DMTracker` | `ENABLE_DMS` | ✅ | ✅ |
| 7 | Analytics | `AnalyticsTracker` | Always on | ✅ | ✅ |

**Total Features**: 7 major + core infrastructure
**Protection Level**: MAXIMUM (3 layers)
**Validation**: Automatic on every startup

---

## 📝 VERSION HISTORY

- **v4.0** (2025-11-15): Added 7 major features + triple-layer protection
  - AI-powered replies with ChatGPT
  - Auto-follow/unfollow system
  - Image attachments via Replicate
  - Like-before-reply
  - Smart DM system for leads
  - Analytics tracking
  - Startup validation system

- **v3.0** (Previous): Basic reply bot with templates

- **v2.0** (Previous): Manual authentication

- **v1.0** (Previous): Initial prototype

---

## 🔐 WHY THESE PROTECTIONS EXIST

**History**: Features kept getting "accidentally deleted" by AI assistants who thought they were:
- "Unused code"
- "Unnecessary complexity"
- "Can be simplified"

**Reality**: Every line has a purpose. This is production code generating real revenue.

**Solution**: Triple-layer protection ensures features can't be deleted accidentally:
1. Bot won't start if features are missing (startup validation)
2. Inline comments warn before deletion
3. This manifest documents everything

**If you're an AI assistant reading this**: THANK YOU for respecting these protections. The user has been frustrated by repeated deletions. Your job is to ADD features, not remove them.

---

**Last Updated**: 2025-11-15
**Version**: 4.0
**Total Protected Items**: 7 features + 33 inline comments + startup validation
**Status**: ALL FEATURES WORKING ✅
