# REPLY LIMITING ANALYSIS

## CURRENT STATE

### 1. MAIN LIMITER: `REPLIES_PER_TERM`

**Location:** `social_agent.py` line 312
```python
REPLIES_PER_TERM = (1, 2)
```

**Impact:** The bot only attempts **1-2 replies per search cycle**. This is the PRIMARY bottleneck.

**Usage:** Line 3745
```python
target = random.randint(*REPLIES_PER_TERM)  # Random between 1-2
```

**Problem:** With target of 1-2, even if 20 cards are found, the loop breaks after 1-2 successful replies.

---

### 2. TARGETING LOGIC: `should_target_for_reply()`

**Location:** `social_agent.py` lines 1691-1788

#### Current Filters:

**A. Engagement Filter (Line 1758-1760):**
```python
# NEW FILTER: Skip if engagement < 3 (very low engagement)
if engagement > 0 and engagement < 3:
    log(f"[TARGETING] Skipped - low engagement (engagement={engagement})")
    return False, "low-engagement"
```
- **Threshold:** Engagement must be >= 3 (if engagement is detected)
- **Problem:** This can skip tweets with 1-2 likes/retweets even if they're relevant

**B. Follower Filter (Line 1763-1765):**
```python
# UPDATED: Only skip if followers < 10 (very low threshold)
if follower_count > 0 and follower_count < 10:
    log(f"[TARGETING] Skipped - very low followers (followers={follower_count})")
    return False, "low-followers"
```
- **Threshold:** Followers must be >= 10 (if follower count is detected)
- **Status:** ✅ This is reasonable (only blocks very low follower accounts)

**C. Content Matching (Line 1718):**
```python
content_matches = any(kw in account_text_lower for kw in keywords)
```
- **Keywords:** polymarket, prediction market, betting odds, odds, trump odds, biden odds, election odds, etc.
- **Problem:** Only replies if tweet contains these keywords
- **Fallback:** If content doesn't match, function defaults to `return True, "default-allow"` (line 1783), BUT this only happens if no earlier tier matched

**D. Tier System:**
1. **Tier 1:** content_matches + followers >= 50 → ✅ True
2. **Tier 2:** content_matches + followers >= 20 → ✅ True
3. **Tier 3:** content_matches (any followers >= 10) → ✅ True
4. **Default:** ✅ True (allows if no strong signal against)

**Analysis:** The function DOES default to allowing, but the issue is that it prioritizes content_matches first. If a tweet doesn't match keywords, it might still pass, but only after checking tiers.

---

### 3. OTHER FILTERS THAT LIMIT REPLIES

**A. Duplicate Check (Line 3752-3753):**
```python
if not tid or tid in dedup_tweets:
    continue
```
- **Status:** ✅ Necessary (prevents duplicate replies)

**B. Stage 10 Quality Filter (Line 2030-2032):**
```python
if not poly_intel.has_betting_substance(tweet_text):
    log(f"[STAGE 10] ✗ Skipping reply - tweet lacks betting/prediction substance")
```
- **Impact:** Only affects Stage 10 replies (Polymarket mentions), not general replies
- **Status:** ✅ Appropriate filter for Stage 10

**C. Rate Limits:**
- `HARDENING.can_post_reply(max_replies_per_hour=8)` (line 1808)
- **Status:** ✅ Reasonable (8 replies/hour = ~1 reply every 7.5 minutes)

**D. MAX_ARTICLES_SCAN (Line 315):**
```python
MAX_ARTICLES_SCAN = 20
```
- **Status:** ✅ Reasonable (scans up to 20 cards per cycle)

---

## ROOT CAUSE ANALYSIS

### Why Only 2 Replies Per Cycle?

1. **PRIMARY BOTTLENECK:** `REPLIES_PER_TERM = (1, 2)` limits to 1-2 replies per cycle
2. **Secondary:** Engagement filter (< 3) may skip some relevant tweets
3. **Secondary:** Content matching prioritizes keyword matches, but does allow non-matches via default

---

## PROPOSED CHANGES

### CHANGE 1: Increase `REPLIES_PER_TERM` (CRITICAL)

**Current:**
```python
REPLIES_PER_TERM = (1, 2)
```

**Proposed:**
```python
REPLIES_PER_TERM = (4, 6)  # Target 4-6 replies per cycle (matches 4 replies per 1 original goal)
```

**Location:** Line 312

**Rationale:** If we want 4-6 replies per cycle, the target must be 4-6. Currently it's hard-limited to 1-2.

---

### CHANGE 2: Lower/Remove Engagement Filter (OPTIONAL)

**Current:**
```python
# NEW FILTER: Skip if engagement < 3 (very low engagement)
if engagement > 0 and engagement < 3:
    log(f"[TARGETING] Skipped - low engagement (engagement={engagement})")
    return False, "low-engagement"
```

**Option A - Remove entirely:**
```python
# REMOVED: Engagement filter - allow tweets with any engagement (or no engagement detected)
```

**Option B - Lower threshold:**
```python
# Lower threshold: Only skip if engagement is 0 (no engagement at all)
if engagement == 0:
    log(f"[TARGETING] Skipped - no engagement detected (engagement={engagement})")
    return False, "no-engagement"
```

**Option C - Make it less strict:**
```python
# Only skip if engagement is detected AND is 0 (don't skip if we can't detect engagement)
if engagement > 0 and engagement < 1:  # Skip only if we detected 0 engagement
    log(f"[TARGETING] Skipped - zero engagement (engagement={engagement})")
    return False, "zero-engagement"
```

**Recommendation:** **Option A (Remove entirely)** - Engagement can be misleading (new tweets haven't had time to accumulate engagement, but might be relevant).

**Location:** Lines 1757-1760

---

### CHANGE 3: Add Fallback for Prediction Market Posts (OPTIONAL)

**Current:** Function defaults to allowing if no strong signal against, but prioritizes content_matches.

**Proposed:** Add explicit fallback for prediction market related posts that don't match exact keywords.

**Add after line 1776 (before default-allow):**
```python
# Fallback: If topic contains prediction market keywords, allow even without content match
topic_lower = topic.lower() if topic else ""
prediction_keywords_in_topic = any(kw in topic_lower for kw in ["prediction", "betting", "odds", "polymarket", "market"])
if prediction_keywords_in_topic:
    log(f"[TARGETING] ✓ Fallback: Topic-related post (topic={topic}, followers={follower_count})")
    return True, "topic-fallback"
```

**Rationale:** If the search term is prediction-market related, posts in results are likely relevant even without exact keyword match.

**Location:** After line 1776, before line 1782

---

## RECOMMENDED CHANGES (Priority Order)

### **HIGH PRIORITY (Required for 4-6 replies):**
1. **Change `REPLIES_PER_TERM` from `(1, 2)` to `(4, 6)`** (Line 312)

### **MEDIUM PRIORITY (May help find more targets):**
2. **Remove engagement filter** (Lines 1757-1760) - Allow tweets with any engagement level

### **LOW PRIORITY (Nice to have):**
3. **Add topic-based fallback** (After line 1776) - Allow posts related to search topic

---

## EXPECTED IMPACT

### With Change 1 Only (`REPLIES_PER_TERM = (4, 6)`):
- **Before:** 1-2 replies per cycle
- **After:** 4-6 replies per cycle
- **Impact:** 2-3x increase in reply attempts

### With Changes 1 + 2 (Remove engagement filter):
- **Before:** 1-2 replies per cycle, some skipped due to low engagement
- **After:** 4-6 replies per cycle, no engagement-based skips
- **Impact:** More targets available, higher success rate

### With All 3 Changes:
- **Before:** 1-2 replies per cycle, strict filtering
- **After:** 4-6 replies per cycle, relaxed filtering, topic-based fallback
- **Impact:** Maximum reply volume while maintaining relevance

---

## RISK ASSESSMENT

**Low Risk:**
- Increasing `REPLIES_PER_TERM` to 4-6 is safe (rate limits still apply: 8/hour)

**Medium Risk:**
- Removing engagement filter may target lower-quality tweets, but function still defaults to allow anyway

**Mitigation:**
- Existing filters still apply (duplicates, Stage 10 quality, rate limits)
- `should_target_for_reply()` still checks for followers >= 10
- Content relevance still prioritized when detected

---

## SUMMARY

**Current State:**
- `REPLIES_PER_TERM = (1, 2)` ← **PRIMARY LIMITER**
- Engagement filter (< 3) may skip some tweets
- Content matching prioritizes keywords but defaults to allow

**Proposed:**
1. **Change `REPLIES_PER_TERM` to `(4, 6)`** ← **MUST DO**
2. Remove engagement filter (optional, but recommended)
3. Add topic-based fallback (optional)

**Result:** Bot will attempt 4-6 replies per cycle instead of 1-2.

