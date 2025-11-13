# AI Features Guide

## Overview

Your Social Agent now has **optional AI-powered features** that make your bot more intelligent and natural:

✅ **AI-Generated Replies** - GPT-4o-mini creates contextual, human-like responses
✅ **AI Image Generation** - DALL-E creates professional images for your posts
✅ **Automatic Fallback** - If AI fails or isn't configured, templates work as before
✅ **No Breaking Changes** - Everything works exactly as before without AI configured

---

## 🚀 Quick Start

### 1. Install New Dependencies

```bash
pip install -r requirements.txt
```

This adds: `openai`, `requests`, `Pillow`

### 2. Add Your OpenAI API Key

Get your API key from: https://platform.openai.com/api-keys

Add to your `.env` file:

```bash
OPENAI_API_KEY=sk-proj-...your-key-here...
```

### 3. Run As Normal

```bash
RUN=1 make start
```

That's it! The bot will now use AI for replies and keep templates as fallback.

---

## 💰 Cost Breakdown

### AI Replies (GPT-4o-mini)
- **Per reply**: ~$0.0025 (quarter of a cent)
- **100 replies/day**: ~$0.25/day = **$7.50/month**
- **300 replies/day**: ~$0.75/day = **$22.50/month**

### AI Images (DALL-E 3)
- **Per image**: ~$0.04 (4 cents)
- **10 images/day**: ~$0.40/day = **$12/month**
- **Image generation is separate** - not automatic with replies

### Total Estimate
- **Light usage** (50 replies/day): **$4-8/month**
- **Medium usage** (150 replies/day): **$12-18/month**
- **Heavy usage** (300+ replies/day): **$25-35/month**

**Much cheaper than manual engagement time!**

---

## 🎛️ Configuration

### Enable/Disable AI Replies

Add to `.env`:

```bash
# Enable AI replies (default: true if OPENAI_API_KEY is set)
ENABLE_AI_REPLIES=true

# Or disable to use only templates
ENABLE_AI_REPLIES=false
```

### Image Generation Provider

```bash
# Choose provider (default: openai)
IMAGE_PROVIDER=openai  # Use DALL-E
# IMAGE_PROVIDER=replicate  # Use Replicate instead
# IMAGE_PROVIDER=none  # Disable AI images

# DALL-E settings
IMAGE_MODEL=dall-e-3  # or dall-e-2 (cheaper but lower quality)
IMAGE_SIZE=1024x1024  # or 1024x1792, 1792x1024
```

**DALL-E 3 Pricing:**
- 1024x1024: $0.04/image
- 1024x1792 or 1792x1024: $0.08/image

**DALL-E 2 Pricing (cheaper):**
- 1024x1024: $0.02/image

---

## 🧠 How AI Replies Work

### Automatic Workflow

```
1. Bot finds a relevant tweet
2. Tries AI generation first (if configured)
3. Falls back to templates if AI fails
4. Posts the reply
```

### AI Reply Generation

The AI receives:
- The original tweet text
- Your search topic
- Instructions to be natural and engaging

It creates:
- Context-aware responses
- Natural, human-like language
- Varied tone and style (not robotic)
- Includes your referral link (30% of the time)

### Example Comparison

**Template-based:**
```
Been riffing with other builders about AI automation,
and this machine learning tips breakdown keeps delivering wins.
Shortcut link: https://example.com/guide
```

**AI-generated:**
```
Really interesting take on ML optimization! Have you tried
ensemble methods? They've been a game-changer for me in
production environments. More on this: https://example.com/guide
```

---

## 🎨 Image Generation

### Command Line Usage

```bash
# Generate an image
python generators/image_gen.py --topic "AI automation tools" --out output.png
```

### In Code

The VideoService class in `social_agent.py` can be extended to generate images. Currently it's configured for video but can be adapted.

### Providers

1. **OpenAI DALL-E** (default)
   - Requires: `OPENAI_API_KEY`
   - Best quality
   - $0.04-0.08 per image

2. **Replicate**
   - Requires: `REPLICATE_API_TOKEN`
   - Various models available
   - Pricing varies by model

3. **Pillow Fallback**
   - Free, generates simple placeholder
   - Used if both APIs fail

---

## 🔒 Safety & Privacy

### What Gets Sent to OpenAI

**For Replies:**
- Tweet text you're replying to
- Your search topic
- System instructions (tone, style)

**NOT sent:**
- Your credentials
- Your full timeline
- Other users' data
- Browser session info

### Rate Limits

OpenAI free tier limits:
- 3 requests/minute
- 200 requests/day

**If you hit limits:**
- Bot falls back to templates
- No errors, seamless transition
- Logs show "[AI] API failed, using template"

### Monitoring Costs

Check usage at: https://platform.openai.com/usage

Set spending limits: https://platform.openai.com/account/limits

---

## 🐛 Troubleshooting

### "AI generation failed, using template"

**Causes:**
1. No `OPENAI_API_KEY` set → Set it in `.env`
2. Invalid API key → Check key at platform.openai.com
3. Rate limit hit → Wait or upgrade plan
4. Network error → Retries automatically

**This is normal behavior** - templates are the fallback!

### "OpenAI package not installed"

```bash
pip install openai
```

### AI replies seem too robotic

Edit `ai_reply_generator.py` line 93:
```python
temperature=0.9,  # More creative (higher = more random)
```

Lower values (0.5-0.7) = more focused
Higher values (0.9-1.0) = more creative

### Costs higher than expected

Check:
1. How many replies per day: `grep "Using AI-generated reply" logs/session.log | wc -l`
2. API usage dashboard: https://platform.openai.com/usage
3. Consider `ENABLE_AI_REPLIES=false` to test templates

---

## 📊 Monitoring AI Usage

### Check if AI is working

```bash
# See AI status on startup
grep "\[AI\]" logs/session.log

# Count AI vs template replies
grep "Using AI-generated reply" logs/session.log | wc -l
grep "Using template-based reply" logs/session.log | wc -l
```

### Expected Output

When working correctly:
```
[AI] ✅ GPT-4o-mini enabled for reply generation (costs ~$1-5/month)
[AI] Using AI-generated reply
[AI] Using AI-generated reply
```

When using templates (AI disabled or failed):
```
[AI] No OPENAI_API_KEY found - using template-based replies (free)
[TEMPLATE] Using template-based reply
```

---

## 🎯 Best Practices

### 1. Start with Templates

Run for a few days without AI to establish baseline:
```bash
# In .env
ENABLE_AI_REPLIES=false
```

### 2. Enable AI Gradually

Once templates work:
```bash
ENABLE_AI_REPLIES=true
OPENAI_API_KEY=sk-proj-...
```

### 3. Monitor Costs

Set OpenAI spending limit to $10/month to start:
https://platform.openai.com/account/limits

### 4. Test Locally First

```bash
# Test AI reply generation
python ai_reply_generator.py "Interesting post about AI automation!"
```

### 5. Review AI Responses

Check `logs/session.log` to see what AI is generating:
```bash
tail -f logs/session.log | grep -A 1 "\[AI\] Generated"
```

---

## 🔄 Reverting to Templates Only

If you want to disable AI completely:

### Option 1: Environment Variable
```bash
# In .env
ENABLE_AI_REPLIES=false
```

### Option 2: Remove API Key
```bash
# In .env, comment out or remove:
# OPENAI_API_KEY=sk-proj-...
```

### Option 3: Uninstall Package
```bash
pip uninstall openai
```

**All methods are safe** - bot automatically falls back to templates.

---

## 📈 Advanced: Custom AI Prompts

Edit `ai_reply_generator.py` to customize AI behavior:

```python
# Line 80-90: System prompt
system_prompt = f"""You are replying to tweets about {topic} on Twitter/X.

Your style:
- [YOUR CUSTOM INSTRUCTIONS HERE]
- Engaging and conversational
- [MORE CUSTOM RULES]
"""
```

Restart bot after changes:
```bash
make kill
RUN=1 make start
```

---

## 🆘 Support

### Getting Help

1. Check logs: `tail -f logs/session.log`
2. Test AI: `python ai_reply_generator.py "test tweet"`
3. Verify key: Check https://platform.openai.com/api-keys
4. Review costs: https://platform.openai.com/usage

### Common Issues

| Issue | Solution |
|-------|----------|
| No AI replies | Check `OPENAI_API_KEY` is set |
| Too expensive | Set `ENABLE_AI_REPLIES=false` or lower reply count |
| Too robotic | Increase temperature (0.9-1.0) |
| Rate limited | Wait or upgrade OpenAI plan |
| Import error | Run `pip install -r requirements.txt` |

---

## ✅ Summary

**You now have:**
- ✅ AI-powered reply generation (GPT-4o-mini)
- ✅ AI image generation (DALL-E)
- ✅ Automatic template fallback
- ✅ Cost-effective operation ($5-25/month)
- ✅ Zero breaking changes to existing code
- ✅ Easy enable/disable via environment variables

**Your bot is now smarter, more natural, and still reliable!**
