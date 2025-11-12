# Upgrade Notes: Political Mode Feature

## 📋 Summary

Added optional **Political Engagement Mode** to pivot bot from gambling to politics/tech/culture topics.

**IMPORTANT**: All changes are **feature-flagged** and **additive**. The existing gambling bot continues to work unless you explicitly enable the new mode.

## 🚨 Zero Breaking Changes

- ✅ **Auth/Login**: UNCHANGED - Chrome persistent context works exactly as before
- ✅ **Existing Features**: UNCHANGED - all gambling code intact
- ✅ **Default Behavior**: UNCHANGED - bot runs in gambling mode by default
- ✅ **Reversible**: Single commit revert or toggle flag to go back

## 📁 Files Added

### Configuration
- `config/bot_config.json` - New political mode settings
- `app/config_loader.py` - Config loader with safe fallbacks

### Media Generation
- `app/media/__init__.py` - Media module init
- `app/media/image_adapter.py` - AI/local image generation (NO-OP if no API keys)
- `app/media/video_adapter.py` - Video generation stub (NO-OP for now)

### Political Engagement
- `app/engagement/__init__.py` - Engagement module init
- `app/engagement/politics_reply.py` - Political templates and civil debate tactics

### Reply Composition
- `app/reply/__init__.py` - Reply module init
- `app/reply/compose.py` - Human-like reply orchestrator

### Documentation
- `docs/UPGRADE_NOTES.md` - This file

## 📝 Files Modified

### `.env` (1 line added)
```bash
# Feature flag for political mode (default: false = gambling mode)
USE_NEW_CONFIG=false
```

### `social_agent.py` (minimal changes)
- Added conditional import of new modules (only if `USE_NEW_CONFIG=true`)
- Added conditional path in reply generation
- Old gambling path remains default

## 🎚️ Feature Flags

### Main Toggle
```bash
USE_NEW_CONFIG=false  # false = gambling mode (default), true = political mode
```

### In `config/bot_config.json`
```json
{
  "rotation_enabled": true,        // Rotate through topics
  "promo_frequency": 0.25,         // 25% of replies include Gumroad link (capped at 0.3)
  "media_probability": 0.25,       // 25% of replies include image/video
  "single_mode_override": "",      // Override to force single mode (e.g., "politics")
  "debate_style": "confident-civil" // Tone: civil debate, no hate speech
}
```

## 🔧 How to Enable Political Mode

### Step 1: Set Environment Variable
```bash
# In .env file:
USE_NEW_CONFIG=true
```

### Step 2: (Optional) Configure Topics
Edit `config/bot_config.json` to customize:
- Topics to engage with
- Promo link frequency
- Media generation probability
- Reply tone/style

### Step 3: Restart Bot
```bash
python social_agent.py
```

Bot will now:
- ✅ Search political/tech topics instead of gambling
- ✅ Generate political replies with civil debate
- ✅ Optionally include AI-generated images
- ✅ Promote Gumroad link (25% of replies)
- ✅ Filter out gambling/casino domains

## 🧪 Testing / Dry Run

Test the new reply composer without posting:

```bash
cd /home/user/social_agent_codex
python -m app.reply.compose
```

This will show sample replies for political tweets without actually posting them.

## 🔄 How to Revert

### Option 1: Toggle Feature Flag (Instant)
```bash
# In .env:
USE_NEW_CONFIG=false
```
Restart bot - back to gambling mode immediately.

### Option 2: Git Revert (Complete Removal)
```bash
git revert <commit-hash>
```
This removes all new files and changes.

### Option 3: Delete New Files
```bash
rm -rf app/ config/ docs/UPGRADE_NOTES.md
# Remove USE_NEW_CONFIG line from .env
# Revert social_agent.py changes
```

## ⚙️ Optional: API Keys for Media

### Local Image Generation (Built-in)
- No API keys needed
- Uses PIL (already installed)
- Generates simple quote images

### AI Image Generation (Optional)
```bash
# In .env:
OPENAI_API_KEY=your_key_here
```
Enables DALL-E or other AI image generation.

### Video Generation (Future)
```bash
# In .env:
REPLICATE_API_TOKEN=your_token_here
```
Currently a stub - will enable video generation when implemented.

## 📊 What Changes in Behavior

### When `USE_NEW_CONFIG=false` (Default)
- ✅ Gambling topics (crypto gambling, slots, etc.)
- ✅ Rainbet promotion
- ✅ Casino-focused replies
- ✅ All existing behavior unchanged

### When `USE_NEW_CONFIG=true`
- ✅ Political/tech topics (elections, policy, AI, etc.)
- ✅ Gumroad promotion
- ✅ Civil debate replies
- ✅ Optional AI-generated images
- ✅ Filters out gambling content

## 🛡️ Safety Features

### Content Safety
- Blocks hate speech patterns
- Blocks unsafe/toxic tweets
- Uses civil debate templates only
- No slurs, no attacks on protected classes

### Spam Prevention
- Promo frequency capped at 30% max
- Media probability capped at 30% max
- Reply length enforced at 280 chars max
- Contextual link inclusion (not every reply)

## 🐛 Troubleshooting

### "Module not found: app.config_loader"
- Make sure `app/` directory exists
- Check that `USE_NEW_CONFIG=true` in .env
- Try: `python -c "from app.config_loader import get_config; print('OK')"`

### "Config file not found"
- Normal! Falls back to safe defaults
- Check `config/bot_config.json` exists
- Logs will show: `[config] Using default config`

### "PIL not available"
- Image generation will be disabled
- Text-only replies will still work
- Install: `pip install pillow`

### Bot still using gambling topics
- Check `USE_NEW_CONFIG=true` in .env
- Restart bot after changing .env
- Check logs for `[config] Loaded config from...`

## 📞 Support

If issues occur:
1. Set `USE_NEW_CONFIG=false` to revert
2. Check logs for `[config]`, `[media]`, `[politics]`, `[composer]` messages
3. Run dry-run test: `python -m app.reply.compose`

## 🎯 Next Steps

Once political mode is working, you can:
1. Adjust topics in `config/bot_config.json`
2. Tune promo frequency (0.0 to 0.3)
3. Enable/disable media generation
4. Add custom reply templates to `politics_reply.py`
5. Implement video generation in `video_adapter.py`

---

**Remember**: Political mode is **OFF by default**. Your gambling bot continues to work as-is until you enable the new features.
