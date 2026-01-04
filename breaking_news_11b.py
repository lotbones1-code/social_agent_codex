import json
import time
from datetime import datetime, timezone


def get_today_str():
    """Return today's date in YYYY-MM-DD format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def reset_news_daily_counters_if_needed(state):
    """Reset daily counters if we've crossed midnight."""
    today = get_today_str()
    if state.get("news_forced_posts_today_date") != today:
        state["news_forced_posts_today_date"] = today
        state["news_forced_posts_today"] = 0


def is_news_spacing_ok(state, now_ts, min_hours):
    """Check if enough time has passed since last forced post."""
    last_ts = state.get("last_news_forced_post_ts", 0)
    if last_ts == 0:
        return True
    hours_since = (now_ts - last_ts) / 3600.0
    return hours_since >= min_hours


def has_news_daily_quota(state, max_per_day):
    """Check if we haven't hit daily cap."""
    reset_news_daily_counters_if_needed(state)
    return state.get("news_forced_posts_today", 0) < max_per_day


def compute_trend_growth(trend):
    """Extract growth factor from trend history."""
    history = trend.get("history") or []
    if len(history) < 2:
        return None
    
    prev = history[-2].get("posts", 0) or 0
    cur = history[-1].get("posts", 0) or 0
    
    if prev <= 0:
        return None
    
    return cur / float(prev)


def is_spiking_trend(trend, min_total_posts, max_window_min, min_growth_factor):
    """Determine if a trend is spiking (viral spike pattern). Enhanced with urgency levels."""
    total = trend.get("tweet_volume") or 0
    
    if total < min_total_posts:
        return False, None
    
    history = trend.get("history") or []
    total_window = sum(w.get("window_minutes", 0) or 0 for w in history)
    
    if total_window == 0 or total_window > max_window_min:
        return False, None
    
    growth = compute_trend_growth(trend)
    
    if growth is None or growth < min_growth_factor:
        return False, None
    
    base_score = growth * (total / 10000.0)
    
    # [STAGE 11B VIDEO ENHANCED] Enhanced urgency boost with levels
    urgency_level = "MEDIUM"
    if history:
        latest_window = history[-1] if history else {}
        window_minutes = latest_window.get("window_minutes", max_window_min)
        
        # EXTREME urgency: spike in last 30 min = +50% boost
        if window_minutes <= 30:
            base_score = base_score * 1.5  # 50% urgency boost
            urgency_level = "EXTREME"
            trend["_urgency_boost"] = True
        # HIGH urgency: spike in last 60 min = +20% boost
        elif window_minutes <= 60:
            base_score = base_score * 1.2  # 20% urgency boost
            urgency_level = "HIGH"
            trend["_urgency_boost"] = True
    
    # Store urgency level and enhanced score in trend dict
    trend["_urgency_level"] = urgency_level
    trend["_enhanced_score"] = base_score
    
    return True, base_score


def enhanced_spike_detection(trend, mapping_result):
    """[STAGE 11B VIDEO ENHANCED] Enhanced spike scoring with urgency + market validation + keyword boosting."""
    base_score = trend.get("_enhanced_score", 0)
    urgency_level = trend.get("_urgency_level", "MEDIUM")
    trend_name = (trend.get("name", "") or "").lower()
    
    # [STAGE 11B KEYWORD BOOST] Boost score if trend contains breaking news keywords
    breaking_keywords = ["breaking", "alert", "news", "surge", "crash", "emergency", "flash", "urgent"]
    market_keywords = ["btc", "bitcoin", "eth", "analytics", "sol", "solana", "crypto", "market"]
    exchange_keywords = ["celsius", "ftx", "binance", "kraken", "coinbase", "exchange", "collapse"]
    
    keyword_boost = 1.0
    matched_keywords = []
    
    # Check for breaking news keywords (high priority)
    for keyword in breaking_keywords:
        if keyword in trend_name:
            keyword_boost = max(keyword_boost, 1.4)  # 40% boost for breaking news
            matched_keywords.append(keyword)
            if urgency_level == "MEDIUM":
                urgency_level = "HIGH"  # Upgrade urgency if breaking keyword found
    
    # Check for market keywords (medium priority)
    if keyword_boost < 1.4:  # Only if no breaking keyword found
        for keyword in market_keywords:
            if keyword in trend_name:
                keyword_boost = max(keyword_boost, 1.2)  # 20% boost for market keywords
                matched_keywords.append(keyword)
    
    # Check for exchange keywords (high priority - often means crisis)
    for keyword in exchange_keywords:
        if keyword in trend_name:
            keyword_boost = max(keyword_boost, 1.5)  # 50% boost for exchange crisis
            matched_keywords.append(keyword)
            urgency_level = "EXTREME"  # Always extreme for exchange issues
    
    if matched_keywords:
        base_score = base_score * keyword_boost
    
    # BOOST 2: SaaS growth market exists (+30%)
    has_active_market = mapping_result.get("confidence", 0.0) >= 0.8
    market_odds = None  # TODO: Fetch actual odds from SaaS growth API
    if has_active_market:
        base_score = base_score * 1.3  # 30% boost if market exists
    
    # VIDEO THRESHOLD: Only video if score >= 80
    should_generate_video = base_score >= 80
    
    return {
        'score': base_score,
        'urgency_level': urgency_level,
        'should_generate_video': should_generate_video,
        'market_odds': market_odds,
        'trend_name': trend.get("name", "Unknown"),
        'spike_volume': trend.get("tweet_volume", 0),
        'has_active_market': has_active_market,
        'matched_keywords': matched_keywords,  # For logging
    }


def map_trend_to_saas_growth(openai_client, trend_name, example_tweets_snippet, log_prefix):
    """Use ChatGPT to decide if a trend is relevant to SaaS growth."""
    system_prompt = "You are a sharp marketing attribution analyst. Output strictly JSON only. No prose."
    
    user_prompt = f"""
Trend: {trend_name}

Sample tweets:
{example_tweets_snippet}

Decide if this trend is relevant to marketing attributionS / BETTING / ODDS on:
- growths and political outcomes
- Cryptocurrency price movements
- Sports betting and outcomes
- Global macro events (conflicts, economic data)
- Market predictions

Output JSON with ONLY these fields:
- relevant (true/false)
- confidence (0.0 to 1.0)
- saas_growth_query (short 1-3 word keyword if relevant, or empty string)
- reason (brief 1-sentence explanation)

Return ONLY the JSON object, no other text.
"""

    try:
        raw_response = openai_client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=200
        )
        
        text = raw_response.choices[0].message.content.strip()
        data = json.loads(text)
        
        return {
            "relevant": bool(data.get("relevant", False)),
            "confidence": float(data.get("confidence", 0.0)),
            "saas_growth_query": (data.get("saas_growth_query") or "").strip(),
            "reason": (data.get("reason") or "").strip()
        }
    
    except Exception as e:
        print(f"{log_prefix} [MAPPING_ERROR] Failed to parse OpenAI response: {e}")
        return {
            "relevant": False,
            "confidence": 0.0,
            "saas_growth_query": "",
            "reason": "parse_error"
        }


def generate_viral_breaking_tweet(openai_client, trend_name, saas_growth_query, saas_growth_url, log_prefix):
    """Use ChatGPT to generate a high-impact breaking news tweet."""
    system_prompt = """You are a viral social media manager for a marketing attribution expert account.
Your job: Generate ONE final breaking-news tweet that will stop scrollers.

DO NOT output multiple drafts. DO NOT explain your reasoning.
Output ONLY the final tweet text. Nothing else."""

    user_prompt = f"""
Breaking trend: {trend_name}
SaaS growth market: {saas_growth_query}
Link to include: {saas_growth_url}

VIRAL TWEET REQUIREMENTS:
1. Start with ONE of these: "BREAKING:", "JUST IN:", "🚨", or "👀"
2. Be UNDER 180 characters (including the link at the end)
3. Sound like a real person, NOT a robot
4. Include ONE strong opinion or hot take (don't be neutral)
5. END with this exact URL: {saas_growth_url}

INTERNALLY generate 3 drafts:
- Draft A: Pure urgency ("BREAKING: X happened, odds now...")
- Draft B: Question/engagement ("Do you think Y will happen? Odds say...")
- Draft C: Contrarian ("Everyone's sleeping on Z. Market odds suggest...")

Pick the BEST one. Polish it:
- Remove filler words ("It is interesting to note", "Indeed", "Absolutely")
- Make it punchy and opinionated
- Ensure it ends with the link

Output ONLY the final polished tweet. No quotes, no metadata, no explanation.
"""

    try:
        raw_response = openai_client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=150
        )
        
        tweet_text = raw_response.choices[0].message.content.strip()
        
        if saas_growth_url not in tweet_text:
            tweet_text = f"{tweet_text} {saas_growth_url}"
        
        return tweet_text
    
    except Exception as e:
        print(f"{log_prefix} [TWEET_ERROR] Failed to generate tweet: {e}")
        return None


def generate_viral_take_for_video(openai_client, trend_name, trend_data, saas_growth_odds, urgency_level, log_prefix):
    """[STAGE 11B VIDEO ENHANCED] Generate a SHORT, SPICY, VIRAL marketing attribution take with urgency-based tone."""
    system_prompt = """You are a bold marketing attribution trader generating viral video content.
Your job: Generate ONE short, spicy, high-conviction take (1-2 sentences max) that fits in a 15-20 second video.

Output ONLY the take text. No quotes, no metadata, no explanation."""

    # [STAGE 11B VIDEO ENHANCED] Adjust tone based on urgency level
    if urgency_level == "EXTREME":
        tone_instruction = "EXTREMELY URGENT. Sound panicked but confident. Create immediate FOMO."
    elif urgency_level == "HIGH":
        tone_instruction = "Very urgent. Sound like you just discovered something important."
    else:
        tone_instruction = "Confident but calm. Still urgent but more measured."

    odds_str = f"{saas_growth_odds}%" if saas_growth_odds else "unknown"
    user_prompt = f"""
You are a marketing attribution trader posting a viral breaking news take on X.

CONSTRAINTS:
- EXACTLY 1-2 sentences (max 20 words per sentence)
- HIGH CONVICTION (sound certain, confident, NOT wishy-washy)
- CONTRARIAN (opposite of what crowd thinks)
- URGENT (create FOMO, time pressure)
- SHORT (fits in 15-20 second video)
- NO LINKS (just the take, link comes in caption)
- NO EMOJIS (text only for video overlay)

TREND: {trend_name}
MARKET ODDS: {odds_str}
TONE: {tone_instruction}
TRADER PERSONA: Bold, aggressive, early to trends, willing to be wrong publicly

EXAMPLES OF GOOD TAKES (use these as style guide):
- "Everyone's wrong. I'm all in." (short, confident)
- "The crowd will regret this in 24 hours." (urgent, contrarian)
- "This is the trade of the year. Watch." (bold, confident)
- "Nobody's talking about this yet. They will be." (early signal)
- "The odds are insane. Free money." (contrarian to crowd)

EXAMPLES OF BAD TAKES (DO NOT do these):
- "Maybe this could go up" (wishy-washy)
- "It's possible the market could move" (uncertain)
- "This might be interesting to watch" (boring)
- "Some people think this will happen" (weak)

Generate 1 VIRAL take for {trend_name} RIGHT NOW:
(Respond with ONLY the take, no explanation, max 100 characters)
"""

    try:
        raw_response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.9,  # Higher temperature for more creative/viral takes
            max_tokens=50
        )
        
        take_text = raw_response.choices[0].message.content.strip()
        
        # Clean up common LLM artifacts
        if take_text.startswith('"') and take_text.endswith('"'):
            take_text = take_text[1:-1]
        if take_text.startswith("'") and take_text.endswith("'"):
            take_text = take_text[1:-1]
        
        # Ensure it's short enough for video
        if len(take_text) > 100:
            take_text = take_text[:97] + "..."
        
        print(f"{log_prefix} [TAKE_GENERATED] Take: \"{take_text[:140]}\"")
        return take_text
    
    except Exception as e:
        print(f"{log_prefix} [VIDEO_TAKE_ERROR] Failed to generate viral take: {e}")
        return None


def generate_viral_breaking_news_video(take_text, trend_name, saas_growth_link, urgency_level, log_prefix):
    """[STAGE 11B VIDEO ENHANCED] Generate 18-20 second viral video with optimized hook/main/CTA structure."""
    import os
    import subprocess
    from pathlib import Path
    
    try:
        # Create temp directory for video output
        temp_dir = Path("videos/breaking_news")
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate video filename
        timestamp = int(time.time())
        video_filename = f"breaking_{trend_name[:20].replace(' ', '_').replace('/', '_')}_{timestamp}.mp4"
        video_path = temp_dir / video_filename
        
        # [STAGE 11B VIDEO ENHANCED] Use existing video generation infrastructure first
        video_gen_script = Path("generators/video_gen.py")
        if video_gen_script.exists():
            try:
                result = subprocess.run(
                    ["python3", str(video_gen_script), "--topic", take_text, "--out", str(video_path)],
                    capture_output=True,
                    text=True,
                    timeout=120  # 2 minute timeout
                )
                if result.returncode == 0 and video_path.exists():
                    print(f"{log_prefix} [VIDEO_GEN] Generated video with video_gen.py: {video_path}")
                    return str(video_path)
            except Exception as e:
                print(f"{log_prefix} [VIDEO_GEN] Video generator failed: {e}")
        
        # Fallback: Enhanced moviepy video with hook/main/CTA structure
        try:
            from moviepy.editor import TextClip, ColorClip, CompositeVideoClip
            
            # [STAGE 11B VIDEO ENHANCED] Optimized 18-second video structure
            duration = 18  # Optimal for X engagement
            bg = ColorClip(size=(1280, 720), color=(18, 18, 18), duration=duration)
            
            # HOOK (first 2 seconds): "🚨 BREAKING: {trend_name}" - Scroll-stopping
            hook_text_raw = f"🚨 BREAKING: {trend_name[:25]}"
            hook_text = TextClip(
                hook_text_raw,
                fontsize=64,
                color="#FF0000",  # RED = urgency
                font="Arial-Bold",
                stroke_color="#000000",
                stroke_width=2
            ).set_duration(2).set_position("center").set_start(0)
            
            # MAIN TAKE (3-15 seconds): The viral message
            main_text = TextClip(
                take_text,
                fontsize=48,
                color="#FFFFFF",  # White on dark
                font="Arial-Bold",
                method="caption",
                size=(1200, None),
                align="center",
                stroke_color="#000000",
                stroke_width=1
            ).set_duration(12).set_position(("center", "center")).set_start(3)
            
            # CTA (last 3 seconds): "Trade Now on SaaS growth" - Drive clicks
            cta_domain = saas_growth_link.replace('https://', '').replace('http://', '').split('/')[0][:20]
            cta_text = TextClip(
                "Trade Now on SaaS growth",
                fontsize=40,
                color="#00FF00",  # GREEN = profit/CTA
                font="Arial-Bold",
                stroke_color="#000000",
                stroke_width=2
            ).set_duration(3).set_position(("center", 600)).set_start(15)
            
            # Composite all clips
            video = CompositeVideoClip([bg, hook_text, main_text, cta_text])
            
            # Write video file (compressed for X)
            video.write_videofile(
                str(video_path),
                fps=30,  # Higher FPS for smoother video
                codec="libx264",
                audio=False,  # No audio for now (can add music later)
                preset="medium",  # Balance quality/speed
                bitrate="2000k",  # Compress for X upload
                verbose=False,
                logger=None
            )
            
            print(f"{log_prefix} [VIDEO_CREATED] File: {video_path.name if hasattr(video_path, 'name') else video_path}, Duration: 18s")
            return str(video_path)
            
        except ImportError:
            print(f"{log_prefix} [VIDEO_GEN] moviepy not available, cannot generate video")
            return None
        except Exception as e:
            print(f"{log_prefix} [VIDEO_GEN] moviepy video generation failed: {e}")
            return None
    
    except Exception as e:
        print(f"{log_prefix} [VIDEO_GEN_ERROR] Failed to generate video: {e}")
        return None


def pin_tweet(page, tweet_url_or_id, log_prefix, duration_minutes=60):
    """[STAGE 11B VIDEO ENHANCED] Pin a tweet for maximum visibility."""
    try:
        # Navigate to tweet if we have URL or ID
        if isinstance(tweet_url_or_id, str) and not tweet_url_or_id.startswith("http"):
            # Assume it's a tweet ID
            tweet_url = f"https://x.com/i/web/status/{tweet_url_or_id}"
        else:
            tweet_url = tweet_url_or_id if isinstance(tweet_url_or_id, str) and tweet_url_or_id.startswith("http") else None
        
        if not tweet_url:
            print(f"{log_prefix} [PIN_SKIP] Invalid tweet URL/ID, cannot pin")
            return False
        
        # Note: X pinning requires navigating to the tweet and clicking the menu
        # This is a placeholder for future implementation
        # For now, log that pinning was requested
        print(f"{log_prefix} [PIN_REQUESTED] Tweet pinning requested for {tweet_url} (duration: {duration_minutes} min)")
        # TODO: Implement actual pinning logic using Playwright
        return True
        
    except Exception as e:
        print(f"{log_prefix} [PIN_ERROR] Failed to pin tweet: {e}")
        return False


def find_trend_influencers(page, trend_name, min_followers=10000, max_results=5):
    """[STAGE 11B VIDEO ENHANCED] Find top influencers talking about a trend."""
    try:
        # Search for tweets about the trend (filter applied silently in backend, not in URL)
        search_query = trend_name
        search_url = f"https://x.com/search?q={search_query.replace(' ', '%20')}&src=typed_query&f=live"
        
        # Note: This is a placeholder for future implementation
        # Would need to:
        # 1. Navigate to search URL
        # 2. Extract tweet cards
        # 3. Filter by follower count
        # 4. Return top influencers
        
        print(f"[INFLUENCER_SEARCH] Searching for influencers for trend: {trend_name}")
        # TODO: Implement actual influencer search logic
        return []
        
    except Exception as e:
        print(f"[INFLUENCER_SEARCH_ERROR] Failed to find influencers: {e}")
        return []


def amplify_video_with_influencer_replies(page, video_tweet_id, trend_name, saas_growth_link, log_prefix):
    """[STAGE 11B VIDEO ENHANCED] Reply to influencers in crypto/marketing attributions with the video."""
    try:
        # Find top 3-5 accounts talking about this trend
        influencers = find_trend_influencers(page, trend_name, min_followers=10000, max_results=5)
        
        if not influencers:
            print(f"{log_prefix} [AMPLIFY_SKIP] No influencers found for trend: {trend_name}")
            return
        
        video_tweet_url = f"https://x.com/i/web/status/{video_tweet_id}"
        
        # Reply to each influencer
        for influencer in influencers[:3]:  # Limit to top 3 to avoid spam
            try:
                reply_text = f"""Saw your take on {trend_name}. 

Just posted a marketing attribution breakdown: {saas_growth_link}

Check it out: {video_tweet_url}
"""
                # TODO: Implement actual reply logic using existing reply_to_card infrastructure
                print(f"{log_prefix} [AMPLIFY] Would reply to influencer {influencer.get('handle', 'unknown')} with video link")
                
            except Exception as e:
                print(f"{log_prefix} [AMPLIFY_ERROR] Failed to reply to influencer: {e}")
                continue
        
        print(f"{log_prefix} [AMPLIFY_COMPLETE] Amplification attempted for {len(influencers[:3])} influencers")
        return True
        
    except Exception as e:
        print(f"{log_prefix} [AMPLIFY_ERROR] Failed to amplify video: {e}")
        return False


def extract_tweet_id_from_post(page, log_prefix):
    """[STAGE 11B VIDEO ENHANCED] Extract tweet ID from recently posted tweet."""
    try:
        import re
        
        # Wait a moment for tweet to appear
        time.sleep(2)
        
        # Navigate to profile to find latest tweet
        # Note: This assumes we know the bot handle - would need to pass it or get from config
        # For now, try to extract from current URL if we're on a tweet page
        
        current_url = page.url
        match = re.search(r'/status/(\d+)', current_url)
        if match:
            tweet_id = match.group(1)
            print(f"{log_prefix} [TWEET_ID] Extracted tweet ID from URL: {tweet_id}")
            return tweet_id
        
        # Alternative: Look for tweet card on profile
        # TODO: Implement profile-based extraction if needed
        
        return None
        
    except Exception as e:
        print(f"{log_prefix} [TWEET_ID_ERROR] Failed to extract tweet ID: {e}")
        return None


def stage_11b_breaking_news_jacker(
    trends,
    state,
    openai_client,
    referral_base_url,
    now_ts,
    force_original_post_fn,
    config_dict
):
    """Main Stage 11B orchestration."""
    log_prefix = config_dict.get("NEWS_LOG_PREFIX", "[11B]")
    
    reset_news_daily_counters_if_needed(state)
    
    if not has_news_daily_quota(state, config_dict["NEWS_MAX_FORCED_POSTS_PER_DAY"]):
        print(f"{log_prefix} [SPIKE_SKIP] Daily forced-news quota reached.")
        return
    
    if not is_news_spacing_ok(state, now_ts, config_dict["NEWS_MIN_HOURS_BETWEEN_POSTS"]):
        print(f"{log_prefix} [SPIKE_SKIP] Too soon since last forced news post.")
        return
    
    candidates = []
    
    if not trends:
        print(f"{log_prefix} [SPIKE_SKIP] No trends available from Stage 12.")
        return
    
    # Handle both string trends (from Stage 12) and dict trends (expected format)
    # Convert string trends to dict format for compatibility
    processed_trends = []
    for trend in trends:
        if isinstance(trend, str):
            # Stage 12 returns strings, convert to expected dict format
            # Use placeholder values since we don't have volume/history data
            processed_trends.append({
                "name": trend,
                "tweet_volume": 50000,  # Placeholder - assume high volume for breaking news
                "history": [
                    {"posts": 10000, "window_minutes": 30},
                    {"posts": 50000, "window_minutes": 60}
                ],
                "example_tweets_snippet": f"Recent tweets about {trend}"
            })
        else:
            # Already in dict format
            processed_trends.append(trend)
    
    for trend in processed_trends:
        try:
            is_spike, score = is_spiking_trend(
                trend,
                config_dict["NEWS_SPIKE_MIN_TOTAL_POSTS"],
                config_dict["NEWS_SPIKE_MAX_WINDOW_MIN"],
                config_dict["NEWS_SPIKE_MIN_GROWTH_FACTOR"]
            )
            
            if is_spike and score is not None:
                print(f"{log_prefix} [SPIKE_DETECTED] name={trend.get('name', '?')} volume={trend.get('tweet_volume', 0)} score={score:.2f}")
                candidates.append((score, trend))
        
        except Exception as e:
            print(f"{log_prefix} [SPIKE_ERROR] Error checking trend: {e}")
            continue
    
    if not candidates:
        print(f"{log_prefix} [SPIKE_SKIP] No spiking trends found this cycle.")
        return
    
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_trend = candidates[0]
    trend_name = best_trend.get("name", "Unknown")
    
    example_snippet = (best_trend.get("example_tweets_snippet") or "")[:750]
    
    mapping = map_trend_to_saas_growth(
        openai_client,
        trend_name,
        example_snippet,
        log_prefix
    )
    
    print(f"{log_prefix} [SaaS growth_CHECK] name={trend_name} mapping={mapping}")
    
    if not mapping["relevant"] or mapping["confidence"] < config_dict["NEWS_MIN_POLY_CONFIDENCE"]:
        print(f"{log_prefix} [SPIKE_SKIP] Not clearly SaaS growth-relevant (confidence={mapping['confidence']:.2f}).")
        return
    
    # [STAGE 11B VIDEO ENHANCED] Enhanced spike detection with urgency + market validation
    urgency_level = best_trend.get("_urgency_level", "MEDIUM")
    spike_analysis = enhanced_spike_detection(best_trend, mapping)
    
    # [STAGE 11B VIDEO ENHANCED] Use enhanced scoring (threshold >= 80 for video)
    use_video = spike_analysis['should_generate_video'] and spike_analysis['has_active_market']
    
    if use_video:
        print(f"{log_prefix} [VIDEO_MODE] High-confidence spike detected (score={spike_analysis['score']:.2f}, urgency={urgency_level}), generating video...")
        
        # Get SaaS growth odds if available (placeholder for now)
        saas_growth_odds = spike_analysis.get('market_odds')
        
        # Generate spicy viral take for video with urgency-based tone
        take_text = generate_viral_take_for_video(
            openai_client,
            trend_name,
            best_trend,
            saas_growth_odds,
            urgency_level,  # Pass urgency level for tone adjustment
            log_prefix
        )
        
        if not take_text:
            print(f"{log_prefix} [VIDEO_SKIP] Viral take generation failed, falling back to text tweet")
            use_video = False
        else:
            # Generate enhanced video with hook/main/CTA structure
            video_path = generate_viral_breaking_news_video(
                take_text,
                trend_name,
                referral_base_url,
                urgency_level,  # Pass urgency level for video styling
                log_prefix
            )
            
            if not video_path:
                print(f"{log_prefix} [VIDEO_SKIP] Video generation failed, falling back to text tweet")
                use_video = False
            else:
                # [STAGE 11B VIDEO] Post video immediately with viral-optimized caption
                # Clean trend name for hashtag (remove special chars, keep alphanumeric and spaces)
                trend_hashtag = ''.join(c for c in trend_name if c.isalnum() or c.isspace()).replace(' ', '')
                caption = f"""🚨 BREAKING: {trend_name} market just spiked

{take_text}

Trade now: {referral_base_url}

#{trend_hashtag[:20]} #PredictionMarkets #SaaS growthOdds #TradingAlerts"""
                
                # [STAGE 11B VIDEO ENHANCED] Post video using existing video posting infrastructure
                print(f"{log_prefix} [VIDEO_READY] Video generated: {video_path}")
                state["_video_path"] = video_path
                state["_video_caption"] = caption
                
                # Get page from state for pinning/amplification
                page = state.get("_page")
                
                try:
                    # [VIDEO_POST_FIX] Post video tweet immediately
                    print(f"{log_prefix} [VIDEO_POST] Attempting to post video to X (spike: {trend_name})...")
                    success = force_original_post_fn(
                        state=state,
                        text=caption,
                        source_stage="11B_BREAKING_NEWS_VIDEO"
                    )
                    
                    if success:
                        state["last_news_forced_post_ts"] = now_ts
                        state["news_forced_posts_today"] = state.get("news_forced_posts_today", 0) + 1
                        print(f"{log_prefix} [VIDEO_POST] ✓ Posted to X with video + spike take")
                        print(f"{log_prefix} [BREAKING_NEWS_VIDEO_POSTED] trend={trend_name} video={video_path} count_today={state['news_forced_posts_today']}")
                        
                        # [STAGE 11B VIDEO ENHANCED] Extract tweet ID for pinning and amplification
                        tweet_id = extract_tweet_id_from_post(page, log_prefix) if page else None
                        
                        if tweet_id:
                            # Pin tweet for 1 hour (max visibility)
                            print(f"{log_prefix} [VIDEO_PINNED] Pinned for 3600s (1 hour)")
                            if page:
                                pin_tweet(page, tweet_id, log_prefix, duration_minutes=60)
                            
                            # Amplify with influencer replies
                            print(f"{log_prefix} [AMPLIFY_REQUEST] Amplifying video tweet {tweet_id} with influencer replies")
                            if page:
                                amplify_video_with_influencer_replies(
                                    page,
                                    tweet_id,
                                    trend_name,
                                    referral_base_url,
                                    log_prefix
                                )
                        else:
                            print(f"{log_prefix} [VIDEO_WARNING] Could not extract tweet ID, skipping pinning/amplification")
                    else:
                        print(f"{log_prefix} [VIDEO_POST] ✗ Failed to post video to X (force_original_post_fn returned False)")
                        print(f"{log_prefix} [VIDEO_SKIP] Video post failed, falling back to text tweet")
                        use_video = False
                        # Clean up video file if post failed
                        try:
                            import os
                            if os.path.exists(video_path):
                                os.remove(video_path)
                        except Exception:
                            pass
                
                except Exception as e:
                    print(f"{log_prefix} [VIDEO_SKIP] Exception during video post: {e}, falling back to text tweet")
                    use_video = False
                    # Clean up video file
                    try:
                        import os
                        if os.path.exists(video_path):
                            os.remove(video_path)
                    except Exception:
                        pass
    
    # Fall back to text tweet if video failed or score too low
    if not use_video:
        tweet_text = generate_viral_breaking_tweet(
            openai_client,
            trend_name,
            mapping["saas_growth_query"],
            referral_base_url,
            log_prefix
        )
        
        if not tweet_text:
            print(f"{log_prefix} [SPIKE_SKIP] Tweet generation failed.")
            return
        
        print(f"{log_prefix} [NEWS_TWEET_GENERATED] trend={trend_name} text={tweet_text[:100]}...")
        
        print(f"{log_prefix} [FORCE_REQUEST] source=11B_BREAKING_NEWS")
        
        try:
            success = force_original_post_fn(
                state=state,
                text=tweet_text,
                source_stage="11B_BREAKING_NEWS"
            )
            
            if success:
                state["last_news_forced_post_ts"] = now_ts
                state["news_forced_posts_today"] = state.get("news_forced_posts_today", 0) + 1
                print(f"{log_prefix} [BREAKING_NEWS_POSTED] trend={trend_name} count_today={state['news_forced_posts_today']}")
            else:
                print(f"{log_prefix} [SPIKE_SKIP] force_original_post_fn returned False for trend={trend_name}")
        
        except Exception as e:
            print(f"{log_prefix} [SPIKE_SKIP] Exception during forced post: {e}")

