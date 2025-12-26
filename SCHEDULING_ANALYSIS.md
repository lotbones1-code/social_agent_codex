# BOT SCHEDULING ANALYSIS & PROPOSED CHANGES

## CURRENT STATE ANALYSIS

### 1. ORIGINAL POST FREQUENCY CONTROL

**File:** `social_agent.py`

**Location 1: OriginalPostScheduler class (lines 2318-2412)**
- **Daily cap:** `posts_per_day_max: 8` (line 2333)
- **Daily min:** `posts_per_day_min: 6` (line 2332)
- **Minimum cooldown:** 300 seconds (5 minutes) between posts (line 2371)
- **Current scheduling logic (lines 2398-2406):**
  - Dynamically calculates `seconds_per_post = (hours_remaining * 3600) / posts_remaining`
  - Problem: If 4 posts remain and 8 hours left, this gives ~2 hours between posts (good)
  - Problem: If 1 post remains and 8 hours left, this gives 8 hours (too long)
  - Problem: If many posts at start of day, interval can be very short (bad)

**Location 2: Main loop original post check (lines 3695-3744)**
- Duplicate logic: Also checks `original_post_schedule.json` file
- Calls `post_original_content()` which uses `ORIGINAL_POST_SCHEDULER.should_post_now()`
- **Current interval on first post (line 2387):** 7200 seconds (2 hours) if `next_post_time == 0`

**Location 3: post_original_content() function (lines 2483-2590)**
- Calls `ORIGINAL_POST_SCHEDULER.should_post_now()` (line 2496)
- Also checks `HARDENING.can_post_original(max_posts_per_day=8)` (line 2500)

---

### 2. REPLY FREQUENCY CONTROL

**File:** `social_agent.py`

**Location 1: Main loop reply section (lines 3988-4190)**
- **No explicit per-cycle limit** - replies run continuously in loop
- **Target per search:** `REPLIES_PER_TERM` (random between min/max, not specified in visible code)
- **Rate limit:** `HARDENING.can_post_reply(max_replies_per_hour=8)` (line 1808)
- **Break logic:** After 5 consecutive actions, break 30-60 minutes (lines 3626-3632)

**Location 2: HARDENING rate limiting (bot_hardening.py, line 90)**
- `can_post_reply(max_replies_per_hour=8)` - hard limit of 8 replies/hour
- `record_reply()` tracks replies per hour

**Location 3: check_rate_limits() function (lines 567-588)**
- Global `action_count` tracks actions per hour
- `max_replies_per_hour: 8` from phase config (line 580)
- Resets every hour

---

### 3. MAIN LOOP EXECUTION ORDER (bot_loop function, lines 3591-4190)

**Current order:**
1. Sleep/safety checks (lines 3612-3633)
2. Phase controller (line 3637)
3. Daily cleanup (line 3641)
4. Strategy Brain (line 3659)
5. Analytics summary (line 3677)
6. **Stage 11A (Thread Builder)** (line 3684) ← Threads
7. Follow logic (line 3689)
8. **Original Posts** (line 3695) ← ORIGINALS CHECK HERE
9. Video scheduler (line 3746)
10. **Stage 12 (Trending Jacker)** (line 3785) ← Replies to trends
11. **Stage 11B (Breaking News)** (line 3950) ← BREAKING NEWS HERE
12. **Reply Loop (Intelligent Search)** (line 3988) ← MAIN REPLIES HERE

**Problem:** Original posts run BEFORE Stage 11B, so Stage 11B can be blocked by daily limit even though it has higher priority.

---

### 4. STAGE 11B (BREAKING NEWS) CONTROL

**File:** `breaking_news_11b.py` → `stage_11b_breaking_news_jacker()`

**Bypass mechanism:**
- Uses `force_original_post_immediately()` (line 2259 in social_agent.py)
- **Bypasses:** `ORIGINAL_POST_SCHEDULER.should_post_now()` ✅
- **Still checks:** `HARDENING.can_post_original(max_posts_per_day=20)` (line 2283) ← Higher limit for forced posts
- **Problem:** If `posts_today >= 20`, Stage 11B is blocked even though it should always be allowed

---

## PROPOSED CHANGES

### CHANGE 1: FIX ORIGINAL POST INTERVAL (60-90 minutes between posts)

**File:** `social_agent.py`

**Location:** `OriginalPostScheduler.mark_posted()` method (lines 2393-2412)

**Current logic:**
```python
posts_remaining = self.config["posts_per_day_max"] - self.config["posts_posted_today"]
if posts_remaining > 0:
    hours_remaining = max(4, 16 - (datetime.now().hour - 6))
    seconds_per_post = (hours_remaining * 3600) / posts_remaining
    next_interval = seconds_per_post + random.randint(-300, 300)
    self.config["next_post_time"] = time.time() + next_interval
```

**Proposed logic:**
```python
# Fixed interval: 60-90 minutes between posts (3600-5400 seconds)
# Add randomization: ±10 minutes (600 seconds)
MIN_INTERVAL_SECONDS = 3600  # 60 minutes
MAX_INTERVAL_SECONDS = 5400  # 90 minutes
next_interval = random.randint(MIN_INTERVAL_SECONDS, MAX_INTERVAL_SECONDS)
self.config["next_post_time"] = time.time() + next_interval
```

**Also update first post interval (line 2387):**
- **Current:** `current_time + 7200` (2 hours)
- **Proposed:** `current_time + random.randint(3600, 5400)` (60-90 minutes)

---

### CHANGE 2: KEEP DAILY CAP AT 6-8 POSTS (NO CHANGE NEEDED)

**File:** `social_agent.py`

**Current values are correct:**
- `posts_per_day_min: 6` (line 2332) ✅
- `posts_per_day_max: 8` (line 2333) ✅

**No changes needed here.**

---

### CHANGE 3: PRIORITIZE REPLIES (4 replies per 1 original)

**File:** `social_agent.py`

**Strategy:** Instead of limiting replies explicitly, adjust the loop order and break logic to favor replies.

**Current:** Replies happen after originals/11B, so originals can consume daily quota first.

**Proposed:** Move reply loop BEFORE original post check, so replies run first each cycle.

**Also:** Increase reply rate limits slightly to allow 4x replies vs originals.

**Location 1: Main loop order (lines 3682-3987)**
- **Current order:** Stage 11A → Original Posts → Stage 12 → Stage 11B → Reply Loop
- **Proposed order:** Stage 11A → **Reply Loop** → Stage 12 → Stage 11B → Original Posts (last)

**Location 2: Reply rate limits (lines 1808, 580)**
- **Current:** `max_replies_per_hour=8`
- **Target:** If 8 originals/day = ~0.33 originals/hour, then 4x = ~1.3 replies/hour needed
- **But:** Replies are bursty, not evenly distributed
- **Proposed:** Keep `max_replies_per_hour=8` but ensure replies run FIRST each cycle

**Location 3: Break logic (lines 3624-3632)**
- **Current:** Break after 5 consecutive actions (any type)
- **Proposed:** Track replies vs originals separately, or adjust to break after 10-15 replies

---

### CHANGE 4: ALWAYS ALLOW STAGE 11B (bypass all limits)

**File:** `social_agent.py`

**Location:** `force_original_post_immediately()` function (lines 2259-2316)

**Current code (line 2283):**
```python
if HARDENING and not HARDENING.can_post_original(max_posts_per_day=20):
    log(f"[FORCE_POST] ✗ Post blocked by rate limit from {source_stage}")
    return False
```

**Proposed code:**
```python
# Stage 11B breaking news should always be allowed (viral potential > scheduling)
if source_stage == "11B_BREAKING_NEWS":
    # Skip rate limit check for breaking news (always allow)
    log(f"[FORCE_POST] Stage 11B breaking news - bypassing rate limit check")
else:
    # For other forced posts, still check rate limit
    if HARDENING and not HARDENING.can_post_original(max_posts_per_day=20):
        log(f"[FORCE_POST] ✗ Post blocked by rate limit from {source_stage}")
        return False
```

**Also:** Move Stage 11B check to run BEFORE original posts in main loop (already identified in CHANGE 3).

---

### CHANGE 5: UPDATE MAIN LOOP ORDER

**File:** `social_agent.py`

**Location:** `bot_loop()` function (lines 3591-4190)

**Current order (lines 3682-3987):**
1. Stage 11A (Threads)
2. Follow logic
3. **Original Posts** ← TOO EARLY
4. Video scheduler
5. Stage 12 (Trending)
6. **Stage 11B (Breaking News)** ← AFTER ORIGINALS (bad)
7. **Reply Loop** ← TOO LATE

**Proposed new order:**
1. Stage 11A (Threads)
2. Follow logic
3. **Reply Loop (Intelligent Search)** ← MOVED UP (prioritize replies)
4. Stage 12 (Trending)
5. **Stage 11B (Breaking News)** ← MOVED UP (before originals)
6. **Original Posts** ← MOVED TO END (lowest priority)
7. Video scheduler

**Rationale:**
- Replies run first (4x priority vs originals)
- Stage 11B runs before originals (can bypass limits, higher viral potential)
- Originals run last (scheduled, lower priority)

---

## SUMMARY OF SPECIFIC VALUES TO CHANGE

### VALUES TO CHANGE:

1. **Original post interval (FIXED):**
   - **CURRENT:** Dynamic based on hours remaining / posts remaining
   - **NEW:** Fixed 60-90 minutes (3600-5400 seconds) with ±10 min randomization
   - **Location:** `OriginalPostScheduler.mark_posted()` line 2405-2406
   - **Also:** First post interval (line 2387): `7200` → `random.randint(3600, 5400)`

2. **Daily cap (NO CHANGE):**
   - **CURRENT:** 6-8 posts/day ✅
   - **NEW:** 6-8 posts/day (keep as-is)

3. **Reply rate limit (NO CHANGE):**
   - **CURRENT:** 8 replies/hour ✅
   - **NEW:** 8 replies/hour (keep as-is, but prioritize replies in loop order)

4. **Stage 11B bypass (ENHANCE):**
   - **CURRENT:** Checks `HARDENING.can_post_original(max_posts_per_day=20)` 
   - **NEW:** Skip rate limit check entirely for `source_stage == "11B_BREAKING_NEWS"`
   - **Location:** `force_original_post_immediately()` line 2283

5. **Main loop order (REORDER):**
   - **CURRENT:** Stage 11A → Original Posts → Stage 12 → Stage 11B → Reply Loop
   - **NEW:** Stage 11A → Reply Loop → Stage 12 → Stage 11B → Original Posts
   - **Location:** `bot_loop()` lines 3682-3987

6. **Minimum cooldown (NO CHANGE):**
   - **CURRENT:** 300 seconds (5 minutes) ✅
   - **NEW:** 300 seconds (keep as-is, but fixed interval handles spacing better)

---

## FILES TO MODIFY

1. `social_agent.py`:
   - `OriginalPostScheduler.mark_posted()` method (lines 2393-2412)
   - `OriginalPostScheduler.should_post_now()` method (line 2387)
   - `force_original_post_immediately()` function (lines 2259-2316)
   - `bot_loop()` function (lines 3682-3987) - reorder execution

---

## RISK ASSESSMENT

**Low Risk:**
- Changing interval calculation (only affects timing, not logic)
- Reordering main loop (no code deletion, just moving blocks)

**Medium Risk:**
- Removing rate limit check for Stage 11B (could theoretically post many times, but Stage 11B has its own daily quota: `NEWS_MAX_FORCED_POSTS_PER_DAY = 5`)

**Mitigation:**
- Stage 11B has internal limits (`NEWS_MAX_FORCED_POSTS_PER_DAY`, `NEWS_MIN_HOURS_BETWEEN_POSTS`) that will still prevent spam
- Fixed interval prevents posts clustering at start of day

---

## EXPECTED BEHAVIOR AFTER CHANGES

1. **Originals:** Post every 60-90 minutes, max 6-8 per day, evenly spread
2. **Replies:** Run first each cycle, target ~4 replies per original posted (organic via loop order)
3. **Stage 11B:** Always posts when triggered, even if originals are at daily limit
4. **Loop order:** Replies → 11B → Originals (priority order)

