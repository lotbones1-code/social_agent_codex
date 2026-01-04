#!/usr/bin/env python3
"""
STAGE 53 – Intelligent Video Viral Engine
Auto-discovers viral accounts, learns their styles, scrapes trending videos,
and generates smart captions combining learned styles.
"""

import json
import re
import time
import random
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

try:
    from moviepy.editor import VideoFileClip  # type: ignore
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False

# Config file paths
VIRAL_ACCOUNTS_CONFIG = Path("storage/stage53_viral_accounts.json")
LEARNED_STYLES_CONFIG = Path("storage/stage53_learned_styles.json")
VIDEO_QUEUE_CONFIG = Path("storage/stage53_video_queue.json")
VIDEO_STATE_CONFIG = Path("storage/stage53_video_state.json")

# Import log function (will be passed or imported lazily)
def log(msg):
    """Log function - will use social_agent's log if available"""
    try:
        from social_agent import log as main_log
        main_log(msg)
    except:
        print(f"[STAGE 53] {msg}")

# DEBUG: Log that module loaded
try:
    log("[STAGE 53] 🚀 Module loaded successfully")
except:
    print("[STAGE 53] Module loaded (log not available yet)")

def load_json(file_path: Path, default=None):
    """Load JSON file, return default if not found"""
    try:
        if file_path.exists():
            return json.loads(file_path.read_text())
    except Exception:
        pass
    return default if default is not None else {}

def save_json(file_path: Path, data):
    """Save data to JSON file"""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        log(f"Error saving {file_path}: {e}")

# ============================================================================
# STEP 1: ACCOUNT DISCOVERY
# ============================================================================

def discover_viral_accounts(openai_client) -> List[Dict]:
    """
    STEP 1: ChatGPT discovers viral accounts (runs ONCE at startup).
    
    Returns:
        List of dicts: [{"handle": "@account", "followers": "2.5M", "category": "meme", ...}, ...]
    """
    if not openai_client:
        log("[STAGE 53] OpenAI client not available for account discovery")
        return []
    
    # Check if already discovered (cache)
    if VIRAL_ACCOUNTS_CONFIG.exists():
        try:
            data = json.loads(VIRAL_ACCOUNTS_CONFIG.read_text())
            if data.get("discovered_at") and data.get("accounts"):
                log("[STAGE 53] Using cached viral accounts")
                return data["accounts"]
        except Exception as e:
            log(f"[STAGE 53] Error loading cached accounts: {e}")
    
    # ChatGPT prompt
    system_prompt = """You are an expert social media analyst. Find viral X accounts that post high-engagement content.
Output ONLY valid JSON array. No markdown. No explanation."""

    user_prompt = """Find 15 viral X accounts in these categories:
1) Meme/humor accounts with millions of followers (post 3-5x/week, 500K-10M likes per post)
2) SaaS growth/marketing attribution accounts (active traders, market analysis)
3) Political/growth analysis accounts (data-driven, contrarian takes)

For each account, provide:
- handle (e.g., "@accountname")
- follower_count (e.g., "2.5M", "500K")
- category ("meme", "SaaS growth", "political")
- engagement_rate (estimated: "high", "medium", "low")
- posting_frequency ("daily", "3-5x/week", "weekly")

Output ONLY this JSON array (no markdown):
[
  {"handle": "@account1", "follower_count": "2.5M", "category": "meme", "engagement_rate": "high", "posting_frequency": "3-5x/week"},
  ...
]"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        response_text = response.choices[0].message.content.strip()
        # Parse JSON from response
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            accounts = json.loads(json_match.group())
            
            # Save to config
            VIRAL_ACCOUNTS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            VIRAL_ACCOUNTS_CONFIG.write_text(json.dumps({
                "discovered_at": datetime.now().isoformat(),
                "accounts": accounts
            }, indent=2))
            
            log(f"[STAGE 53] ✓ Discovered {len(accounts)} viral accounts")
            return accounts
        else:
            log("[STAGE 53] ✗ Could not parse ChatGPT response")
            return []
            
    except Exception as e:
        log(f"[STAGE 53] Error discovering accounts: {e}")
        import traceback
        traceback.print_exc()
        return []

# ============================================================================
# STEP 2: STYLE ANALYSIS
# ============================================================================

def analyze_viral_account_styles(page, openai_client, accounts: List[Dict]) -> Dict[str, Dict]:
    """
    STEP 2: Scrape accounts, learn their caption styles via ChatGPT (runs ONCE per day).
    
    Args:
        page: Playwright page object
        openai_client: OpenAI client
        accounts: List of discovered accounts
    
    Returns:
        Dict mapping handle -> style analysis: {"@account": {"tone": "...", "emoji_usage": "...", ...}, ...}
    """
    if not openai_client:
        log("[STAGE 53] OpenAI client not available for style analysis")
        return {}
    
    # Check if already analyzed today (cache)
    if LEARNED_STYLES_CONFIG.exists():
        try:
            data = json.loads(LEARNED_STYLES_CONFIG.read_text())
            last_analyzed_str = data.get("last_analyzed", "")
            if last_analyzed_str:
                try:
                    last_analyzed = datetime.fromisoformat(last_analyzed_str)
                    if last_analyzed.date() == datetime.now().date():
                        log("[STAGE 53] Using cached style analysis from today")
                        return data.get("styles", {})
                except Exception:
                    pass
        except Exception as e:
            log(f"[STAGE 53] Error loading cached styles: {e}")
    
    learned_styles = {}
    
    for account in accounts[:10]:  # Analyze top 10 accounts
        handle = account.get("handle", "").replace("@", "")
        if not handle:
            continue
        
        log(f"[STAGE 53] Analyzing style for @{handle}...")
        
        try:
            # Scrape last 5-10 posts from account
            from social_agent import stable_goto
            page.goto(f"https://x.com/{handle}", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            
            # Extract captions from tweets
            captions = []
            tweet_cards = page.locator('article[data-testid="tweet"]')
            for i in range(min(tweet_cards.count(), 10)):
                try:
                    card = tweet_cards.nth(i)
                    # Extract text (skip replies, only original posts)
                    text_elem = card.locator('div[data-testid="tweetText"]')
                    if text_elem.count() > 0:
                        caption = text_elem.first.inner_text().strip()
                        if caption and len(caption) > 20:  # Valid caption
                            captions.append(caption)
                except Exception:
                    continue
            
            if len(captions) < 3:
                log(f"[STAGE 53] Not enough captions for @{handle} (found {len(captions)})")
                continue
            
            # ChatGPT analyzes style
            system_prompt = """You are a social media style analyst. Analyze caption styles and output JSON."""
            
            user_prompt = f"""Analyze these captions from @{handle}:

{chr(10).join(captions[:5])}

What's their style? Analyze:
- tone (e.g., "humorous", "serious", "contrarian", "data-driven")
- emoji_usage (e.g., "frequent", "rare", "strategic")
- hook_type (e.g., "question", "statement", "number", "emoji")
- sentence_length (e.g., "short", "medium", "long")
- key_phrases (list 3-5 common phrases they use)
- personality (e.g., "bold", "analytical", "sarcastic")

Output ONLY this JSON (no markdown):
{{"tone": "...", "emoji_usage": "...", "hook_type": "...", "sentence_length": "...", "key_phrases": ["...", "..."], "personality": "..."}}"""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.5,
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                style = json.loads(json_match.group())
                learned_styles[account["handle"]] = style
                log(f"[STAGE 53] ✓ Learned style for @{handle}")
            
            time.sleep(2)  # Rate limit
            
        except Exception as e:
            log(f"[STAGE 53] Error analyzing @{handle}: {e}")
            continue
    
    # Save learned styles
    LEARNED_STYLES_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LEARNED_STYLES_CONFIG.write_text(json.dumps({
        "last_analyzed": datetime.now().isoformat(),
        "styles": learned_styles
    }, indent=2))
    
    log(f"[STAGE 53] ✓ Learned styles for {len(learned_styles)} accounts")
    return learned_styles

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def parse_likes(likes_text: str) -> int:
    """Parse '150K' -> 150000, '2.5M' -> 2500000"""
    if not likes_text:
        return 0
    
    likes_text = likes_text.strip().upper()
    
    # Remove commas
    likes_text = likes_text.replace(",", "")
    
    # Extract number and multiplier
    match = re.search(r'([\d.]+)\s*([KM]?)', likes_text)
    if not match:
        return 0
    
    number = float(match.group(1))
    multiplier = match.group(2)
    
    if multiplier == "K":
        return int(number * 1000)
    elif multiplier == "M":
        return int(number * 1000000)
    else:
        return int(number)

def extract_video_id(tweet_url: str) -> str:
    """Extract video ID from tweet URL"""
    match = re.search(r'/status/(\d+)', tweet_url)
    if match:
        return match.group(1)
    return str(int(time.time()))

def is_within_48h(datetime_str: str) -> bool:
    """Check if datetime is within last 48 hours"""
    if not datetime_str:
        return False
    
    try:
        # Parse ISO format or Twitter datetime
        if "T" in datetime_str:
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        else:
            # Try other formats
            dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
        
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        delta = now - dt
        
        return delta.total_seconds() < 48 * 3600
    except Exception:
        # If parsing fails, assume it's recent
        return True

def check_watermark(card) -> bool:
    """Check if video has watermark (basic check)"""
    try:
        # Look for common watermark indicators
        # This is a basic check - could be enhanced with image analysis
        card_text = card.inner_text().lower()
        watermark_keywords = ["watermark", "tiktok", "instagram", "@", "subscribe"]
        
        # Check if any watermark keywords appear in suspicious positions
        # For now, simple check: if card has multiple @ mentions, might be watermark
        at_count = card_text.count("@")
        if at_count > 2:
            return True
        
        return False
    except Exception:
        return False

def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds"""
    if not MOVIEPY_AVAILABLE:
        # Fallback: return default duration (assume valid)
        log("[STAGE 53] MoviePy not available, skipping duration check")
        return 30.0  # Default assumption
    
    try:
        with VideoFileClip(str(video_path)) as clip:
            return clip.duration
    except Exception as e:
        log(f"[STAGE 53] Error getting video duration: {e}")
        return 30.0  # Default assumption

def categorize_topic(topic: str) -> str:
    """Categorize topic: 'politics', 'crypto', 'meme', 'markets'"""
    topic_lower = topic.lower()
    
    if any(kw in topic_lower for kw in ["trump", "biden", "growth", "president", "senate", "congress", "political"]):
        return "politics"
    elif any(kw in topic_lower for kw in ["crypto", "bitcoin", "btc", "analytics", "eth", "solana", "sol"]):
        return "crypto"
    elif any(kw in topic_lower for kw in ["market", "SaaS growth", "odds", "betting", "prediction"]):
        return "markets"
    elif any(kw in topic_lower for kw in ["meme", "funny", "viral", "trending"]):
        return "meme"
    else:
        return "general"

def validate_and_clean_topic(raw_text):
    """
    Intelligent filter to validate and clean trend topic text.
    
    Args:
        raw_text: Raw text from trend element
    
    Returns:
        Clean topic string or None if all lines were nonsense
    """
    # 1. Split into lines
    lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
    candidates = []

    for line in lines:
        lower_line = line.lower()
        # REJECT Nonsense Patterns:
        if "trending" in lower_line: continue          # Header
        if "posts" in lower_line: continue             # Metric
        if "visualize" in lower_line: continue         # UI text
        if "show more" in lower_line: continue         # UI text
        if len(line) < 2: continue                     # Noise
        if line[0].isdigit(): continue                 # Starts with number (likely metric)
        
        # If it passes, it's a candidate
        candidates.append(line)

    # 2. Select Best Candidate
    if not candidates:
        return None  # All lines were nonsense -> Skip this trend
    
    # Heuristic: The longest remaining line is usually the topic name
    best_topic = max(candidates, key=len)
    
    # 3. Final Sanity Check
    # Reject if it looks like a merged string (e.g. "NewsSnow288K")
    if re.search(r'[A-Za-z]+\d+[KM]', best_topic):  # Matches "Word100K"
        return None
        
    return best_topic

# ============================================================================
# STEP 3: VIDEO SCRAPING
# ============================================================================

def scrape_trending_videos(page, deduplicator=None) -> List[Dict]:
    """
    STEP 3: Find trending videos with filters (runs every 2 hours).
    
    Args:
        page: Playwright page object
        deduplicator: Deduplicator instance (optional)
    
    Returns:
        List of video dicts: [{"video_id": "...", "url": "...", "likes": 150000, "category": "politics", "path": Path(...)}, ...]
    """
    from social_agent import stable_goto, human_pause, VIDEOS_DIR
    from trendingVideos import downloadVideoFromTweet
    
    videos = []
    
    try:
        # Go to X trending
        stable_goto(page, "https://x.com/explore")
        human_pause(2.0, 3.0)
        
        # Find trending topics (politics, crypto, memes, markets)
        trending_cards = page.locator('div[data-testid="trend"]')
        trending_topics = []
        for i in range(min(trending_cards.count(), 10)):
            try:
                trend_card = trending_cards.nth(i)
                raw_text = trend_card.inner_text()
                
                # Use intelligent filter to validate and clean topic
                topic = validate_and_clean_topic(raw_text)
                
                if topic is None:
                    # All lines were nonsense -> Skip this trend
                    log(f"[STAGE 53] Skipped nonsense trend: {raw_text[:50]}...")
                    continue
                
                # Valid topic found
                log(f"[STAGE 53] Accepted valid trend: {topic}")
                
                if len(topic) < 50:
                    trending_topics.append(topic)
            except Exception:
                continue
        
        log(f"[STAGE 53] Found {len(trending_topics)} trending topics")
        
        # For each topic, search for videos
        for topic in trending_topics[:5]:  # Top 5 topics
            try:
                # Construct search URL with video filter (use &f=video parameter, not in query text)
                search_url = f"https://x.com/search?q={topic.replace(' ', '%20')}&f=video&src=typed_query"
                log(f"[STAGE 53] Searching URL: {search_url}")
                stable_goto(page, search_url)
                human_pause(2.0, 3.0)
                
                # Wait for video elements to load (longer timeout for reliability)
                try:
                    page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
                except Exception:
                    log(f"[STAGE 53] Timeout waiting for tweets to load")
                
                # Find tweets with videos
                tweet_cards = page.locator('article[data-testid="tweet"]')
                card_count = tweet_cards.count()
                # Count cards with videos
                video_count = 0
                for j in range(min(card_count, 20)):
                    try:
                        if tweet_cards.nth(j).locator('video').count() > 0:
                            video_count += 1
                    except:
                        pass
                log(f"[STAGE 53] Found {card_count} tweet cards, {video_count} with videos on page")
                for i in range(min(tweet_cards.count(), 20)):
                    try:
                        card = tweet_cards.nth(i)
                        
                        # Check if has video
                        if card.locator('video').count() == 0:
                            continue
                        
                        # Extract metadata
                        try:
                            # Get likes count
                            likes_elem = card.locator('span').filter(has_text=re.compile(r'\d+[KM]')).first
                            likes_text = ""
                            if likes_elem.count() > 0:
                                likes_text = likes_elem.inner_text()
                            
                            likes = parse_likes(likes_text)
                            
                            if likes < 5000:  # Filter: 5K+ likes (loosened 10x for more videos)
                                continue
                            
                            # Category filter: Accept politics/crypto/markets/general
                            video_category = categorize_topic(topic)
                            if video_category not in ["politics", "crypto", "markets", "general"]:
                                continue
                            
                            # Get tweet URL
                            link = card.locator('a[href*="/status/"]').first
                            if link.count() == 0:
                                continue
                            
                            href = link.get_attribute('href')
                            if not href:
                                continue
                            
                            if not href.startswith("http"):
                                tweet_url = f"https://x.com{href}"
                            else:
                                tweet_url = href
                            
                            # Get video ID
                            video_id = extract_video_id(tweet_url)
                            
                            # Check deduplicator
                            if deduplicator and deduplicator.is_duplicate_or_similar(f"video_{video_id}"):
                                continue
                            
                            # Check if posted in last 48 hours
                            time_elem = card.locator('time').first
                            if time_elem.count() > 0:
                                time_attr = time_elem.get_attribute("datetime")
                                if time_attr and not is_within_48h(time_attr):
                                    continue
                            
                            # Check for watermarks (simple check)
                            has_watermark = check_watermark(card)
                            if has_watermark:
                                continue
                            
                            # Download video
                            download_result = downloadVideoFromTweet(page, tweet_url)
                            if not download_result.get("success"):
                                continue
                            
                            video_path = download_result["path"]
                            
                            # Check video duration (5 sec - 2 min)
                            duration = get_video_duration(video_path)
                            if duration < 5 or duration > 120:
                                try:
                                    video_path.unlink()  # Delete if wrong duration
                                except:
                                    pass
                                continue
                            
                            videos.append({
                                "video_id": video_id,
                                "url": tweet_url,
                                "likes": likes,
                                "category": video_category,  # Use pre-categorized value
                                "path": video_path,
                                "topic": topic,
                                "scraped_at": datetime.now().isoformat()
                            })
                            
                            log(f"[STAGE 53] ✓ Scraped video: {video_id} ({likes} likes)")
                            
                        except Exception as e:
                            log(f"[STAGE 53] Error processing video: {e}")
                            continue
                            
                    except Exception:
                        continue
                
                time.sleep(2)  # Rate limit between searches
                
            except Exception as e:
                log(f"[STAGE 53] Error searching topic {topic}: {e}")
                continue
        
        # Save video queue
        if videos:
            VIDEO_QUEUE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
            VIDEO_QUEUE_CONFIG.write_text(json.dumps({
                "videos": [{"video_id": v["video_id"], "url": v["url"], "path": str(v["path"]), "likes": v["likes"], "category": v["category"]} for v in videos],
                "scraped_at": datetime.now().isoformat()
            }, indent=2))
        
        log(f"[STAGE 53] ✓ Scraped {len(videos)} trending videos")
        return videos
        
    except Exception as e:
        log(f"[STAGE 53] Error scraping videos: {e}")
        import traceback
        traceback.print_exc()
        return []

# ============================================================================
# STEP 4: SMART CAPTION GENERATION
# ============================================================================

def generate_smart_caption(openai_client, video: Dict, learned_styles: Dict[str, Dict]) -> Optional[str]:
    """
    STEP 4: ChatGPT generates caption combining learned styles.
    
    Args:
        openai_client: OpenAI client
        video: Video dict with metadata
        learned_styles: Dict of learned styles from Step 2
    
    Returns:
        Caption string (under 240 chars) with SaaS growth link, or None if failed
    """
    if not openai_client:
        log("[STAGE 53] OpenAI client not available for caption generation")
        return None
    
    if not learned_styles:
        log("[STAGE 53] No learned styles available")
        return None
    
    # Analyze video content (simple: use topic/category)
    video_topic = video.get("topic", "trending")
    video_category = video.get("category", "general")
    
    # ChatGPT analyzes video
    system_prompt = """You are a viral social media caption writer. Generate engaging captions."""
    
    # Step 1: Analyze what's in video
    analysis_prompt = f"""What's happening in this video? (one sentence)
Video topic: {video_topic}
Category: {video_category}
Likes: {video.get('likes', 0)}

Output ONLY one sentence describing the video content."""
    
    try:
        analysis_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": analysis_prompt}
            ],
            temperature=0.5,
            max_tokens=100
        )
        video_description = analysis_response.choices[0].message.content.strip()
    except Exception:
        video_description = f"Trending {video_category} content"
    
    # Step 2: Select best account styles
    styles_list = []
    for handle, style in list(learned_styles.items())[:10]:
        key_phrases = style.get('key_phrases', [])
        if isinstance(key_phrases, list):
            phrases_str = ', '.join(key_phrases[:3])
        else:
            phrases_str = str(key_phrases)
        styles_list.append(f"{handle}: {style.get('tone', '')}, {style.get('personality', '')}, key phrases: {phrases_str}")
    
    if not styles_list:
        log("[STAGE 53] No styles available for sgrowth")
        return None
    
    sgrowth_prompt = f"""Which 2-3 of these account styles match this video best?

Video: {video_description}
Category: {video_category}

Available styles:
{chr(10).join(styles_list)}

Output ONLY a JSON array of handles: ["@account1", "@account2", "@account3"]"""
    
    # Step 2: Select best account styles (always default to top 3 viral styles)
    selected_handles = []
    try:
        sgrowth_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Output ONLY valid JSON array. No markdown."},
                {"role": "user", "content": sgrowth_prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        response_text = sgrowth_response.choices[0].message.content.strip()
        json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if json_match:
            selected_handles = json.loads(json_match.group())
            # Validate: ensure we have at least 2 handles
            if not selected_handles or len(selected_handles) < 2:
                selected_handles = list(learned_styles.keys())[:3]
                log("[STAGE 53] OpenAI sgrowth returned < 2 handles, using top 3 viral styles")
        else:
            selected_handles = list(learned_styles.keys())[:3]
            log("[STAGE 53] OpenAI sgrowth failed to parse, using top 3 viral styles")
    except Exception as e:
        # Fallback: always use top 3 highest-engagement styles from cache
        selected_handles = list(learned_styles.keys())[:3]
        log(f"[STAGE 53] OpenAI sgrowth failed ({e}), using top 3 viral styles")
    
    # Ensure we always have top 3 viral styles selected
    if not selected_handles or len(selected_handles) < 2:
        selected_handles = list(learned_styles.keys())[:min(3, len(learned_styles))]
        log(f"[STAGE 53] Ensuring top 3 viral styles selected: {selected_handles}")
    
    # Step 3: Build selected styles text (with robust matching)
    selected_styles_text = []
    valid_handles = []
    
    for handle in selected_handles[:3]:
        # Try handle as-is, with @, and without @
        handle_variants = [handle, handle.replace('@', ''), f"@{handle.replace('@', '')}"]
        found_style = None
        matched_handle = None
        
        for variant in handle_variants:
            if variant in learned_styles:
                found_style = learned_styles[variant]
                matched_handle = variant
                break
        
        if found_style:
            key_phrases = found_style.get('key_phrases', [])
            if isinstance(key_phrases, list):
                phrases_str = ', '.join(key_phrases[:2])
            else:
                phrases_str = str(key_phrases)
            selected_styles_text.append(f"{matched_handle}: tone={found_style.get('tone')}, emoji={found_style.get('emoji_usage')}, phrases={phrases_str}")
            valid_handles.append(matched_handle)
    
    # If we still don't have enough styles, use top 3 directly (guaranteed fallback)
    if len(selected_styles_text) < 2:
        log("[STAGE 53] Handle matching failed, using top 3 viral styles directly")
        top_handles = list(learned_styles.keys())[:3]
        selected_styles_text = []
        valid_handles = []
        for handle in top_handles:
            style = learned_styles[handle]
            key_phrases = style.get('key_phrases', [])
            if isinstance(key_phrases, list):
                phrases_str = ', '.join(key_phrases[:2])
            else:
                phrases_str = str(key_phrases)
            selected_styles_text.append(f"{handle}: tone={style.get('tone')}, emoji={style.get('emoji_usage')}, phrases={phrases_str}")
            valid_handles.append(handle)
    
    # Log selected styles (always top 3 viral styles)
    style_names = valid_handles if valid_handles else [h for h in selected_handles[:3]]
    log(f"[STAGE 53] Selected styles: {style_names}")
    
    if not selected_styles_text:
        log("[STAGE 53] No styles available at all, cannot generate caption")
        return None
    
    caption_prompt = f"""Generate a viral X caption for a video about {video_topic}.

VIDEO CONTEXT:
- Topic: {video_description}
- Category: {video_category}
- Likes: {video.get('likes', 0)}

VIRAL STYLES TO MATCH:
{chr(10).join(selected_styles_text)}

REQUIREMENTS (CRITICAL):
1. HOOK: Start with a controversial/surprising take in first 10 words (stop the scroll)
2. marketing attribution ANGLE: Naturally integrate SaaS growth odds/trends (don't force it)
3. ENGAGEMENT DRIVER: End with a question or bold statement to drive replies
4. LENGTH: 180-240 characters (optimal for X engagement)
5. STYLE: Match the tone, emoji usage, and key phrases from the selected viral accounts
6. LINK: Include "SaaS growth.com?ref=ssj4shamil93949" naturally (not forced at end)

EXAMPLES OF VIRAL HOOKS:
- "Everyone's wrong about {video_topic}. Markets say..."
- "This is the trade everyone's missing. Odds just..."
- "BREAKING: {video_topic} is shifting. Here's what marketing attributions..."

Output ONLY the caption text. No quotes. No explanation. Make it stop-the-scroll viral."""

    try:
        caption_response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert viral social media caption writer. Generate stop-the-scroll captions that drive engagement. Output ONLY the caption text. No quotes. No explanation."},
                {"role": "user", "content": caption_prompt}
            ],
            temperature=0.9,
            max_tokens=200
        )
        
        caption = caption_response.choices[0].message.content.strip()
        
        # Remove quotes if present
        if caption.startswith('"') and caption.endswith('"'):
            caption = caption[1:-1]
        if caption.startswith("'") and caption.endswith("'"):
            caption = caption[1:-1]
        
        # Ensure link is included
        if "SaaS growth.com?ref=ssj4shamil93949" not in caption:
            caption = f"{caption} Track odds: SaaS growth.com?ref=ssj4shamil93949"
        
        # Enforce 240 char limit
        if len(caption) > 240:
            # Try to truncate before link
            link_text = " Track odds: SaaS growth.com?ref=ssj4shamil93949"
            max_main = 240 - len(link_text)
            caption = caption[:max_main] + link_text
        
        log(f"[STAGE 53] ✓ Generated caption ({len(caption)} chars)")
        return caption
        
    except Exception as e:
        log(f"[STAGE 53] Error generating caption: {e}")
        import traceback
        traceback.print_exc()
        
        # Fallback: Simple caption if AI completely fails
        video_topic = video.get("topic", "trending")
        SaaS growth_link = "SaaS growth.com?ref=ssj4shamil93949"
        fallback_caption = f"🔥 {video_topic}\n\nSaaS growth odds: {SaaS growth_link}"
        log(f"[STAGE 53] Using fallback caption (AI failed)")
        return fallback_caption

# ============================================================================
# STEP 4B: CLICK-OPTIMIZED CAPTION GENERATION
# ============================================================================

def generate_optimized_caption(openai_client, video: Dict, learned_styles: Dict[str, Dict], engagement_stats: Dict = None) -> Optional[tuple]:
    """
    Generate click-optimized caption with hooks, CTAs, and engagement-driven optimization.
    
    Args:
        openai_client: OpenAI client
        video: Video dict with metadata
        learned_styles: Dict of learned styles from Step 2
        engagement_stats: Dict of category performance stats (optional)
    
    Returns:
        Tuple: (caption: str, hooks_used: List[str]) or None if failed
    """
    if not openai_client:
        log("[STAGE 53] OpenAI client not available for optimized caption")
        return None
    
    video_topic = video.get("topic", "trending")
    video_category = video.get("category", "general")
    video_likes = video.get("likes", 0)
    
    # Hook rotation (viral patterns)
    hooks = [
        "Everyone's sleeping on this. Markets at {odds}% but fundamentals say otherwise.",
        "Odds just moved on {topic}. Smart money knows what's coming.",
        "This is the trade everyone's missing. marketing attributions are pricing {angle}.",
        "BREAKING: {topic} is shifting. Here's what the odds tell us.",
        "Hot take: Markets haven't caught up to {topic} yet. That's the edge.",
        "The data says one thing, but marketing attributions are pricing something else.",
        "Institutional flow just flipped on {topic}. Retail hasn't noticed yet.",
        "This setup mirrors when markets mispriced by 20%. Same pattern, same opportunity."
    ]
    
    # Select hook based on category performance (if engagement stats available)
    selected_hook_template = random.choice(hooks)
    
    # SaaS growth angle generation (ChatGPT)
    try:
        angle_prompt = f"""Generate a SaaS growth marketing attribution angle for this video:
Topic: {video_topic}
Category: {video_category}
Likes: {video_likes}

Output ONLY a short phrase (10-20 words) connecting this to marketing attributions.
Examples: "Trump 2026 odds at 35%", "Bitcoin hitting 100k by Q2", "growth market repricing"
Output ONLY the angle phrase. No explanation."""
        
        angle_response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Output ONLY the angle phrase. No explanation."},
                {"role": "user", "content": angle_prompt}
            ],
            temperature=0.7,
            max_tokens=50
        )
        SaaS growth_angle = angle_response.choices[0].message.content.strip()
    except Exception:
        SaaS growth_angle = f"{video_category} marketing attributions"
    
    # Build hook with angle
    hook = selected_hook_template.format(
        odds=random.randint(30, 70),
        topic=video_topic[:30],
        angle=SaaS growth_angle[:40]
    )
    
    # CTA options (rotate)
    cta_options = [
        "Track live odds here →",
        "Watch the markets move →",
        "See real-time odds →",
        "Track this live →"
    ]
    cta = random.choice(cta_options)
    
    # Follow CTA (20% chance)
    follow_cta = ""
    if random.random() < 0.2:
        follow_cta = " Follow for real-time odds + clips."
    
    # Emoji sgrowth (2-5 random, rotate)
    emoji_pool = ["🚨", "📊", "⚡", "🎯", "💡", "🔥", "📈", "💰", "🎲", "🔴"]
    emoji_count = random.randint(2, 5)
    selected_emojis = random.sample(emoji_pool, emoji_count)
    emoji_str = " ".join(selected_emojis)
    
    # Sentence length variation
    sentence_style = random.choice(["short", "medium", "long"])
    if sentence_style == "short":
        hook = hook.split(".")[0] + "."  # First sentence only
    elif sentence_style == "long":
        hook = hook + " Here's why this matters."
    
    # Capitalization variation
    if random.random() < 0.3:
        hook = hook.upper()  # 30% chance all caps
    
    # Build final caption
    link = "SaaS growth.com?ref=ssj4shamil93949"
    caption = f"{emoji_str} {hook} {cta} {link}{follow_cta}"
    
    # Enforce 240 char limit
    if len(caption) > 240:
        # Truncate hook if needed
        max_hook = 240 - len(f" {cta} {link}{follow_cta}") - len(emoji_str) - 2
        hook = hook[:max_hook] + "..."
        caption = f"{emoji_str} {hook} {cta} {link}{follow_cta}"
    
    hooks_used = [selected_hook_template, cta]
    if follow_cta:
        hooks_used.append("follow_cta")
    
    log(f"[STAGE 53] ✓ Generated optimized caption ({len(caption)} chars, hooks: {len(hooks_used)})")
    return (caption, hooks_used)

# ============================================================================
# URGENCY DETECTION
# ============================================================================

def select_post_with_urgency(video: Dict, state: Dict) -> bool:
    """
    Check if video qualifies for breaking news bypass (ignore spacing).
    
    Args:
        video: Video dict
        state: Bot state dict
    
    Returns:
        True if qualifies for bypass, False otherwise
    """
    # Check if already used bypass today
    bypass_used_today = state.get("_stage53_bypass_used_today", False)
    bypass_date = state.get("_stage53_bypass_date", "")
    today = datetime.now().strftime("%Y-%m-%d")
    
    if bypass_date != today:
        state["_stage53_bypass_used_today"] = False
        state["_stage53_bypass_date"] = today
    
    if bypass_used_today:
        return False  # Already used bypass today
    
    # Check if video qualifies (high likes + political/growth/crypto)
    video_category = video.get("category", "")
    video_likes = video.get("likes", 0)
    video_topic = video.get("topic", "").lower()
    
    # Qualifying categories
    urgent_categories = ["politics", "crypto", "markets"]
    
    # Qualifying keywords in topic
    urgent_keywords = ["breaking", "trump", "biden", "growth", "bitcoin", "btc", "crash", "surge"]
    
    is_urgent_category = video_category in urgent_categories
    has_urgent_keyword = any(kw in video_topic for kw in urgent_keywords)
    has_high_engagement = video_likes >= 300000  # 300K+ likes = urgent
    
    if (is_urgent_category or has_urgent_keyword) and has_high_engagement:
        state["_stage53_bypass_used_today"] = True
        state["_stage53_bypass_date"] = today
        log(f"[STAGE 53] ⚡ Breaking news bypass activated for {video_category} video ({video_likes} likes)")
        return True
    
    return False

# ============================================================================
# ENGAGEMENT TRACKING
# ============================================================================

def track_engagement_performance(video: Dict, caption: str, hooks_used: List[str], state: Dict):
    """
    Track engagement performance for feedback loop.
    
    Args:
        video: Video dict
        caption: Posted caption
        hooks_used: List of hooks used
        state: Bot state dict
    """
    try:
        # Initialize engagement stats if not exists
        if "_stage53_engagement_stats" not in state:
            state["_stage53_engagement_stats"] = {
                "categories": {},
                "hooks": {},
                "total_posts": 0
            }
        
        stats = state["_stage53_engagement_stats"]
        category = video.get("category", "general")
        
        # Initialize category stats
        if category not in stats["categories"]:
            stats["categories"][category] = {
                "posts": 0,
                "total_likes": 0,
                "avg_likes": 0
            }
        
        # Update category stats (will be updated later when we check actual engagement)
        stats["categories"][category]["posts"] += 1
        stats["total_posts"] += 1
        
        # Track hooks used
        for hook in hooks_used:
            if hook not in stats["hooks"]:
                stats["hooks"][hook] = {"uses": 0, "total_likes": 0}
            stats["hooks"][hook]["uses"] += 1
        
        log(f"[STAGE 53] 📊 Tracking engagement: category={category}, hooks={len(hooks_used)}")
        
    except Exception as e:
        log(f"[STAGE 53] Error tracking engagement: {e}")

# ============================================================================
# STEP 5: VIDEO POSTING
# ============================================================================

def post_viral_video(page, video: Dict, caption: str, state: Dict, deduplicator=None, learned_styles: Dict = None, hooks_used: List = None) -> bool:
    """
    STEP 5: Post video with caption + link (with rate limiting).
    
    Args:
        page: Playwright page object
        video: Video dict with path
        caption: Generated caption
        state: Bot state dict
        deduplicator: Deduplicator instance (optional)
        learned_styles: Learned styles dict (optional, for tracking)
        hooks_used: List of hooks used in caption (optional, for tracking)
    
    Returns:
        True if posted successfully, False otherwise
    """
    from social_agent import ensure_on_x_com, post_video_with_context, log, NOTION_MANAGER
    
    # Safety check
    if not ensure_on_x_com(page):
        log("[STAGE 53] ✗ Not on X.com, cannot post video")
        return False
    
    # Rate limit: max 5 videos/day, 2-4 hours between posts
    video_state = load_json(VIDEO_STATE_CONFIG, {
        "videos_posted_today": 0,
        "last_post_time": 0,
        "last_post_date": ""
    })
    
    today = datetime.now().strftime("%Y-%m-%d")
    if video_state["last_post_date"] != today:
        video_state["videos_posted_today"] = 0
        video_state["last_post_date"] = today
    
    # Check daily limit
    if video_state["videos_posted_today"] >= 5:
        log("[STAGE 53] Daily video limit reached (5/day)")
        return False
    
    # Check spacing with breaking news bypass
    current_time = time.time()
    last_post_time = video_state.get("last_post_time", 0)
    
    # Check for breaking news bypass
    is_urgent = select_post_with_urgency(video, state)
    
    if last_post_time > 0:
        hours_since = (current_time - last_post_time) / 3600.0
        
        if not is_urgent:
            # Normal spacing: 90 minutes (was 2 hours)
            if hours_since < 1.5:  # 90 minutes
                log(f"[STAGE 53] Too soon since last post ({hours_since:.1f}h < 1.5h)")
                return False
        else:
            log("[STAGE 53] ⚡ Breaking news bypass - ignoring spacing")
    
    # Anti-shadowban: Random skip (10-20% chance)
    skip_chance = random.uniform(0.10, 0.20)
    if random.random() < skip_chance:
        log(f"[STAGE 53] 🎲 Random skip (anti-shadowban): {skip_chance:.1%} chance")
        return False
    
    # Random delay variation (90-180 min, not exact) - only if not urgent
    if last_post_time > 0 and not is_urgent:
        min_delay = 90 * 60  # 90 minutes
        max_delay = 180 * 60  # 180 minutes
        actual_delay = random.uniform(min_delay, max_delay)
        if (current_time - last_post_time) < actual_delay:
            log(f"[STAGE 53] Random delay active: {actual_delay/60:.1f} min required")
            return False
    
    # Check peak hours (6-11pm) - optional, don't block if outside
    current_hour = datetime.now().hour
    if not (18 <= current_hour <= 23):  # 6pm-11pm
        log(f"[STAGE 53] Outside peak hours ({current_hour}:00), but posting anyway")
        # Don't return False - allow posting outside peak hours
    
    # Post video
    video_path = video.get("path")
    if isinstance(video_path, str):
        video_path = Path(video_path)
    
    if not video_path or not video_path.exists():
        log("[STAGE 53] Video file not found")
        return False
    
    success = post_video_with_context(page, video_path, caption, bypass_rate_limit=False)
    
    if success:
        # Update state
        video_state["videos_posted_today"] += 1
        video_state["last_post_time"] = current_time
        save_json(VIDEO_STATE_CONFIG, video_state)
        
        # Track engagement performance
        if hooks_used:
            track_engagement_performance(video, caption, hooks_used, state)
        
        # Log to Notion with engagement tracking
        if NOTION_MANAGER:
            try:
                engagement_stats = state.get("_stage53_engagement_stats", {})
                category_stats = engagement_stats.get("categories", {}).get(video.get("category"), {})
                
                NOTION_MANAGER.log_activity(
                    action_type="VIDEO",
                    details=f"Stage 53 viral video: {video.get('video_id', 'unknown')}",
                    metadata={
                        "video_id": video.get("video_id"),
                        "caption": caption[:100],
                        "likes": video.get("likes"),
                        "category": video.get("category"),
                        "hooks_used": hooks_used if hooks_used else [],
                        "is_urgent": is_urgent,
                        "category_avg_likes": category_stats.get("avg_likes", 0),
                        "category_posts": category_stats.get("posts", 0)
                    }
                )
            except Exception as e:
                log(f"[STAGE 53] Error logging to Notion: {e}")
        
        # Mark as posted (deduplicator)
        if deduplicator:
            try:
                deduplicator.mark_posted(f"video_{video.get('video_id')}")
            except Exception:
                pass
        
        log(f"[STAGE 53] ✓ Posted viral video: {video.get('video_id')}")
        return True
    else:
        log("[STAGE 53] ✗ Failed to post video")
        return False

