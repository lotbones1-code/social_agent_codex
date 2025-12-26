# STAGE 11B BREAKING NEWS VIDEO SYSTEM - DEBUG REPORT

## 1. DOES STAGE 11B CODE EXIST?
**✅ YES**

- **File:** `breaking_news_11b.py` exists (807 lines)
- **Main Function:** `stage_11b_breaking_news_jacker()` (lines 566-807)
- **Called From:** `social_agent.py` bot_loop() (lines 7437-7475)

### Key Functions:
- `is_spiking_trend()` - Detects viral spikes
- `enhanced_spike_detection()` - Enhanced scoring with urgency + market validation
- `generate_viral_take_for_video()` - Generates spicy AI take for video
- `generate_viral_breaking_news_video()` - Creates 18-20 second video
- `stage_11b_breaking_news_jacker()` - Main orchestration

---

## 2. IS SPIKE DETECTION RUNNING?
**❌ NO - NO LOGS FOUND**

### Evidence:
- **0** `[SPIKE_DETECTED]` logs in run.log
- **0** `[11B]` logs in run.log (last 200 lines)
- **0** `[SPIKE_SKIP]` logs in run.log

### Spike Detection Logic:
- **Function:** `is_spiking_trend()` (lines 49-90)
- **Thresholds:**
  - `NEWS_SPIKE_MIN_TOTAL_POSTS = 40000` (minimum volume)
  - `NEWS_SPIKE_MAX_WINDOW_MIN = 90` (max time window)
  - `NEWS_SPIKE_MIN_GROWTH_FACTOR = 2.0` (2x growth required)
- **Keywords:** No specific keywords - uses volume/growth patterns

### Why It's Not Running:
1. **Stage 12 returns empty trends** - `get_cached_trends()` returns `[]`
2. **Stage 11B exits early** - `if not trends: return` (line 590-592)
3. **Exception swallowed** - Exception caught but may not log properly

---

## 3. IS VIDEO CREATION WORKING?
**⚠️ UNKNOWN - NO ATTEMPTS**

### Video Creation Function:
- **Function:** `generate_viral_breaking_news_video()` (lines 347-536)
- **Library:** Uses `generators/video_gen.py` OR `moviepy` fallback
- **Output:** Creates videos in `videos/breaking_news/` directory
- **Logs:** Should log `[VIDEO_GEN]` or `[VIDEO_CREATED]`

### Evidence:
- **0** `[VIDEO_GEN]` logs
- **0** `[VIDEO_CREATED]` logs
- **0** video generation attempts

### Why It's Not Running:
- Video generation only runs if `use_video = True` (line 659)
- Requires: `should_generate_video = True` AND `has_active_market = True`
- Requires: `spike_analysis['score'] >= 80` (line 139)

---

## 4. IS POSTING WORKING?
**⚠️ UNKNOWN - NO ATTEMPTS**

### Video Posting Function:
- **Function:** `force_original_post_immediately()` (social_agent.py lines 3570-3710)
- **Logs:** Should log `[VIDEO_POST]` or `[FORCE_POST]`
- **Path:** State → `_video_path` → Video posting infrastructure

### Evidence:
- **0** `[VIDEO_POST]` logs from Stage 11B
- **0** `[VIDEO_READY]` logs
- **0** `[BREAKING_NEWS_VIDEO_POSTED]` logs

### Note:
- Logs show `[VIDEO_POST] Video posting temporarily disabled` (Dec 22)
- But this is from `post_trending_video()` (Stage 16A), NOT Stage 11B

---

## 5. WHAT'S THE TRIGGER FLOW?

### Expected Flow:
```
Step 1: Stage 12 scans trends → caches in TRENDING_JACKER
   ↓
Step 2: bot_loop() calls Stage 11B → gets trends from cache
   ↓
Step 3: Stage 11B converts trends to dict format (with placeholders)
   ↓
Step 4: is_spiking_trend() checks each trend → returns (is_spike, score)
   ↓
Step 5: enhanced_spike_detection() scores trend → must score >= 80
   ↓
Step 6: map_trend_to_polymarket() checks relevance → confidence >= 0.75
   ↓
Step 7: generate_viral_take_for_video() creates AI take
   ↓
Step 8: generate_viral_breaking_news_video() creates video file
   ↓
Step 9: force_original_post_immediately() posts video to X
   ↓
Step 10: pin_tweet() + amplify_video_with_influencer_replies()
```

### Actual Flow (Based on Logs):
```
Step 1: Stage 12 runs (logs show "[STAGE 12] Starting trending scan...")
   ↓
Step 2: ❌ Stage 11B NEVER RUNS OR EXITS IMMEDIATELY
   (No [11B] logs, no [SPIKE_SKIP] logs, nothing)
```

---

## 6. WHY IS IT SILENT?

### TOP 1 REASON: **Stage 12 trends are empty or not passed to Stage 11B**

### Evidence:
1. **Stage 12 runs:** Logs show "[STAGE 12] Starting trending scan..." (Dec 20-21)
2. **But Stage 11A shows:** "[11A] [THREAD] No trends available from Stage 12" (Dec 20)
3. **Stage 11B check:** `if not trends: return` (line 590-592) - exits silently
4. **Cache issue:** `get_cached_trends()` returns `[]` if cache > 2 hours old

### Root Cause Analysis:

**Problem 1: Stage 12 cache expires**
- `get_cached_trends()` only returns trends if cache < 2 hours old (line 107)
- If Stage 12 doesn't scan successfully, cache becomes stale
- Stage 11B gets empty list → exits immediately

**Problem 2: Stage 12 may not be scanning successfully**
- Stage 12 uses X UI selectors that may have changed
- Timeouts are short (8 seconds) - may fail silently
- No trends found → empty cache → Stage 11B gets nothing

**Problem 3: Stage 11B exits silently**
- No logging when trends are empty (line 591)
- Exception caught but may not log properly (line 7474-7475)

### Other Potential Issues:

**Issue 2: Spike detection too strict**
- Requires: 40000+ volume, 2.0x growth, 90min window
- Placeholder trends may pass, but real trends from Stage 12 may not
- If trends don't pass → no candidates → exits silently

**Issue 3: Polymarket relevance check too strict**
- Requires: confidence >= 0.75
- If OpenAI returns low confidence → exits silently (line 650-652)

**Issue 4: Video threshold too high**
- Requires: `score >= 80` (line 139)
- Even with placeholders, score may not reach 80
- If score < 80 → `use_video = False` → falls back to text only

---

## 7. RELEVANT CODE SECTIONS

### Stage 11B Entry Point (social_agent.py:7443-7475):
```python
if stage_11b_breaking_news_jacker and openai_client:
    try:
        # Get trends from Stage 12 cache
        stage11b_trends = []
        if TRENDING_JACKER:
            stage11b_trends = TRENDING_JACKER.get_cached_trends() or []
        
        if stage11b_trends:  # ← IF THIS IS EMPTY, STAGE 11B NEVER RUNS
            # ... Stage 11B code ...
        # ← NO ELSE CLAUSE - SILENT EXIT IF NO TRENDS
    except Exception as e:
        log(f"[11B] Stage 11B error: {e}")
```

### Trend Conversion (breaking_news_11b.py:597-612):
```python
processed_trends = []
for trend in trends:
    if isinstance(trend, str):
        # Convert string to dict with placeholders
        processed_trends.append({
            "name": trend,
            "tweet_volume": 50000,  # Placeholder
            "history": [
                {"posts": 10000, "window_minutes": 30},
                {"posts": 50000, "window_minutes": 60}
            ],
        })
```

### Spike Detection (breaking_news_11b.py:616-625):
```python
is_spike, score = is_spiking_trend(
    trend,
    config_dict["NEWS_SPIKE_MIN_TOTAL_POSTS"],  # 40000
    config_dict["NEWS_SPIKE_MAX_WINDOW_MIN"],   # 90
    config_dict["NEWS_SPIKE_MIN_GROWTH_FACTOR"] # 2.0
)
```

### Video Threshold (breaking_news_11b.py:138-139):
```python
# VIDEO THRESHOLD: Only video if score >= 80
should_generate_video = base_score >= 80
```

---

## 8. RECOMMENDED FIXES

### Fix 1: Add logging when trends are empty
```python
if not stage11b_trends:
    log(f"[11B] No trends available from Stage 12 (cache empty or expired)")
    return  # Or continue without video generation
```

### Fix 2: Add logging in Stage 11B entry
```python
if not trends:
    print(f"{log_prefix} [SPIKE_SKIP] No trends available from Stage 12.")
    return
```

### Fix 3: Lower video threshold or add logging
- Current: `score >= 80` (very high)
- Suggested: `score >= 50` OR add logging when threshold not met

### Fix 4: Verify Stage 12 is caching trends correctly
- Check if `TRENDING_JACKER.get_cached_trends()` actually returns data
- Add logging to see what trends are passed to Stage 11B

### Fix 5: Make spike detection less strict for placeholder trends
- Current placeholders SHOULD pass (50000 volume, 5x growth)
- But real trends from Stage 12 may not have this data

---

## SUMMARY

**Does Stage 11B exist?** ✅ YES

**Which part is broken?** 🔴 **SPIKE DETECTION** (never runs - no trends)

**Why is it silent?** 🔴 **TOP 1 REASON: Stage 12 trends are empty, Stage 11B exits silently**

**Next Steps:**
1. Add logging to see if Stage 11B is called
2. Verify Stage 12 is caching trends correctly
3. Check if `get_cached_trends()` returns data
4. Add logging when trends are empty
5. Lower video threshold OR add logging when threshold not met

