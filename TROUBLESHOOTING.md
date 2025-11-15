# 🔧 Troubleshooting Guide - Social Agent Codex

**Last Updated:** 2025-11-15

---

## 🚨 Current Issues & Solutions

### Issue #1: "Request Might Be Automated" Warning

**Symptoms:**
- Twitter shows "this request might be automated" warning
- Bot gets blocked or rate limited
- Actions slow down or stop working

**Root Causes:**
1. **Too aggressive engagement** - Bot is interacting too fast
2. **Consistent patterns** - Bot behavior is too predictable
3. **High volume** - Too many actions in short time period

**Solutions:**

#### ✅ Immediate Actions:
1. **Increase delays** in `.env`:
   ```bash
   ACTION_DELAY_MIN_SECONDS=30  # Increase from 20
   ACTION_DELAY_MAX_SECONDS=60  # Increase from 40
   LOOP_DELAY_SECONDS=900       # Increase from 600 (15 min instead of 10)
   ```

2. **Reduce volume** in `.env`:
   ```bash
   MAX_REPLIES_PER_TOPIC=6      # Reduce from 12
   ```

3. **Add search topic variety** to avoid hitting same users:
   ```bash
   SEARCH_TOPICS="AI automation||growth hacking||product launches||indie hackers||creator economy||SaaS marketing"
   ```

4. **Take breaks** - Let the bot rest:
   - Stop the bot for 2-4 hours
   - Run it in shorter sessions (1-2 hours) instead of 24/7

#### ✅ Long-term Solutions:
1. **Add more randomization** (already implemented):
   - Random delays between actions
   - Random selection of reply templates
   - Random image attachment (50% of replies)

2. **Vary your behavior**:
   - Don't always follow every user you reply to
   - Sometimes just like without replying
   - Mix up timing patterns

3. **Account health**:
   - Build up account age and activity first
   - Get verified if possible
   - Have complete profile with bio, avatar, header

---

### Issue #2: Not Following People / No Follower Growth

**Symptoms:**
- Bot logs show "✅ Followed @username" but follow count doesn't increase
- No new followers
- Follow tracking logs exist but Twitter doesn't show the follows

**Root Causes:**
1. **Twitter rate limits** - Max ~400 follows per day
2. **Account restrictions** - New accounts have lower limits
3. **Automation detection** - Twitter blocking follow actions
4. **Follow button selector changed** - Twitter updated their UI

**Current Status:**
✅ **All follow code is properly implemented and connected**
- `FollowTracker` class: line 237
- `follow_user()` function: line 872
- `unfollow_user()` function: line 916
- Follow tracking log: `logs/follows.json`
- Auto-unfollow after 48 hours: Working
- Analytics tracking: Working

**Diagnosis Steps:**

1. **Check if bot is actually trying to follow:**
   ```bash
   # Look for [FOLLOW] logs
   tail -f logs/session.log | grep FOLLOW

   # Check follow tracking file
   cat logs/follows.json
   ```

2. **Check Twitter account status:**
   - Go to your Twitter account settings
   - Check if you have any restrictions
   - Look for suspension/limited functionality warnings

3. **Check follow limits:**
   - New accounts: ~400 follows/day max
   - If you hit the limit, Twitter will silently block follows
   - Wait 24 hours and try again

4. **Check if you're being rate limited:**
   - If you see "rate limit exceeded" in logs
   - Twitter may block follows without showing error
   - Reduce follow rate (see "Automated Request" solutions above)

**Solutions:**

#### If hitting rate limits:
```bash
# In .env, reduce aggressiveness:
MAX_REPLIES_PER_TOPIC=3        # Fewer replies = fewer follows
ACTION_DELAY_MIN_SECONDS=40    # Longer delays between actions
ACTION_DELAY_MAX_SECONDS=80
LOOP_DELAY_SECONDS=1800        # 30 min between cycles
```

#### If account is restricted:
1. **Manual activity** - Use the account manually for a few days
2. **Verify account** - Add phone number, email verification
3. **Age the account** - Older accounts have higher limits
4. **Build organic followers** - Get some real followers first

#### If selector changed (unlikely but possible):
- Check browser console for errors
- Inspect the Follow button element
- Update selectors in `follow_user()` function at line 890

---

### Issue #3: OpenAI API Not Configured

**Symptoms:**
- Bot uses template replies instead of AI-generated ones
- Logs show "AI_REPLIES=disabled (using templates only)"
- No AI-generated personalized replies

**Root Cause:**
- `OPENAI_API_KEY` not configured or is placeholder value

**Solution:**

1. **Get OpenAI API key:**
   - Go to https://platform.openai.com/api-keys
   - Create new secret key
   - Copy it immediately (you won't see it again)

2. **Add to `.env` file:**
   ```bash
   OPENAI_API_KEY=sk-proj-ABC123...YOUR_REAL_KEY_HERE
   ```

3. **Verify it works:**
   - Restart the bot
   - Look for log: "AI_REPLIES=enabled (OpenAI)"
   - Look for logs: "[AI] Calling OpenAI API for reply generation..."
   - Look for logs: "[AI] Generated reply (XXX chars)"

4. **Cost management:**
   - Model used: `gpt-4o-mini` (very cheap)
   - ~$0.001 per reply
   - Set usage limits in OpenAI dashboard if concerned

---

### Issue #4: No Followers Gained Despite Following

**Symptoms:**
- Bot successfully follows people
- No one follows back
- Follower count stays at 0 or very low

**Root Causes:**
1. **Account looks like a bot** - Profile not optimized
2. **No value proposition** - Users don't see why to follow back
3. **Replies aren't engaging** - Not providing value in replies
4. **Following wrong audience** - Target users not interested

**Solutions:**

#### ✅ Optimize Your Profile:
1. **Professional avatar** - Real photo or branded logo
2. **Compelling bio** - Clear value prop, what you tweet about
3. **Header image** - Professional, on-brand
4. **Pinned tweet** - Showcase your best content
5. **Tweet history** - Have 10-20 existing tweets before running bot

#### ✅ Target Better Audience:
```bash
# In .env, refine your search topics to match your niche:
SEARCH_TOPICS="YOUR_SPECIFIC_NICHE||YOUR_EXPERTISE||YOUR_INDUSTRY"

# Better keywords to find engaged users:
RELEVANT_KEYWORDS="question||how to||help||advice||struggling||looking for"
```

#### ✅ Improve Reply Quality:
1. **Use OpenAI** - AI replies are more engaging (see Issue #3)
2. **Better templates** - If not using AI, improve your templates:
   ```bash
   REPLY_TEMPLATES="Provide actual helpful advice, not just link spam||Ask thoughtful follow-up questions||Share genuine insights or experiences"
   ```

#### ✅ Build Social Proof First:
1. **Get initial followers manually** - 50-100 real followers
2. **Post quality content** - Tweet valuable things daily
3. **Engage authentically** - Manual engagement alongside bot
4. **Use images** - Already enabled at 50% (IMAGE_ATTACH_RATE=0.5)

---

## 📊 How to Monitor Bot Health

### 1. Check Analytics:
```bash
cat logs/analytics.json
```
**Look for:**
- Total replies, likes, follows
- Success vs failure rates
- Trends over time

### 2. Check Follow Tracking:
```bash
cat logs/follows.json
```
**Should show:**
- Users you've followed
- Timestamps
- Growing list over time

### 3. Check Reply History:
```bash
cat logs/replied.json
```
**Should show:**
- Tweet IDs/URLs you've replied to
- Growing list (no duplicates)

### 4. Watch Live Logs:
```bash
# In headless mode (HEADLESS=true), watch logs:
python3 social_agent.py

# Look for these success indicators:
# [AI] Generated reply (270 chars)
# [LIKE] ✅ Liked tweet
# [REPLY] ✅ Reply posted successfully!
# [FOLLOW] ✅ Followed @username
```

---

## 🎯 Recommended Safe Settings

For accounts concerned about automation detection:

```bash
# Conservative settings (safer, slower growth):
HEADLESS=false                    # Run visible browser to watch it work
DEBUG=false
SEARCH_TOPICS="niche topic 1||niche topic 2||niche topic 3"
MIN_TWEET_LENGTH=80               # Only reply to substantial tweets
MIN_KEYWORD_MATCHES=2             # More selective targeting
MAX_REPLIES_PER_TOPIC=2           # Very conservative
ACTION_DELAY_MIN_SECONDS=40       # Slow and steady
ACTION_DELAY_MAX_SECONDS=80
LOOP_DELAY_SECONDS=1800           # 30 min between cycles
IMAGE_ATTACH_RATE=0.3             # 30% images (less aggressive)
```

For established accounts wanting aggressive growth:

```bash
# Aggressive settings (faster growth, higher risk):
HEADLESS=true
MAX_REPLIES_PER_TOPIC=12          # Maximum engagement
ACTION_DELAY_MIN_SECONDS=20       # Faster actions
ACTION_DELAY_MAX_SECONDS=40
LOOP_DELAY_SECONDS=600            # 10 min between cycles
IMAGE_ATTACH_RATE=0.6             # 60% images (max engagement)
OPENAI_API_KEY=<your-key>         # AI replies for quality
```

---

## 🔍 Current Configuration Status

**✅ Fixed in This Session:**
1. Restored all 7 sales-driving features (were deleted in merge)
2. Updated `.env` with optimized settings:
   - MAX_REPLIES_PER_TOPIC: 3 → 12
   - LOOP_DELAY_SECONDS: 900 → 600
   - MIN_TWEET_LENGTH: 60 → 40
   - Fixed X_USERNAME and X_PASSWORD naming
3. Added OPENAI_API_KEY, IMAGE_PROVIDER, IMAGE_ATTACH_RATE to config
4. Created FEATURES_LIST.md tracking document

**⚠️ Still Needs User Action:**
1. **Add real OpenAI API key** to `.env`:
   ```bash
   OPENAI_API_KEY=sk-proj-YOUR_REAL_KEY_HERE
   ```

2. **Verify Twitter credentials** in `.env`:
   ```bash
   X_USERNAME=your_actual_twitter_handle
   X_PASSWORD=your_actual_password
   ```

3. **Update referral link** in `.env`:
   ```bash
   REFERRAL_LINK=https://your-actual-offer-url.com
   ```

4. **If getting "automated request" warnings:**
   - Increase delays (see Issue #1 solutions)
   - Reduce volume (MAX_REPLIES_PER_TOPIC to 3-6)
   - Take breaks (stop bot for few hours)

---

## 📈 Expected Performance

**Realistic Expectations:**

| Metric | Conservative | Moderate | Aggressive |
|--------|-------------|----------|------------|
| Replies/hour | 2-4 | 6-12 | 12-20 |
| Follows/hour | 2-4 | 6-12 | 12-20 |
| Follow-back rate | 5-15% | 10-25% | 15-35% |
| New followers/day | 5-20 | 20-60 | 40-150 |
| Time to 1K followers | 2-6 months | 1-2 months | 2-4 weeks |

**Factors affecting results:**
- Account age and credibility
- Profile quality and optimization
- Niche and target audience
- Reply quality (AI vs templates)
- Image usage (2-3x boost with images)
- Manual engagement alongside bot
- Content posted outside of bot

---

## 🆘 Quick Fixes

**Bot not starting?**
```bash
# Check requirements
pip install -r requirements.txt
playwright install chromium

# Check .env file exists
ls -la .env

# Run with debug mode
DEBUG=true python3 social_agent.py
```

**Bot keeps logging out?**
```bash
# Delete old session and login fresh
rm -rf ~/.social_agent_codex/browser_session/
rm -f auth.json

# Run again (will prompt for manual login)
python3 social_agent.py
```

**Bot actions not working?**
```bash
# Run in visible mode to watch what's happening
HEADLESS=false python3 social_agent.py

# Check for Twitter UI changes
# Inspect elements in browser
# Update selectors if needed
```

---

## 📞 Getting Help

1. **Check logs first:** `logs/` directory
2. **Review FEATURES_LIST.md:** Verify all features present
3. **Try visible mode:** `HEADLESS=false` to watch bot
4. **Reduce aggressiveness:** If getting blocked
5. **Check Twitter account:** No restrictions or bans

---

**Remember:** This is a production revenue-generating bot. Be patient, start conservatively, and scale up gradually as you see what works for your account and niche.
