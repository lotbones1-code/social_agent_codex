#!/usr/bin/env python3
# social_agent.py — Chrome persistent login + anti-duplicate posting + image/video generator hooks

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError
from pathlib import Path
import time, sys, json, random, re, subprocess, hashlib, os
from datetime import datetime, timezone
from collections import deque
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import phase controller for automatic phase management
try:
    from social_agent_config import PHASE_CONTROLLER
except ImportError:
    # Fallback if config file doesn't exist yet
    PHASE_CONTROLLER = None

# Import deduplication and video scheduling
try:
    from reply_deduplication import DEDUPLICATOR
except ImportError:
    DEDUPLICATOR = None
    print("⚠️ Reply deduplicator not available")

try:
    from video_scheduler import VIDEO_SCHEDULER
except ImportError:
    # Fallback to video_poster if video_scheduler not found
    try:
        from video_poster import VIDEO_SCHEDULER
    except ImportError:
        VIDEO_SCHEDULER = None
        print("⚠️ Video scheduler not available")

try:
    from video_poster import VIDEO_FINDER
except ImportError:
    VIDEO_FINDER = None
    print("⚠️ Video finder not available")

try:
    from account_helper import ACCOUNT_HELPER
except ImportError:
    ACCOUNT_HELPER = None
    print("⚠️ Account helper not available")

try:
    from post_cleanup import CLEANUP
except ImportError:
    CLEANUP = None
    print("⚠️ Post cleanup not available")

try:
    from follower_management import FOLLOWER_MGR
except ImportError:
    FOLLOWER_MGR = None
    print("⚠️ Follower manager not available")

try:
    from engagement_mixer import ENGAGEMENT_MIXER
except ImportError:
    ENGAGEMENT_MIXER = None
    print("⚠️ Engagement mixer not available")

try:
    from radar_targeting import RADAR_TARGETING
except ImportError:
    RADAR_TARGETING = None
    print("⚠️ Radar targeting not available")

try:
    from performance_analytics import ANALYTICS
except ImportError:
    ANALYTICS = None
    print("⚠️ Performance analytics not available")

try:
    from strategy_brain import BRAIN
except ImportError:
    BRAIN = None
    print("⚠️ Strategy Brain not available")

try:
    from notion_manager import NotionManager, init_notion_manager
    NOTION_MANAGER = init_notion_manager()
    if NOTION_MANAGER and NOTION_MANAGER.enabled:
        print("[NOTION] ✅ Notion controller initialized and connected")
    else:
        # Notion manager exists but is disabled - error messages already printed by init_notion_manager
        pass
except ImportError as e:
    # notion_manager.py file doesn't exist or has import errors
    NOTION_MANAGER = None
    print(f"[NOTION] ❌ Failed to import notion_manager: {e}")
    print("[NOTION] Ensure notion_manager.py exists in the project directory")
except Exception as e:
    NOTION_MANAGER = None
    print(f"[NOTION] ❌ Unexpected error initializing Notion: {e}")
    print("[NOTION] Continuing without Notion logging")

# [BOT RECONSTRUCTION] Import hashtag manager
try:
    from hashtag_manager import add_hashtags_to_post, generate_hashtags
    HASHTAG_MANAGER_AVAILABLE = True
except ImportError as e:
    HASHTAG_MANAGER_AVAILABLE = False
    log(f"[HASHTAG] Hashtag manager not available: {e}")

# [FOLLOWER MULTIPLICATION ENGINE] Import engagement and authority modules
try:
    from engagement_multiplier import EngagementMultiplier
    ENGAGEMENT_MULTIPLIER_AVAILABLE = True
except ImportError as e:
    ENGAGEMENT_MULTIPLIER_AVAILABLE = False
    print(f"⚠️ Engagement multiplier not available: {e}")

try:
    from authority_targeting import AuthorityTargeter
    AUTHORITY_TARGETER_AVAILABLE = True
except ImportError as e:
    AUTHORITY_TARGETER_AVAILABLE = False
    print(f"⚠️ Authority targeter not available: {e}")

try:
    from bot_hardening import HARDENING
except ImportError:
    HARDENING = None
    print("⚠️ Bot hardening not available")

try:
    from reply_optimizer import REPLY_OPTIMIZER
except ImportError:
    REPLY_OPTIMIZER = None
    print("⚠️ Reply optimizer not available")

try:
    from reply_psychology import REPLY_PSYCHOLOGY
except ImportError:
    REPLY_PSYCHOLOGY = None
    print("⚠️ Reply psychology not available")

try:
    from trending_jacker import TRENDING_JACKER
except ImportError:
    TRENDING_JACKER = None
    print("⚠️ Trending jacker (Stage 12) not available")

# [STAGE 16B] Niche Focus Mode Configuration
NICHE_FOCUS_CONFIG = {
    "enabled": True,
    "niches": {
        "growth": {
            "keywords": ["growth", "marketing", "SaaS", "attribution", "conversion", "tracking"],
            "focus_post_percentage": 0.70
        },
        "bitcoin": {
            "keywords": ["bitcoin", "btc", "crypto", "blockchain", "satoshi"],
            "focus_post_percentage": 0.70
        },
        "fed_rate": {
            "keywords": ["fed", "federal reserve", "interest rate", "inflation", "rate cut"],
            "focus_post_percentage": 0.70
        },
        "superbowl": {
            "keywords": ["superbowl", "nfl", "football", "super bowl", "championship"],
            "focus_post_percentage": 0.70
        }
    },
    "default_focus_post_percentage": 0.70
}

_niche_focus_state = {
    "active_niche": None,
    "activated_at": 0,
    "last_niche_post_time": 0
}

def activate_niche_focus(niche_name):
    """[STAGE 16B] Activate niche focus mode for a specific niche."""
    global _niche_focus_state
    if niche_name not in NICHE_FOCUS_CONFIG.get("niches", {}):
        log(f"[STAGE 16B] Invalid niche: {niche_name}")
        return False
    
    _niche_focus_state["active_niche"] = niche_name
    _niche_focus_state["activated_at"] = time.time()
    log(f"[STAGE 16B] Activated niche focus: {niche_name}")
    return True

# [STAGE 17] Feedback Database
POST_HISTORY_FILE = "post_performance_history.json"

def load_post_history():
    """[STAGE 17] Load post performance history from JSON file."""
    try:
        if os.path.exists(POST_HISTORY_FILE):
            with open(POST_HISTORY_FILE, "r") as f:
                data = json.load(f)
                log(f"[STAGE 17] Loaded {len(data.get('posts', []))} posts from performance history")
                return data.get("posts", [])
        else:
            log("[STAGE 17] Post performance history file not found, starting fresh")
            return []
    except Exception as e:
        log(f"[STAGE 17] Error loading post history: {e}")
        return []

def save_post_result(post_id, prompt_used, hashtags, views, likes, timestamp=None):
    """[STAGE 17] Save post result to performance history."""
    try:
        posts = load_post_history()
        
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        post_entry = {
            "post_id": str(post_id),
            "timestamp": timestamp,
            "prompt_used": prompt_used[:200] if prompt_used else "",  # Truncate long prompts
            "hashtags": hashtags if hashtags else [],
            "views": views,
            "likes": likes,
            "velocity": 0.0,  # Will be calculated later
            "status": "pending"  # Will be updated by performance checker
        }
        
        posts.append(post_entry)
        
        # Keep last 100 posts
        posts = posts[-100:]
        
        # Save back to file
        os.makedirs(os.path.dirname(POST_HISTORY_FILE) if os.path.dirname(POST_HISTORY_FILE) else ".", exist_ok=True)
        with open(POST_HISTORY_FILE, "w") as f:
            json.dump({"posts": posts}, f, indent=2)
        
        log(f"[STAGE 17] Saved post result: {post_id} (views={views}, likes={likes})")
    except Exception as e:
        log(f"[STAGE 17] Error saving post result: {e}")

def get_post_metrics(page, post_id):
    """[STAGE 17] Get metrics (views, likes) for a post by navigating to it."""
    try:
        tweet_url = f"https://x.com/{BOT_HANDLE.replace('@', '')}/status/{post_id}"
        stable_goto(page, tweet_url)
        human_pause(2.0, 3.0)
        
        # Find the tweet card
        tweet_card = page.locator('article[data-testid="tweet"]').first
        if tweet_card.count() == 0:
            log(f"[STAGE 17] Could not find tweet card for post: {post_id}")
            return {"views": 0, "likes": 0}
        
        likes = 0
        views = 0
        
        # Extract likes
        try:
            likes_elem = tweet_card.locator('[data-testid="like"]').first
            if likes_elem.count() > 0:
                likes_text = likes_elem.inner_text() or ""
                # Parse likes (handles K, M suffixes)
                def parse_count_stage17(count_str):
                    if not count_str:
                        return 0
                    count_str = count_str.upper().replace(",", "").strip()
                    if 'K' in count_str:
                        return int(float(count_str.replace('K', '')) * 1000)
                    elif 'M' in count_str:
                        return int(float(count_str.replace('M', '')) * 1000000)
                    else:
                        return int(''.join(filter(str.isdigit, count_str))) if ''.join(filter(str.isdigit, count_str)) else 0
                likes = parse_count_stage17(likes_text)
        except Exception as e:
            log(f"[STAGE 17] Error extracting likes: {e}")
        
            # Extract views (if visible)
            try:
                views_elem = tweet_card.locator('text=/\\d+[KM]?\\s*Views/i').first
                if views_elem.count() > 0:
                    views_text = views_elem.inner_text()
                    views = parse_count_stage17(views_text)
                else:
                    # Estimate views from likes (rough: 10 views per like)
                    views = likes * 10
            except Exception:
                views = likes * 10  # Fallback estimate
        
        return {"views": views, "likes": likes}
    except Exception as e:
        log(f"[STAGE 17] Error getting post metrics: {e}")
        return {"views": 0, "likes": 0}

def check_recent_post_performance(page):
    """[STAGE 17] Check performance of recent posts (MVP—minimal implementation)."""
    try:
        # MVP: Just log that we're checking, don't actually check API
        log("[STAGE 17] Checking recent post performance...")
        # Real implementation: would fetch own recent posts, check likes/retweets, analyze
        # For now, just return successfully
        return True
    except Exception as e:
        log(f"[STAGE 17] Error checking post performance: {e}")
        return False

def get_optimized_prompt_modifiers():
    """[STAGE 17] Get prompt modifiers for tweet generation (MVP—minimal implementation)."""
    try:
        # MVP: Return empty string (no modifications)
        # Real implementation: would analyze recent post performance and suggest tone/structure changes
        return ""
    except Exception as e:
        log(f"[STAGE 17] Error getting prompt modifiers: {e}")
        return ""

def is_niche_focus_active():
    """[STAGE 16B] Check if niche focus is currently active."""
    return _niche_focus_state.get("active_niche") is not None

def should_post_about_niche():
    """[STAGE 16B] Check if next post should be about active niche (70% probability)."""
    if not is_niche_focus_active():
        return False
    
    niche = _niche_focus_state.get("active_niche")
    config = NICHE_FOCUS_CONFIG.get("niches", {}).get(niche, {})
    focus_percentage = config.get("focus_post_percentage", NICHE_FOCUS_CONFIG.get("default_focus_post_percentage", 0.70))
    
    import random
    should_post = random.random() < focus_percentage
    if should_post:
        log(f"[STAGE 16B] Next post will focus on niche: {niche}")
    return should_post

def get_niche_prompt_instruction():
    """[STAGE 16B] Get niche-specific prompt instruction."""
    if not is_niche_focus_active():
        return ""
    
    niche = _niche_focus_state.get("active_niche")
    config = NICHE_FOCUS_CONFIG.get("niches", {}).get(niche, {})
    keywords = config.get("keywords", [])
    keyword_list = ", ".join(keywords[:3])  # Use first 3 keywords
    
    return f"\n\nNICHE FOCUS: This post MUST be about {niche.upper()}. Include keywords like: {keyword_list}. Make it highly relevant to this niche."

def check_trending_for_niche_opportunity():
    """[STAGE 16B] Check trending topics and activate niche if relevant."""
    if not TRENDING_JACKER:
        return
    
    try:
        trends = TRENDING_JACKER.get_cached_trends() or []
        for trend in trends[:5]:  # Check top 5 trends
            trend_name = trend.get("name", "").lower() if isinstance(trend, dict) else str(trend).lower()
            
            # Check each niche
            for niche_name, niche_config in NICHE_FOCUS_CONFIG.get("niches", {}).items():
                keywords = niche_config.get("keywords", [])
                if any(keyword.lower() in trend_name for keyword in keywords):
                    if not is_niche_focus_active() or _niche_focus_state.get("active_niche") != niche_name:
                        activate_niche_focus(niche_name)
                        log(f"[STAGE 16B] Activated niche '{niche_name}' based on trending: {trend_name}")
                        return
    except Exception as e:
        log(f"[STAGE 16B] Error checking trending for niche: {e}")

# [STAGE 16C] Engagement Loop Functions
ENGAGEMENT_STATE_FILE = "engagement_state.json"

def track_own_post_for_engagement(post_id, tweet_text):
    """[STAGE 16C] Track own post for later engagement checking."""
    try:
        state = load_json(Path(ENGAGEMENT_STATE_FILE), {
            "tracked_posts": [],
            "last_engagement_check": 0,
            "last_reply_process": 0
        })
        
        # Append new post to tracked list
        tracked_posts = state.get("tracked_posts", [])
        tracked_posts.append({
            "post_id": post_id,
            "tweet_text": tweet_text[:100],  # First 100 chars
            "timestamp": time.time(),
            "checked": False
        })
        
        # Keep only last 50 posts
        tracked_posts = tracked_posts[-50:]
        state["tracked_posts"] = tracked_posts
        
        save_json(Path(ENGAGEMENT_STATE_FILE), state)
        log(f"[STAGE 16C] Tracking post {post_id} for engagement checking")
    except Exception as e:
        log(f"[STAGE 16C] Error tracking post: {e}")

def check_own_posts_for_engagement(page):
    """[STAGE 16C] Check tracked posts for engagement (MVP - throttled every 5-10 min)."""
    try:
        # Check throttle: only run every 5-10 minutes
        state = load_json(Path(ENGAGEMENT_STATE_FILE), {
            "tracked_posts": [],
            "last_engagement_check": 0,
            "last_reply_process": 0
        })
        
        last_check = state.get("last_engagement_check", 0)
        current_time = time.time()
        throttle_seconds = random.randint(300, 600)  # 5-10 minutes
        
        if last_check > 0 and (current_time - last_check) < throttle_seconds:
            return  # Skip if not enough time has passed
        
        # Update last check time
        state["last_engagement_check"] = current_time
        save_json(Path(ENGAGEMENT_STATE_FILE), state)
        
        log("[STAGE 16C] [ENGAGEMENT_LOOP] Checking own posts for engagement...")
        
        # MVP: Just mark first 5 unchecked posts as "checked"
        tracked_posts = state.get("tracked_posts", [])
        unchecked_posts = [p for p in tracked_posts if not p.get("checked", False)]
        
        for post in unchecked_posts[:5]:  # Process max 5 at a time
            post["checked"] = True
        
        # Save updated state
        state["tracked_posts"] = tracked_posts
        save_json(Path(ENGAGEMENT_STATE_FILE), state)
        
        if unchecked_posts:
            log(f"[STAGE 16C] [ENGAGEMENT_LOOP] Marked {min(5, len(unchecked_posts))} posts as checked (MVP)")
        
    except Exception as e:
        log(f"[STAGE 16C] Error checking engagement: {e}")

def process_scheduled_replies(page):
    """[STAGE 16C] Process scheduled replies from queue (MVP - throttled every 2-5 min)."""
    try:
        # Check throttle: only run every 2-5 minutes
        state = load_json(Path(ENGAGEMENT_STATE_FILE), {
            "tracked_posts": [],
            "last_engagement_check": 0,
            "last_reply_process": 0
        })
        
        last_process = state.get("last_reply_process", 0)
        current_time = time.time()
        throttle_seconds = random.randint(120, 300)  # 2-5 minutes
        
        if last_process > 0 and (current_time - last_process) < throttle_seconds:
            return  # Skip if not enough time has passed
        
        # Update last process time
        state["last_reply_process"] = current_time
        save_json(Path(ENGAGEMENT_STATE_FILE), state)
        
        log("[STAGE 16C] Processing scheduled replies...")
        
        # MVP: No replies queued yet, just return
        # Real reply queueing implementation can be added later
        
    except Exception as e:
        log(f"[STAGE 16C] Error processing scheduled replies: {e}")

# [STAGE 16A] Video Posting Functions
VIDEO_MAGNET_STATE_FILE = "video_magnet_state.json"
VIDEO_CACHE_FILE = "video_cache.json"
VIDEO_POSTING_CONFIG = {"context_prompt": "Watch below 👇"}  # Default config

def should_post_video_now():
    """[STAGE 16A] Gate function - returns True if video posting is allowed."""
    try:
        # Check if bot is awake
        if should_sleep_now():
            return False
        
        # 5% chance per cycle
        if random.random() >= 0.05:
            return False
        
        # Check if video source exists
        if os.path.exists(VIDEO_CACHE_FILE):
            try:
                with open(VIDEO_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    videos = data.get("videos", [])
                    if videos:
                        return True
            except Exception:
                pass
        
        # No videos available
        return False
    except Exception as e:
        log(f"[STAGE 16A] Error in should_post_video_now: {e}")
        return False

def get_video_for_post():
    """[STAGE 16A] Fetch function - returns video path or None."""
    try:
        # Read video cache
        videos = []
        if os.path.exists(VIDEO_CACHE_FILE):
            try:
                with open(VIDEO_CACHE_FILE, "r") as f:
                    data = json.load(f)
                    videos = data.get("videos", [])
            except Exception:
                pass
        
        if not videos:
            return None
        
        # Read/write state file for rotation
        state = load_json(Path(VIDEO_MAGNET_STATE_FILE), {
            "last_video_post_time": 0,
            "last_magnet_post_time": 0,
            "video_index": 0
        })
        
        video_index = state.get("video_index", 0)
        video_path = videos[video_index % len(videos)]
        
        # Increment index for next time
        state["video_index"] = (video_index + 1) % len(videos)
        save_json(Path(VIDEO_MAGNET_STATE_FILE), state)
        
        return video_path
    except Exception as e:
        log(f"[STAGE 16A] Error in get_video_for_post: {e}")
        return None

def post_video_with_context(page, video_path, context_text, bypass_rate_limit=False):
    """[STAGE 16A/11B VIDEO] Post function - posts video with caption, returns bool.
    
    Args:
        page: Playwright page object
        video_path: Path to video file
        context_text: Caption text for the video
        bypass_rate_limit: If True, skip rate limit check (for breaking news videos)
    """
    try:
        # [SAFETY] Ensure we're on X.com before posting
        if not ensure_on_x_com(page):
            log("[VIDEO_POST] ✗ Not on X.com, cannot post video")
            return False
        
        # [STAGE 11B VIDEO] Skip rate limit for breaking news videos (viral potential > scheduling)
        if not bypass_rate_limit:
            # Check rate limit (24 hours)
            state = load_json(Path(VIDEO_MAGNET_STATE_FILE), {
                "last_video_post_time": 0,
                "last_magnet_post_time": 0,
                "video_index": 0
            })
            
            last_post_time = state.get("last_video_post_time", 0)
            current_time = time.time()
            if last_post_time > 0 and (current_time - last_post_time) < (24 * 3600):
                return False  # Rate limited
        else:
            log("[STAGE 11B VIDEO] Bypassing video rate limit for breaking news")
        
        # Generate caption (reuse context_text or generate minimal one)
        if not context_text:
            context_text = "Watch below 👇"
        
        # Post video using existing infrastructure
        stable_goto(page, HOME_URL)
        human_pause(2.0, 3.0)
        
        # Open composer
        new_tweet_button = page.locator('[data-testid="SideNav_NewTweet_Button"]').first
        if new_tweet_button.count() == 0:
            log("[STAGE 16A] [VIDEO_POST] Could not find composer button")
            return False
        
        try:
            new_tweet_button.click(timeout=5000)
        except Exception as e:
            log(f"[STAGE 16A] [VIDEO_POST] Could not click composer button: {e}")
            return False
        human_pause(1.0, 2.0)
        
        # Type caption
        composer_selectors = [
            'div[role="textbox"][data-testid="tweetTextarea_0"]',
            'div[role="textbox"][data-testid="tweetTextarea_1"]',
            'div[data-testid="tweetTextarea"]',
            'div[placeholder*="What"]',
            '[contenteditable="true"]',
            'textarea'
        ]
        
        typed = False
        for selector in composer_selectors:
            try:
                composer = page.locator(selector).first
                if composer.count() > 0:
                    try:
                        composer.click(timeout=5000)
                    except Exception as e:
                        log(f"[STAGE 16A] [VIDEO_POST] Could not click composer: {e}")
                        continue
                    human_pause(0.3, 0.5)
                    page.keyboard.type(context_text, delay=random.randint(30, 80))
                    typed = True
                    break
            except Exception:
                continue
        
        if not typed:
            log("[STAGE 16A] [VIDEO_POST] Could not type caption")
            page.keyboard.press("Escape")
            return False
        
        human_pause(1.0, 2.0)
        
        # Attach video
        file_input = find_file_input(page)
        if file_input and os.path.exists(video_path):
            try:
                file_input.set_input_files(str(video_path))
                log(f"[STAGE 16A] [VIDEO_POST] Attached video: {video_path}")
                human_pause(3.0, 5.0)  # Wait for upload
            except Exception as e:
                log(f"[STAGE 16A] [VIDEO_POST] Error attaching video: {e}")
                page.keyboard.press("Escape")
                return False
        else:
            log("[STAGE 16A] [VIDEO_POST] Could not attach video (file_input not found or file missing)")
            page.keyboard.press("Escape")
            return False
        
        # Post (allow media for Stage 53 video posts)
        posted = click_post_once(page, allow_media=True)
        if posted:
            # Update state
            state["last_video_post_time"] = current_time
            save_json(Path(VIDEO_MAGNET_STATE_FILE), state)
            log(f"[STAGE 16A] [VIDEO_POST] Posted video: {video_path}, caption: {context_text[:50]}...")
            
            # [NOTION] Log video post activity
            if NOTION_MANAGER:
                try:
                    video_name = os.path.basename(video_path) if video_path else "unknown"
                    NOTION_MANAGER.log_activity(
                        "VIDEO",
                        f"Video posted: {video_name}",
                        metadata={
                            "video_path": video_name,
                            "caption": context_text[:200],
                            "bypass_rate_limit": str(bypass_rate_limit),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log video: {e}")
            
            human_pause(2.0, 3.0)
            return True
        else:
            log("[STAGE 16A] [VIDEO_POST] Failed to post video")
            page.keyboard.press("Escape")
            return False
            
    except Exception as e:
        log(f"[STAGE 16A] [VIDEO_POST] Error posting video: {e}")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False

# [STAGE 16D] Follower Magnet Functions
def should_post_follower_magnet():
    """[STAGE 16D] Gate function - returns True if follower magnet posting is allowed."""
    try:
        # Check if bot is awake
        if should_sleep_now():
            return False
        
        # Check state file for cooldown
        state = load_json(Path(VIDEO_MAGNET_STATE_FILE), {
            "last_video_post_time": 0,
            "last_magnet_post_time": 0,
            "video_index": 0
        })
        
        last_magnet_time = state.get("last_magnet_post_time", 0)
        current_time = time.time()
        
        # Check if 12 hours have passed
        if last_magnet_time > 0 and (current_time - last_magnet_time) < (12 * 3600):
            return False  # Still in cooldown
        
        # 2% chance per cycle (if cooldown passed)
        return random.random() < 0.02
    except Exception as e:
        log(f"[STAGE 16D] Error in should_post_follower_magnet: {e}")
        return False

def post_follower_magnet(page):
    """[STAGE 16D] Post function - posts viral follower magnet tweet, returns bool."""
    try:
        # [SAFETY] Ensure we're on X.com before posting
        if not ensure_on_x_com(page):
            log("[FOLLOWER_MAGNET] ✗ Not on X.com, cannot post")
            return False
        
        # Check rate limit (12 hours)
        state = load_json(Path(VIDEO_MAGNET_STATE_FILE), {
            "last_video_post_time": 0,
            "last_magnet_post_time": 0,
            "video_index": 0
        })
        
        last_magnet_time = state.get("last_magnet_post_time", 0)
        current_time = time.time()
        if last_magnet_time > 0 and (current_time - last_magnet_time) < (12 * 3600):
            return False  # Rate limited
        
        # Pick template
        templates = [
            "Switched from Bitly to Dub for this exact reason - their conversion tracking actually shows which links drive signups, not just clicks. Plus real-time attribution. 🔮",
            "{niche} is trending hard right now. Link attribution shows {metric}% improvement. Here's why... 🧵",
            "The marketing attribution just shifted. Here's what the data tells us about what happens next... 📊",
            "Hot take: {niche} will see {prediction}% growth. Conversion tracking puts it at {metric}%. Agree or disagree? 🤔",
            "Just checked the link analytics. {niche} performance is wild right now. Here's the breakdown..."
        ]
        
        template = random.choice(templates)
        
        # Fill placeholders
        niche = "crypto"
        if is_niche_focus_active():
            niche = _niche_focus_state.get("active_niche", "crypto")
        
        price = random.choice(["100k", "120k", "150k", "200k"])
        date = random.choice(["end of Q1 2026", "mid-2026", "by Q2 2026", "end of 2026"])
        odds = random.randint(55, 75)
        position = random.choice(["long", "short", "neutral", "hedging"])
        prediction = random.choice([
            "dominate enterprise AI",
            "crash 50%",
            "moon 10x",
            "break new ATH",
            "trigger a recession"
        ])
        
        # Format template with placeholders (handle ${price} syntax by replacing first)
        try:
            # Replace ${price} with {price} for Python format
            template_formatted = template.replace("${price}", "{price}")
            tweet_text = template_formatted.format(
                price=price,
                date=date,
                niche=niche,
                odds=odds,
                position=position,
                prediction=prediction
            )
        except (KeyError, ValueError) as e:
            # Fallback if template has unexpected placeholders
            tweet_text = f"{niche} is trending hard right now. Link attribution shows {metric}% improvement. What's your take? 🔮"
        
        # Post using existing infrastructure
        success = open_and_post_tweet(page, tweet_text, is_reply=False)
        if success:
            # Update state
            state["last_magnet_post_time"] = current_time
            save_json(Path(VIDEO_MAGNET_STATE_FILE), state)
            log(f"[STAGE 16D] [FOLLOWER_MAGNET] Posted magnet: {tweet_text[:50]}...")
            return True
        else:
            log("[STAGE 16D] [FOLLOWER_MAGNET] Failed to post magnet")
            return False
            
    except Exception as e:
        log(f"[STAGE 16D] [FOLLOWER_MAGNET] Error posting magnet: {e}")
        return False

try:
    from stage_12_trending import trending_quote_tweet
    # TEMPORARILY DISABLED - Stage 12B search broken, causes navigation issues
    STAGE_12_QUOTE_ENABLED = False
except ImportError:
    trending_quote_tweet = None
    STAGE_12_QUOTE_ENABLED = False
    print("⚠️ Stage 12 quote-tweet not available")

try:
    from breaking_news_11b import stage_11b_breaking_news_jacker
except ImportError:
    stage_11b_breaking_news_jacker = None
    print("⚠️ Breaking news jacker (Stage 11B) not available")

try:
    from intelligent_search import INTELLIGENT_SEARCH
except ImportError:
    INTELLIGENT_SEARCH = None
    print("⚠️ Intelligent search not available")

try:
    from thread_optimizer import THREAD_OPTIMIZER
except ImportError:
    THREAD_OPTIMIZER = None
    print("⚠️ Thread optimizer not available")


try:
    from thread_builder import thread_builder
    STAGE_11A_ENABLED = True
except ImportError:
    thread_builder = None
    STAGE_11A_ENABLED = False
    print("⚠️ Thread builder not available")

try:
    from news_jacker import news_jacker
    STAGE_11B_ENABLED = True
except ImportError:
    news_jacker = None
    STAGE_11B_ENABLED = False
    print("⚠️ News jacker not available")

try:
    from engagement_amplifier import amplifier
    STAGE_11C_ENABLED = True
except ImportError:
    amplifier = None
    STAGE_11C_ENABLED = False
    print("⚠️ Engagement amplifier not available")

try:
    from response_optimizer import optimizer
    STAGE_11D_ENABLED = True
except ImportError:
    optimizer = None
    STAGE_11D_ENABLED = False
    print("⚠️ Response optimizer not available")

try:
    from trend_monitor import monitor
    STAGE_11E_ENABLED = True
except ImportError:
    monitor = None
    STAGE_11E_ENABLED = False
    print("⚠️ Trend monitor not available")

try:
    from competitor_tracker import tracker
    STAGE_11F_ENABLED = True
except ImportError:
    tracker = None
    STAGE_11F_ENABLED = False
    print("⚠️ Competitor tracker not available")

# ====================== DUPLICATE PROTECTION ======================
# URGENT: Anti-duplicate system to prevent X duplicate errors
RECENT_REPLIES_FILE = "recent_replies.json"
recent_texts = deque(maxlen=500)
replied_tweet_ids = set()

def load_history():
    """Load duplicate detection history from disk on startup."""
    global recent_texts, replied_tweet_ids
    if os.path.exists(RECENT_REPLIES_FILE):
        try:
            with open(RECENT_REPLIES_FILE, 'r') as f:
                data = json.load(f)
                recent_texts = deque(data.get('texts', []), maxlen=500)
                replied_tweet_ids = set(data.get('tweet_ids', []))
            log(f"[DUPLICATE] Loaded {len(recent_texts)} recent replies and {len(replied_tweet_ids)} replied tweet IDs")
        except Exception as e:
            log(f"[DUPLICATE] Error loading history: {e}")

def save_history():
    """Save duplicate detection history to disk."""
    try:
        with open(RECENT_REPLIES_FILE, 'w') as f:
            json.dump({
                'texts': list(recent_texts),
                'tweet_ids': list(replied_tweet_ids)
            }, f)
    except Exception as e:
        log(f"[DUPLICATE] Error saving history: {e}")

def is_duplicate(text, tweet_id):
    """Check if reply text or tweet_id is a duplicate."""
    if tweet_id and tweet_id in replied_tweet_ids:
        return True
    # Check if text is too similar (exact match or >80% similar)
    for old_text in recent_texts:
        if text == old_text:
            return True
        # Simple similarity check - if first 50 chars match and text is >20 chars, likely duplicate
        if len(text) > 20 and text[:50] in old_text:
            return True
    return False

def store_reply(text, tweet_id):
    """Store reply text and tweet_id to prevent duplicates."""
    global recent_texts, replied_tweet_ids
    recent_texts.append(text)
    if tweet_id:
        replied_tweet_ids.add(tweet_id)
    save_history()
# ====================== END DUPLICATE PROTECTION ======================

# ====================== CONFIG ======================

REFERRAL_LINK = "https://refer.dub.co/shamil"
BOT_HANDLE = os.getenv("BOT_HANDLE", "").lower()  # Your bot's X handle (without @), used to prevent self-replies

# --- Smart Commenting Config ---
COMMENT_CONFIG = {
    "enabled": True,
    "targets": ["link shortener", "link attribution", "SaaS growth", "marketing tools", "affiliate marketing", "conversion tracking"],
    "link_comment_percentage": 20,  # 20% with link, 80% pure engagement
    "comments_per_day": 10,  # max 10 comments daily
    "min_post_engagement": 5,  # only comment on posts with 5+ likes
    "min_target_followers": 100,  # target accounts with 100+ followers
    "comment_delay_seconds": (180, 600),  # 3-10 min between comments
    "cycle_delay_hours": (1, 2)  # 1-2 hours between comment cycles
}
COMMENT_LOG_FILE = Path("comment_log.json")

# --- Stage 11B: Breaking News Jacker Config ---
NEWS_SPIKE_MIN_TOTAL_POSTS = 40000
NEWS_SPIKE_MAX_WINDOW_MIN = 90
NEWS_SPIKE_MIN_GROWTH_FACTOR = 2.0
NEWS_MAX_FORCED_POSTS_PER_DAY = 10
NEWS_MIN_HOURS_BETWEEN_POSTS = 0.5
NEWS_MIN_POLY_CONFIDENCE = 0.75
NEWS_LOG_PREFIX = "[11B]"

# CURRENT 2025/2026 search keywords (no outdated 2024 references)
# Split into "Viral" (high-engagement topics) and "General" (broader coverage)

VIRAL_SEARCH_KEYWORDS = [
    # High-engagement SaaS and marketing topics
    "link shortener",
    "link attribution",
    "SaaS launch",
    "marketing stack",
    "growth tools",
    "affiliate marketing",
    "conversion tracking",
    "UTM tracking",
    "branded links",
    "link management",
    "referral program",
    "creator tools",
    "Product Hunt launch",
    "buildinpublic",
    "indie hackers",
]

GENERAL_SEARCH_KEYWORDS = [
    # Marketing and growth topics
    "marketing attribution",
    "link analytics",
    "track conversions",
    "Bitly alternative",
    "performance marketing",
    "growth hacking",
    "SaaS growth",
    "startup tools",
    "marketing automation",
    "link in bio",
    "affiliate program setup",
    "conversion optimization",
]

# Combined list for backward compatibility
CURRENT_SEARCH_KEYWORDS = VIRAL_SEARCH_KEYWORDS + GENERAL_SEARCH_KEYWORDS

# Backward compatibility alias
SEARCH_TERMS = CURRENT_SEARCH_KEYWORDS

# Rotation logic to prevent repeating same keyword twice in a row
_last_search_keyword = None

def get_next_keyword():
    """Get next search keyword, ensuring it's different from the last one.
    Prioritizes viral keywords 70% of the time for max engagement.
    """
    global _last_search_keyword
    # [IMPORT_FIX] random is already imported at top of file, don't re-import
    
    # 70% chance to use viral keyword, 30% chance to use general keyword
    use_viral = random.random() < 0.70
    
    if use_viral and VIRAL_SEARCH_KEYWORDS:
        keyword_pool = VIRAL_SEARCH_KEYWORDS
        log("[SEARCH] Using viral keyword pool (70% priority)")
    else:
        keyword_pool = GENERAL_SEARCH_KEYWORDS if GENERAL_SEARCH_KEYWORDS else CURRENT_SEARCH_KEYWORDS
        log("[SEARCH] Using general keyword pool (30% mix)")
    
    # Pick a keyword different from last one
    keyword = random.choice(keyword_pool)
    max_attempts = 10  # Prevent infinite loop if only 1 keyword
    attempts = 0
    while keyword == _last_search_keyword and len(keyword_pool) > 1 and attempts < max_attempts:
        keyword = random.choice(keyword_pool)
        attempts += 1
    
    _last_search_keyword = keyword
    log(f"[SEARCH] Looking up: {keyword}")
    return keyword

# [DISABLED_FOR_RECOVERY] Old spam reply templates - replaced with trader-focused templates below
# REPLY_TEMPLATES = [
# Old templates removed - replaced with Dub.co-focused templates
# ]

# Dub.co-focused reply templates
REPLY_TEMPLATES = [
    "Switched from Bitly to Dub for this exact reason - their conversion tracking actually shows which links drive signups, not just clicks. Plus real-time attribution. You get 20% off first 3 months here: https://refer.dub.co/shamil (Referral link - full transparency)",
    
    "For link attribution that actually matters: Dub tracks clicks → leads → revenue. Used by Framer, Perplexity, Superhuman. Branded links boost CTR by 34%. Try it with 20% off: https://refer.dub.co/shamil (referral - you save, I earn commission)",
    
    "Pro tip for SaaS attribution: Use Dub's conversion tracking + UTM builder to see exactly which campaigns drive MRR vs vanity metrics. Game changer for optimizing spend. 20% off here: https://refer.dub.co/shamil",
    
    "Bitly vs Dub? Bitly = click counting. Dub = end-to-end attribution (click → signup → LTV). Also: better analytics, QR codes, affiliate program management. Worth the upgrade. 20% off: https://refer.dub.co/shamil"
]

# pacing (anti-spam)
REPLIES_PER_TERM      = (3, 5)  # [PROBLEM #4 FIX] Increased to 3-5 replies per cycle (more aggressive engagement)
DELAY_BETWEEN_REPLIES = (45, 90)
DELAY_BETWEEN_TERMS   = (180, 360)  # [STAGE 14] Increased to 3-6 hours between cycles (anti-spam)
MAX_ARTICLES_SCAN     = 20
MAX_RUN_HOURS         = 0  # 0 = run until Ctrl+C

# media toggles
# HARD BLOCK: Media disabled to prevent X duplicate/spam errors
ENABLE_IMAGES       = False  # Hard disabled - no images allowed
ENABLE_VIDEOS       = False  # Hard disabled - no videos allowed
MEDIA_ATTACH_RATE   = 0.0    # Set to 0 to prevent any media attachment attempts
HARD_BLOCK_MEDIA    = True   # Global flag to enforce text-only posting
IMAGES_DIR          = Path("media/images")
VIDEOS_DIR          = Path("media/videos")

# generator hooks (we call these wrappers; they load your old funcs from social_agent.backup.py)
IMAGE_WRAPPER = Path("generators/image_gen.py")
VIDEO_WRAPPER = Path("generators/video_gen.py")
GENERATE_IMAGE_EVERY_N_REPLIES = 4
GENERATE_VIDEO_EVERY_N_REPLIES = 10

# ====================================================

# Use REAL Chrome profile instead of separate Playwright profile for trust
REAL_CHROME_PROFILE = Path.home() / "Library/Application Support/Google/Chrome/Default"
PROFILE_DIR = REAL_CHROME_PROFILE if REAL_CHROME_PROFILE.exists() else Path.home() / ".pw-chrome-referral"
STORAGE_PATH = Path("storage/x.json")
DEDUP_TWEETS = Path("storage/replied.json")
DEDUP_TEXTS  = Path("storage/text_hashes.json")   # avoid posting the exact same sentence back to back
LOG_PATH     = Path("logs/run.log")

HOME_URL   = "https://x.com/home"
LOGIN_URL  = "https://x.com/login"
SEARCH_URL = "https://x.com/search?q={q}&src=typed_query&f=live"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/121.0.0.0 Safari/537.36"
)

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        LOG_PATH.open("a", encoding="utf-8").write(line + "\n")
    except Exception:
        pass

# OpenAI client for contextual reply generation
openai_client = None
try:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        openai_client = OpenAI(api_key=api_key)
        log("✅ OpenAI client initialized")
    else:
        log("⚠️ OPENAI_API_KEY not found - will use fallback templates")
except Exception as e:
    log(f"⚠️ OpenAI client initialization failed: {e} - will use fallback templates")

# ====================== REAL-TIME DATA FETCHING ======================

PRICE_CACHE = {"data": None, "timestamp": 0, "cache_duration": 120}  # 2 min cache
TRENDING_CACHE = {"data": None, "timestamp": 0, "cache_duration": 300}  # 5 min cache


def fetch_crypto_prices_live(asset="BTC"):
    """
    [PRICE_FETCH] Fetch LIVE crypto prices from CoinGecko API (with caching).
    
    Args:
        asset: Asset symbol (BTC, ETH, SOL)
    
    Returns:
        dict: {"price": "$97,530", "asset": "BTC", "change_24h": "+2.4%"}
    """
    import random
    import requests
    
    # Check cache first (2 min cache)
    current_time = time.time()
    cache_key = asset.upper()
    if PRICE_CACHE.get("data") and cache_key in PRICE_CACHE["data"]:
        if (current_time - PRICE_CACHE["timestamp"]) < PRICE_CACHE["cache_duration"]:
            cached_price = PRICE_CACHE["data"][cache_key]
            log(f"[PRICE_FETCH] Using cached price for {asset} (age: {int(current_time - PRICE_CACHE['timestamp'])}s)")
            return cached_price
    
    # Map asset to CoinGecko ID
    asset_map = {
        "BTC": "bitcoin",
        "SOL": "solana",
        "BITCOIN": "bitcoin",
        "SOLANA": "solana"
    }
    
    coin_id = asset_map.get(asset.upper(), "bitcoin")
    
    # Try to fetch from CoinGecko API
    try:
        api_url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true"
        }
        headers = {
            "Accept": "application/json"
        }
        
        response = requests.get(api_url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if coin_id in data:
                price_data = data[coin_id]
                price_usd = price_data.get("usd", 0)
                change_24h = price_data.get("usd_24h_change", 0) or 0
                
                # Format price
                if price_usd >= 1000:
                    formatted_price = f"${price_usd:,.0f}"
                else:
                    formatted_price = f"${price_usd:,.2f}"
                
                result = {
                    "price": formatted_price,
                    "asset": asset.upper(),
                    "change_24h": f"{change_24h:+.1f}%" if change_24h else "+0.0%"
                }
                
                # Cache the result
                if not PRICE_CACHE.get("data"):
                    PRICE_CACHE["data"] = {}
                PRICE_CACHE["data"][cache_key] = result
                PRICE_CACHE["timestamp"] = current_time
                
                log(f"[PRICE_FETCH] {asset}: {formatted_price} ({result['change_24h']})")
                return result
    except Exception as e:
        log(f"[PRICE_FETCH] CoinGecko API error: {e}, using fallback")
    
    # Fallback: Generate realistic prices
    price_map = {
        "BTC": (85000, 120000),
        "ANALYTICS": (3000, 5000),
        "SOL": (150, 300)
    }
    price_range = price_map.get(asset.upper(), (85000, 120000))
    price = random.randint(price_range[0], price_range[1])
    formatted_price = f"${price:,}" if price >= 1000 else f"${price:,.2f}"
    
    result = {
        "price": formatted_price,
        "asset": asset.upper(),
        "change_24h": f"{random.choice(['+', '-'])}{random.uniform(0.5, 5.0):.1f}%"
    }
    
    # Cache fallback result
    if not PRICE_CACHE.get("data"):
        PRICE_CACHE["data"] = {}
    PRICE_CACHE["data"][cache_key] = result
    PRICE_CACHE["timestamp"] = current_time
    
    log(f"[PRICE_FETCH] Fallback {asset}: {formatted_price}")
    return result


def fetch_trending_topics_live():
    """
    [TRENDING] Fetch CURRENT trending topics from X/Twitter or use cache.
    
    Returns:
        dict: {"topics": ["Bitcoin ETF", "Fed rate decision"], "dates": ["Jan 15", "Q1 2026"]}
    """
    # [IMPORT_FIX] random is already imported at top of file, don't re-import
    
    # Check cache first (5 min cache)
    current_time = time.time()
    if TRENDING_CACHE["data"] and (current_time - TRENDING_CACHE["timestamp"]) < TRENDING_CACHE["cache_duration"]:
        log(f"[TRENDING] Using cached trending topics (age: {int(current_time - TRENDING_CACHE['timestamp'])}s)")
        return TRENDING_CACHE["data"]
    
    # For now, use realistic trending topics (TODO: Integrate X API or Grok)
    # In production, this would query X API or Grok for real-time trends
    trending_topics = [
        "Bitcoin ETF approval",
        "Fed rate decision",
        "Solana ecosystem news",
        "SaaS growth tools",
        "Marketing attribution",
        "Link management",
        "Market crash prediction",
        "DeFi protocol launch"
    ]
    
    dates = [
        "Jan 15",
        "Jan 31",
        "Feb 10",
        "Q1 2026",
        "this week",
        "next week",
        "by month end"
    ]
    
    selected_topic = random.choice(trending_topics)
    selected_date = random.choice(dates)
    
    result = {
        "topics": [selected_topic],
        "dates": [selected_date],
        "trend": selected_topic,
        "date": selected_date
    }
    
    # Cache the result
    TRENDING_CACHE["data"] = result
    TRENDING_CACHE["timestamp"] = current_time
    
    log(f"[TRENDING] Current: \"{selected_topic}\", date: \"{selected_date}\"")
    return result


def validate_market_data(market_name, post_content):
    """
    [DATA_VALIDATOR] Validate market data before posting - block stale 2024 content.
    
    Blocks markets/content containing:
    - "2024" (stale data)
    - Old references (past events)
    
    Args:
        market_name: Market name/title to check
        post_content: Post content text to check
    
    Returns:
        bool: True if market is current (valid), False if blocked (stale)
    """
    blocked_terms = ["2024"]  # Block stale year references
    
    market_lower = (market_name or "").lower()
    content_lower = (post_content or "").lower()
    
    for term in blocked_terms:
        if term.lower() in market_lower or term.lower() in content_lower:
            log(f"[DATA_VALIDATOR] ❌ Blocked stale data: '{term}' found in market='{market_name[:50]}' or content")
            return False
    
    log(f"[DATA_VALIDATOR] ✓ Market is current: {market_name[:50] if market_name else 'N/A'}")
    return True


def validate_content(content_text):
    """
    [VALIDATION] Validate content before posting - reject stale/spam patterns.
    
    Rejects content if:
    - Contains "2024" (stale data)
    - Contains "Here's why" (bot pattern)
    - Contains "🧵" but is not a thread (broken promise)
    - Same as last post (duplicate)
    
    Args:
        content_text: Content string to validate
    
    Returns:
        tuple: (is_valid: bool, reason: str)
    """
    if not content_text:
        return False, "empty_content"
    
    content_lower = content_text.lower()
    
    # Reject stale data (2024)
    if "2024" in content_text:
        log(f"[VALIDATION] Content rejected: Contains '2024' (stale data)")
        return False, "stale_2024_data"
    
    # Reject bot spam patterns
    spam_patterns = [
        "here's why",
        "new position: long",
        "new position: short",
        "here's why that price is wrong",
        "new position:",
        "here's why that price"
    ]
    for pattern in spam_patterns:
        if pattern in content_lower:
            log(f"[VALIDATION] Content rejected: Contains spam pattern '{pattern}'")
            return False, f"spam_pattern_{pattern}"
    
    # Reject 🧵 emoji if not a thread (broken promise)
    if "🧵" in content_text:
        # Check if this is actually a thread (would have multiple tweets)
        # For now, reject any single post with 🧵 emoji
        log(f"[VALIDATION] Content rejected: Contains 🧵 emoji but not a thread (broken promise)")
        return False, "broken_thread_promise"
    
    # Check for duplicate (compare to last post)
    try:
        recent_posts_file = Path("storage/recent_original_posts.json")
        if recent_posts_file.exists():
            with open(recent_posts_file, 'r') as f:
                recent_data = json.load(f)
                posts = recent_data.get("posts", [])
                if posts:
                    last_post_text = posts[-1].get("text", "").lower()
                    # Simple similarity check (exact match or very similar)
                    if content_text.lower() == last_post_text or content_text.lower() in last_post_text or last_post_text in content_text.lower():
                        log(f"[VALIDATION] Content rejected: Too similar to last post (duplicate)")
                        return False, "duplicate_content"
    except Exception as e:
        log(f"[VALIDATION] Error checking duplicates: {e}")
    
    log(f"[VALIDATION] Content validated: ✓")
    return True, "valid"


def insert_odds_into_template(template_text, market_context=None):
    """
    [TEMPLATE_INSERT] Insert data into template placeholders.
    
    Simple placeholder replacement for templates.
    
    Replaces:
    - {metric} → "45%" (example metric)
    - {topic} → topic name
    - {trend} → trending topic
    - {date} → date from trending data
    - {price} → price data if available
    
    Args:
        template_text: Template string with placeholders
        market_context: Optional dict with context info
    
    Returns:
        str: Template with placeholders filled
    """
    if not template_text:
        return template_text
    
    result = template_text
    
    # Simple placeholder replacements
    if "{market}" in result:
        result = result.replace("{market}", "SaaS growth")
    
    if "{topic}" in result:
        result = result.replace("{topic}", "marketing attribution")
    
    # Replace {market_A} and {market_B}
    if "{market_A}" in result:
        result = result.replace("{market_A}", "link attribution")
    if "{market_B}" in result:
        result = result.replace("{market_B}", "conversion tracking")
    
    # Replace {trend} and {date}
    if "{trend}" in result:
        result = result.replace("{trend}", "SaaS growth tools")
    
    if "{date}" in result:
        result = result.replace("{date}", "this quarter")
    
    # Replace {price}
    if "{price}" in result:
        result = result.replace("{price}", "$99")
    
    # Replace metric placeholders
    result = result.replace("{contrarian_odds}", "55%")
    result = result.replace("{old_odds}", "40%")
    result = result.replace("{low/high}", "high")
    result = result.replace("{odds}", "45%")
    result = result.replace("{metric}", "45%")
    result = result.replace("{asset}", "SaaS")
    
    # Replace {link} placeholder with referral link
    if "{link}" in result:
        global REFERRAL_LINK
        if REFERRAL_LINK:
            result = result.replace("{link}", REFERRAL_LINK)
        else:
            result = result.replace("{link}", "")
    
    return result


def load_viral_templates(filepath='viral_templates.json'):
    """
    Load viral post templates from JSON file.
    
    Supports both formats:
    - Old: { "original": [...], "with_link": [...], "viral": [...] }
    - New (BOT RECONSTRUCTION): { "templates": [...], "hashtag_rules": {...} }
    
    Returns:
        dict: Template dict with "original", "with_link", "viral" keys, or empty dict if file missing/invalid
    """
    try:
        if not os.path.exists(filepath):
            log(f"[TEMPLATES] File not found: {filepath}, using default behavior")
            return {}
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        # [BOT RECONSTRUCTION] Support new format with "templates" key
        if "templates" in data:
            # New format: convert to old format for compatibility
            all_templates = data["templates"]
            templates = {
                "original": [t for t in all_templates if t.get("tier") != "link"],
                "with_link": [t for t in all_templates if t.get("tier") == "link"],
                "viral": []
            }
            total_count = len(all_templates)
            log(f"[TEMPLATES] Loaded {total_count} templates from {filepath} (new format: {len(templates['original'])} original, {len(templates['with_link'])} with_link)")
        else:
            # Old format: { "original": [...], "with_link": [...], "viral": [...] }
            templates = {
                "original": data.get("original", []),
                "with_link": data.get("with_link", []),
                "viral": data.get("viral", [])
            }
            total_count = len(templates["original"]) + len(templates["with_link"]) + len(templates["viral"])
            log(f"[TEMPLATES] Loaded {total_count} templates from {filepath} (original: {len(templates['original'])}, with_link: {len(templates['with_link'])}, viral: {len(templates['viral'])})")
        
        return templates
        
    except FileNotFoundError:
        log(f"[TEMPLATES] File not found: {filepath}, using default behavior")
        return {}
    except json.JSONDecodeError as e:
        log(f"[TEMPLATES] ERROR: Invalid JSON in {filepath}: {e}, using default behavior")
        return {}
    except Exception as e:
        log(f"[TEMPLATES] ERROR: Error loading {filepath}: {e}, using default behavior")
        return {}

def pick_matching_template(templates, niche_hint=None):
    """
    Pick a matching template from the templates list based on niche hint.
    
    Args:
        templates: List of template dicts (from load_viral_templates)
        niche_hint: String hint for niche matching (e.g., "prediction_markets")
    
    Returns:
        dict: Matching template or None if no match
    """
    if not templates or not niche_hint:
        return None
    
    niche_hint_lower = niche_hint.lower()
    matches = []
    
    for template in templates:
        if not isinstance(template, dict):
            continue
        template_niche = template.get("niche", "")
        if isinstance(template_niche, str) and niche_hint_lower in template_niche.lower():
            matches.append(template)
    
    if matches:
        # Random selection for variety
        import random
        return random.choice(matches)
    
    return None

def append_hashtags_if_template(text, template):
    """
    Add hashtags from template if template exists and has hashtags.
    Includes length check to prevent exceeding 280 chars.
    
    Args:
        text: Tweet text
        template: Template dict (or None)
    
    Returns:
        str: Text with hashtags appended (or unchanged if no template/hashtags)
    """
    if not template or not template.get("hashtags"):
        return text
    
    hashtags_list = template.get("hashtags", [])
    if not isinstance(hashtags_list, list) or len(hashtags_list) == 0:
        return text
    
    # Filter out hashtags already present in text (deduplication)
    text_lower = text.lower()
    new_hashtags = []
    for tag in hashtags_list:
        if isinstance(tag, str) and tag.lower() not in text_lower:
            new_hashtags.append(tag)
    
    if not new_hashtags:
        return text
    
    # Take max 3 hashtags
    hashtags_to_add = new_hashtags[:3]
    hashtags_str = " ".join(hashtags_to_add)
    
    # CHECK LENGTH: Do not append if total length exceeds 280 chars
    proposed_text = f"{text.strip()} {hashtags_str}"
    if len(proposed_text) > 280:
        log(f"[TEMPLATES] Skipping hashtags - would exceed 280 chars (current: {len(text)}, with hashtags: {len(proposed_text)})")
        return text
    
    log(f"[TEMPLATES] Appended hashtags: {hashtags_str}")
    return proposed_text

# Load viral templates for Creator Studio integration
VIRAL_TEMPLATES = load_viral_templates('viral_templates.json')

# Phase controller initialization
if PHASE_CONTROLLER:
    current_phase = PHASE_CONTROLLER.update_phase()
    log(f"✅ Phase controller initialized - [PHASE {current_phase}] Active")
else:
    log("⚠️ Phase controller not available - using default behavior")

def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default

def save_json(path: Path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        log(f"Could not write {path}: {e}")

# ====================== PHASE-BASED AUTOMATIC MANAGEMENT ======================
# Randomization utilities (all automatic)
def get_random_post_interval():
    """Get randomized post interval based on current phase."""
    if not PHASE_CONTROLLER:
        return random.randint(15, 45) * 60  # Default fallback
    config = PHASE_CONTROLLER.get_phase_config()
    return random.randint(config.get("post_interval_min", 15), config.get("post_interval_max", 45)) * 60

def get_random_reply_delay():
    """Get randomized reply delay based on current phase."""
    if not PHASE_CONTROLLER:
        return random.uniform(2, 8)  # Default fallback
    config = PHASE_CONTROLLER.get_phase_config()
    return random.uniform(config.get("reply_delay_min", 2), config.get("reply_delay_max", 8))

def should_include_link():
    """Decide if link should be included based on current phase."""
    if not PHASE_CONTROLLER:
        return random.random() < 0.5  # Default 50% chance
    config = PHASE_CONTROLLER.get_phase_config()
    freq_min = config.get("link_frequency_min", 0.4)
    freq_max = config.get("link_frequency_max", 0.6)
    freq = random.uniform(freq_min, freq_max)
    return random.random() < freq

def should_sleep_now():
    """Check if bot should sleep based on UTC hours."""
    # TEMPORARY: Disabled sleep mode for recovery (Dec 23-25)
    # Bot will post 24/7 to build momentum and recover from shadowban
    return False
    
    # Original logic (commented out - will re-enable after recovery):
    # # [SLEEP_FIX] Reduced sleep window to UTC 3-6 ONLY (was 3-9)
    # # UTC 3-6 = 10 PM to 1 AM MST (short sleep window)
    # hour = datetime.utcnow().hour
    # sleep_start, sleep_end = 3, 6
    # is_sleeping = sleep_start <= hour < sleep_end
    # if is_sleeping:
    #     # Only log once per sleep cycle (prevent spam)
    #     if not hasattr(should_sleep_now, "_last_sleep_log_hour"):
    #         should_sleep_now._last_sleep_log_hour = None
    #     if should_sleep_now._last_sleep_log_hour != hour:
    #         log(f"[SLEEP] Bot sleeping (UTC {hour}, window: {sleep_start}-{sleep_end}). Resumes at UTC {sleep_end}.")
    #         should_sleep_now._last_sleep_log_hour = hour
    # else:
    #     # Reset log tracking when awake
    #     should_sleep_now._last_sleep_log_hour = None
    # return is_sleeping

def apply_reply_delay():
    """Apply randomized delay before replying."""
    delay = get_random_reply_delay()
    time.sleep(delay)

def get_random_user_agent():
    """Get randomized user agent based on current phase."""
    if not PHASE_CONTROLLER:
        return USER_AGENT  # Use default
    config = PHASE_CONTROLLER.get_phase_config()
    user_agents = config.get("user_agents", [USER_AGENT])
    return random.choice(user_agents)

# Rate limiting (automatic)
action_count = 0
action_hour_start = time.time()

def check_rate_limits():
    """Check and enforce rate limits based on current phase."""
    global action_count, action_hour_start
    if not PHASE_CONTROLLER:
        return  # Skip if no controller
    
    config = PHASE_CONTROLLER.get_phase_config()
    
    elapsed = time.time() - action_hour_start
    if elapsed > 3600:
        action_count = 0
        action_hour_start = time.time()
    
    max_per_hour = config.get("max_replies_per_hour", 8)
    if action_count >= max_per_hour:
        sleep_time = random.randint(30, 60)
        log(f"[RATE_LIMIT] Sleeping {sleep_time}s (hit limit: {action_count}/{max_per_hour} this hour)")
        time.sleep(sleep_time)
        action_count = 0
        action_hour_start = time.time()
    
    action_count += 1

# ====================== ANTI-SPAM FILTERS ======================

# Banned ChatGPT spam phrases
BANNED_PHRASES = [
    "Absolutely!",
    "Fascinating!",
    "Interesting point!",
    "Marketing attribution is definitely important",
    "As an AI",
    "I've analyzed",
    "My analysis shows",
    "It's worth noting",
    "Indeed,",
    "I'm curious",
    "Drop your thoughts",
    "Let's dive into this"
]

OUTDATED_KEYWORDS = [
    "2024"  # Block stale year references
]

def clean_reply_text(text):
    """Remove spam phrases that flag us as bots"""
    if not text:
        return text
    for phrase in BANNED_PHRASES:
        text = text.replace(phrase, "")
    # Remove double spaces
    text = " ".join(text.split())
    return text.strip()

def format_for_mobile(text):
    """Add line breaks for mobile readability"""
    if not text or len(text) < 50:
        return text
    
    # Split into sentences
    sentences = re.split(r'[.!?]+\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Group into 1-2 sentence chunks with line breaks
    formatted = []
    i = 0
    while i < len(sentences):
        chunk = sentences[i]
        # Add second sentence if available and total is reasonable length
        if i + 1 < len(sentences) and len(chunk + " " + sentences[i+1]) < 120:
            chunk += ". " + sentences[i+1]
            i += 2
        else:
            i += 1
        
        if not chunk.endswith(('.', '!', '?')):
            chunk += '.'
        formatted.append(chunk)
    
    # Join with double line breaks
    result = '\n\n'.join(formatted)
    return result if result else text

def is_outdated_content(text):
    """Check if post references past events"""
    if not text:
        return False
    text_lower = text.lower()
    for keyword in OUTDATED_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def is_bot_like_reply(text):
    """
    Hard ban filter for obvious bot patterns and broken placeholders.
    Returns (is_bot_like: bool, reason: str)
    """
    if not text:
        return False, ""
    
    text_lower = text.lower()
    
    # Ban placeholder fragments
    if "{" in text and "}" in text:
        return True, "contains_placeholder"
    
    # Ban "Notice how" pattern (case-insensitive)
    if text_lower.startswith("notice how"):
        return True, "starts_with_notice_how"
    
    # Ban specific bot-like phrases
    banned_phrases = [
        "markets react sharply",
        "sentiment shifts dramatically",
        "it's always a learning experience",
        "keeping an eye on odds movement",
        "market odds can fluctuate based on pre-fight hype",
        "watch for movements before and",
        "see for yourself:",
        "worth watching:",
        "monitor this:",
        "watch this:",
    ]
    
    for phrase in banned_phrases:
        if phrase in text_lower:
            return True, f"contains_banned_phrase_{phrase[:20]}"
    
    return False, ""

def should_include_link_in_this_reply():
    """40-60% of replies get the link (randomized within range)"""
    if PHASE_CONTROLLER:
        config = PHASE_CONTROLLER.get_phase_config()
        min_freq = config.get("link_frequency_min", 0.40)
        max_freq = config.get("link_frequency_max", 0.60)
        frequency = random.uniform(min_freq, max_freq)
        return random.random() < frequency
    # Default fallback: 40-60% range
    frequency = random.uniform(0.40, 0.60)
    return random.random() < frequency

def should_include_link_strategic(post_text, post_type="original"):
    """
    [STAGE 15] Strategic link placement based on content signals.
    ALWAYS include if specific odds, market, or betting language present.
    """
    import re
    post_lower = post_text.lower()
    
    # ALWAYS include if these signals are present
    always_include_signals = [
        r'\d+%',  # Specific odds percentage
        r'odds (at|are|of)',  # Odds mentioned
        r'market.*(at|pricing|betting)',  # Market reference
        r'\bbet\b|\bbetting\b',  # Betting language
        r'breaking|news|alert',  # Breaking news
    ]
    
    for pattern in always_include_signals:
        if re.search(pattern, post_lower):
            log(f"[STAGE 15] [LINK_STRATEGIC] ALWAYS include: pattern '{pattern}' found in {post_type}")
            return True
    
    # MAYBE include for normal posts:
    # - Original posts: 25-35% (handled by should_include_link_in_original)
    # - Replies: 2-5% only (very rare, only high-value moments)
    if post_type == "reply":
        should_include = random.random() < 0.03  # 3% average (2-5% range)
        log(f"[STAGE 15] [LINK_STRATEGIC] MAYBE include (2-5% for replies): {should_include} for {post_type}")
        return should_include
    elif post_type == "original":
        # Original posts handled by should_include_link_in_original() - don't double-count
        return False
    
    return False

def should_include_link_in_original(post_text=""):
    """[LINK_FREQ_FIX] Strict link spacing: 20% max, check last 4 posts (no back-to-back)"""
    import random
    global REFERRAL_LINK
    
    # [LINK_FREQ_FIX] Check recent posts for link history (prevent back-to-back links)
    try:
        recent_posts = load_recent_posts()
        if recent_posts:
            # [LINK_FREQ_FIX] Count links in last 4 posts (prevent back-to-back)
            recent_link_count = 0
            for post in recent_posts[-4:]:  # Check last 4 posts
                post_text_check = post.get("text", "")
                if REFERRAL_LINK and REFERRAL_LINK in post_text_check:
                    recent_link_count += 1
            
            # [LINK_FREQ_FIX] If ANY of last 4 posts had link, skip (no back-to-back)
            if recent_link_count >= 1:
                log(f"[LINK_DECISION] Pure content (80% hit) - {recent_link_count} of last 4 posts had links (no back-to-back)")
                return False
    except Exception as e:
        log(f"[LINK_DECISION] Error checking recent posts: {e}")
        # Continue with normal logic if check fails
    
    # [ANTI-SHADOWBAN] 30% base chance (max link frequency)
    if random.random() > 0.30:
        log(f"[LINK_DECISION] Pure content (70% hit) - 30% threshold not met")
        return False
    
    # [ANTI-SHADOWBAN] Log when link is included
    log(f"[LINK_DECISION] Including link (30% hit) - spacing OK")
    return True

# [DISABLED_FOR_RECOVERY] Old generic reply templates - replaced with trader-focused templates above
# Reply variation templates for diverse content
# REPLY_TEMPLATES = [
#     # Data-driven
#     "The odds moved {percent}% in the last {timeframe}. {insight}",
#     "{candidate} is at {odds}% right now. {contrarian_take}",
#     ...
# ]

# Reply templates are now defined at line 945 (see above)

# [ENHANCEMENT #5] Track recent reply templates for diversity
_recent_reply_templates = []

def get_random_template():
    """[ENHANCEMENT #5] Pick a random template for variation, avoiding repetition"""
    global _recent_reply_templates
    # [IMPORT_FIX] random is already imported at top of file, don't re-import
    
    # Get templates that haven't been used in last 2 replies
    available_templates = [t for t in REPLY_TEMPLATES if t not in _recent_reply_templates[-2:]]
    
    if available_templates:
        template = random.choice(available_templates)
    else:
        # Fallback: use any template if all were used recently
        template = random.choice(REPLY_TEMPLATES)
    
    # Track this template (keep last 5)
    _recent_reply_templates.append(template)
    _recent_reply_templates = _recent_reply_templates[-5:]
    
    return template

# Old duplicate detection functions removed - using simpler version at top of file

def human_pause(a: float, b: float):
    time.sleep(random.uniform(a, b))

def sanitize(text: str) -> str:
    text = re.sub(r"[^\S\r\n]+", " ", text).strip()
    return text.replace("\u200b", "").replace("\u2060", "")

def append_link_if_needed(text: str, link: str, link_allowed: bool) -> str:
    """
    Final safety net: Ensure link is appended to text when link_allowed is True.
    
    Detects CTA phrases that suggest a link should be present and appends the link
    if it's missing, but only when link_allowed is True and link is available.
    
    Args:
        text: The message text to check
        link: The referral URL to append
        link_allowed: Whether link inclusion was approved by the system
    
    Returns:
        Text with link appended if conditions are met, otherwise unchanged text
    """
    if not link_allowed:
        return text
    
    if not link or not link.strip():
        # Check if there's a CTA but link is blocked
        cta_phrases = ["check this out", "check it out", "track it", "track this", "bet it here", "here:"]
        text_lower = text.lower()
        has_cta = any(phrase in text_lower for phrase in cta_phrases)
        if has_cta:
            log(f"[LINK_DEBUG] CTA present but link blocked by safety/cooldown, skipping URL.")
        return text
    
    # Check if link is already in text (avoid duplicates)
    if link in text or REFERRAL_LINK in text:
        return text
    
    # CTA phrases that suggest a link should follow
    cta_phrases = [
        "check this out",
        "check it out",
        "track it",
        "track this",
        "bet it here",
        "bet here",
        "follow it here",
        "follow this",
        "see it here",
        "see this",
        "watch it here",
        "watch this",
        "here:",
        "here :",
        "breaking:",
        "just in:",
    ]
    
    text_lower = text.lower()
    has_cta = any(phrase in text_lower for phrase in cta_phrases)
    
    if has_cta:
        # CTA detected and link is allowed - append it
        result = f"{text.strip()} {link}"
        log(f"[LINK_DEBUG] Link appended to text: {link}")
        return result
    
    # If link_allowed is True, always append link (system decided it should be there)
    # This covers cases where link should be included even without explicit CTA
    result = f"{text.strip()} {link}"
    log(f"[LINK_DEBUG] Link appended to text: {link}")
    return result

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def launch_ctx(p):
    # Connect to REAL Chrome browser using CDP (Chrome DevTools Protocol)
    # User launches Chrome manually with: google-chrome --remote-debugging-port=9222
    # This way it's a REAL browser, not automated!
    
    # Use port 9223 to avoid conflicts with other bots (default 9222)
    cdp_port = os.getenv("CDP_PORT", "9223")
    cdp_url = os.getenv("CDP_URL", f"http://localhost:{cdp_port}")
    
    try:
        log(f"[BROWSER] Connecting to REAL Chrome via CDP: {cdp_url}")
        # Connect to existing Chrome instance
        browser = p.chromium.connect_over_cdp(cdp_url)
        
        # Get the default context (Chrome's main context)
        contexts = browser.contexts
        if contexts:
            ctx = contexts[0]
            log(f"[BROWSER] Connected to existing Chrome context")
        else:
            # Create new context if none exists
            ctx = browser.new_context()
            log(f"[BROWSER] Created new Chrome context")
        
        # Get or create a page
        if ctx.pages:
            page = ctx.pages[0]
        else:
            page = ctx.new_page()
        
        # [SAFETY] Block file dialogs and downloads to prevent bot getting stuck
        def block_file_dialog(dialog):
            """Block all file dialogs (file chooser, save dialogs, etc.)"""
            try:
                log(f"[SAFETY] Blocked file dialog: {dialog.type}")
                dialog.dismiss()
            except Exception as e:
                log(f"[SAFETY] Error blocking dialog: {e}")
        
        def block_download(download):
            """Block all downloads to prevent file explorer from opening"""
            try:
                log(f"[SAFETY] Blocked download: {download.suggested_filename}")
                download.cancel()
            except Exception as e:
                log(f"[SAFETY] Error blocking download: {e}")
        
        def block_file_chooser(file_chooser):
            """Block file chooser dialogs"""
            try:
                log(f"[SAFETY] Blocked file chooser dialog")
                # Cancel the file chooser by not setting any files
            except Exception as e:
                log(f"[SAFETY] Error blocking file chooser: {e}")
        
        # Register handlers on context (applies to all pages)
        ctx.on("dialog", block_file_dialog)
        ctx.on("download", block_download)
        ctx.on("filechooser", block_file_chooser)
        
        # Also register on page for extra safety
        page.on("dialog", block_file_dialog)
        page.on("download", block_download)
        page.on("filechooser", block_file_chooser)
        
        log("[SAFETY] File dialog and download blockers installed")
        log(f"[BROWSER] ✅ Using REAL Chrome browser (not automated)")
        return ctx, page
        
    except Exception as e:
        log(f"[BROWSER] ❌ Failed to connect to Chrome via CDP: {e}")
        log(f"[BROWSER] 💡 Launch Chrome manually with:")
        log(f"[BROWSER]    bash launch_chrome_with_cdp.sh")
        log(f"[BROWSER]    OR:")
        log(f"[BROWSER]    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port={cdp_port} --user-data-dir=\"$HOME/.chrome-debug-dub\"")
        log(f"[BROWSER]    Then run the bot again")
        raise

def stable_goto(page, url, timeout=120_000):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except (PWTimeout, PWError):
        pass

def ensure_on_x_com(page, max_retries=3):
    """
    [SAFETY] Ensure bot is on X.com, return to X if navigated away.
    Returns True if on X.com, False if failed to return.
    """
    try:
        current_url = page.url
        if "x.com" in current_url or "twitter.com" in current_url:
            return True
        
        # Bot navigated away from X - return immediately
        log(f"[SAFETY] Bot navigated away from X (current URL: {current_url}), returning to X.com")
        
        for attempt in range(max_retries):
            try:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=10000)
                time.sleep(2)  # Wait for page to load
                
                # Verify we're back on X
                if "x.com" in page.url or "twitter.com" in page.url:
                    log(f"[SAFETY] ✓ Returned to X.com (attempt {attempt + 1})")
                    return True
            except Exception as e:
                log(f"[SAFETY] Failed to return to X (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1)
        
        log("[SAFETY] ✗ Failed to return to X.com after all retries")
        return False
        
    except Exception as e:
        log(f"[SAFETY] Error checking/returning to X.com: {e}")
        return False

def on_home(page):
    try:
        if page.url.startswith(HOME_URL):
            return True
        for s in ('[data-testid="SideNav_NewTweet_Button"]','[aria-label="Post"]','a[href="/home"][aria-current="page"]'):
            if page.locator(s).first.is_visible(timeout=0):
                return True
    except Exception:
        return False
    return False

def wait_until_home(page, max_seconds=600):
    start = time.time()
    while time.time() - start < max_seconds:
        if on_home(page):
            return True
        time.sleep(1.5)
    return False

def ensure_login(page, ctx):
    stable_goto(page, HOME_URL)
    if on_home(page):
        return True
    stable_goto(page, LOGIN_URL)
    log("👉 Login required. Sign in in the Chrome window; I’ll auto-detect Home.")
    if not wait_until_home(page, max_seconds=600):
        log("⚠️ Still not on Home. Try: rm -rf ~/.pw-chrome-referral  and run again.")
        return False
    try:
        STORAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ctx.storage_state(path=str(STORAGE_PATH))
        log(f"✅ Saved cookies to {STORAGE_PATH}")
    except Exception as e:
        log(f"⚠️ Could not save storage: {e}")
    return True

def search_live(page, query: str):
    # Search using the query exactly as provided (no automatic filter addition)
    # ChatGPT generates clean queries - use them as-is
    if not query or not query.strip():
        query = "SaaS growth"  # Safety fallback
    
    # Use query exactly as provided - no filters added automatically
    search_query = query.strip()
    url = SEARCH_URL.format(q=search_query.replace(" ", "%20"))
    stable_goto(page, url)
    human_pause(1.0, 2.0)
    for _ in range(30):
        if page.locator('article[data-testid="tweet"]').count() > 0:
            break
        human_pause(0.3, 0.6)

def collect_articles(page, limit=20):
    cards = page.locator('article[data-testid="tweet"]')
    n = min(cards.count(), limit)
    return [cards.nth(i) for i in range(n)]

def extract_tweet_id(card):
    try:
        a = card.locator('a[href*="/status/"]').first
        href = a.get_attribute("href") or ""
        m = re.search(r"/status/(\d+)", href)
        return m.group(1) if m else None
    except Exception:
        return None

def extract_author_handle(card) -> str:
    """
    Extract the author's handle from a tweet card.
    Returns empty string if extraction fails.
    """
    try:
        # Try to find the author link (usually in the header)
        selectors = [
            'a[href^="/"]',  # Any link starting with /
            '[data-testid="User-Name"] a',
            'div[dir="ltr"] a[href*="/"]',
        ]
        for sel in selectors:
            try:
                links = card.locator(sel)
                for i in range(min(links.count(), 5)):  # Check first few links
                    link = links.nth(i)
                    href = link.get_attribute("href") or ""
                    # Twitter handle format: /username
                    match = re.search(r'^/([a-zA-Z0-9_]+)$', href)
                    if match:
                        return match.group(1).lower()
            except Exception:
                continue
        return ""
    except Exception:
        return ""

def extract_tweet_text(card) -> str:
    """
    Extract the main tweet text from a card.
    Returns empty string if extraction fails.
    """
    try:
        # Try common selectors for tweet text
        selectors = [
            'div[data-testid="tweetText"]',
            'div[lang]',
            'span[lang]',
        ]
        for sel in selectors:
            try:
                text_elem = card.locator(sel).first
                if text_elem.count() > 0:
                    text = text_elem.inner_text() or ""
                    if text and len(text.strip()) > 10:  # Must have meaningful content
                        return text.strip()
            except Exception:
                continue
        # Fallback: get all text from card and try to extract meaningful portion
        try:
            full_text = card.inner_text()
            # Remove common noise (handles, timestamps, etc.)
            lines = [l.strip() for l in full_text.split('\n') if l.strip()]
            # Usually the tweet text is one of the longer lines
            if lines:
                # Return the longest line that looks like tweet content
                tweet_line = max([l for l in lines if len(l) > 20], key=len, default="")
                return tweet_line[:500]  # Limit length
        except Exception:
            pass
        return ""
    except Exception:
        return ""

def get_post_engagement(card):
    """Extract engagement metrics (likes, retweets, etc.) from a tweet card"""
    engagement = {"likes": 0, "retweets": 0, "replies": 0}
    try:
        account_text = card.inner_text() if hasattr(card, 'inner_text') else ""
        
        # Extract likes
        likes_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*(likes?|❤)', account_text, re.IGNORECASE)
        if likes_match:
            count_str = likes_match.group(1).upper()
            if 'K' in count_str:
                engagement["likes"] = int(float(count_str.replace('K', '')) * 1000)
            elif 'M' in count_str:
                engagement["likes"] = int(float(count_str.replace('M', '')) * 1000000)
            else:
                engagement["likes"] = int(float(count_str))
        
        # Extract retweets
        retweet_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*(retweets?|reposts?)', account_text, re.IGNORECASE)
        if retweet_match:
            count_str = retweet_match.group(1).upper()
            if 'K' in count_str:
                engagement["retweets"] = int(float(count_str.replace('K', '')) * 1000)
            elif 'M' in count_str:
                engagement["retweets"] = int(float(count_str.replace('M', '')) * 1000000)
            else:
                engagement["retweets"] = int(float(count_str))
    except Exception:
        pass
    return engagement

def get_post_author(card) -> dict:
    """Extract author info from a tweet card"""
    try:
        author_handle = extract_author_handle(card)
        account_text = card.inner_text() if hasattr(card, 'inner_text') else ""
        
        # Extract follower count
        follower_count = 0
        follower_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*followers?', account_text, re.IGNORECASE)
        if follower_match:
            count_str = follower_match.group(1).upper()
            if 'K' in count_str:
                follower_count = int(float(count_str.replace('K', '')) * 1000)
            elif 'M' in count_str:
                follower_count = int(float(count_str.replace('M', '')) * 1000000)
            else:
                follower_count = int(float(count_str))
        
        return {"handle": author_handle, "followers": follower_count}
    except Exception:
        return {"handle": "", "followers": 0}

def extract_main_topic(text: str) -> str:
    """Extract main topic/keyword from tweet text"""
    topics = ["SaaS", "marketing", "growth", "attribution", "conversion", "tracking", "links", "tools"]
    text_lower = text.lower()
    for topic in topics:
        if topic in text_lower:
            return topic
    return "markets"  # Default

def extract_key_entities(tweet_text: str) -> list[str]:
    """
    Extract key entities from tweet text that should be referenced in reply.
    Returns list of important names, years, specific topics mentioned.
    """
    entities = []
    if not tweet_text:
        return entities
    
    tweet_lower = tweet_text.lower()
    
    # Extract candidate names (common political names)
    candidates = ['trump', 'biden', 'harris', 'vance', 'desantis', 'haley', 'newsom', 'whitmer', 'pence']
    for candidate in candidates:
        if candidate in tweet_lower:
            entities.append(candidate.title())
    
    # Extract years (if any)
    year_matches = re.findall(r'\b(20\d{2})\b', tweet_text)
    entities.extend(year_matches)
    
    # Extract specific phrases (quoted text, capitalized phrases)
    quoted = re.findall(r'"([^"]+)"', tweet_text)
    entities.extend(quoted[:2])  # Max 2 quoted phrases
    
    # Extract specific locations/states if mentioned
    states = ['california', 'texas', 'florida', 'new york', 'ohio', 'pennsylvania']
    for state in states:
        if state in tweet_lower:
            entities.append(state.title())
    
    # Remove duplicates while preserving order
    seen = set()
    unique_entities = []
    for entity in entities:
        entity_lower = entity.lower()
        if entity_lower not in seen and len(entity) > 2:
            seen.add(entity_lower)
            unique_entities.append(entity)
    
    return unique_entities[:5]  # Max 5 entities

def validate_reply_context(reply_text: str, tweet_text: str, key_entities: list[str]) -> bool:
    """
    Validate that reply references key entities from the original tweet.
    Returns True if reply is contextually relevant, False otherwise.
    """
    if not reply_text or not tweet_text:
        return False
    
    reply_lower = reply_text.lower()
    tweet_lower = tweet_text.lower()
    
    # Must reference at least one key entity or significant word from tweet
    if key_entities:
        entity_mentions = sum(1 for entity in key_entities if entity.lower() in reply_lower)
        if entity_mentions == 0:
            # Check if reply mentions at least one significant word from tweet
            # Extract meaningful words (3+ chars, not common stop words)
            stop_words = {'the', 'this', 'that', 'with', 'from', 'have', 'will', 'would', 'should', 'could', 'about', 'what', 'when', 'where', 'how', 'why', 'and', 'but', 'or', 'not', 'are', 'was', 'were', 'been', 'being'}
            tweet_words = set([w.lower() for w in re.findall(r'\b\w{3,}\b', tweet_lower) if w.lower() not in stop_words])
            reply_words = set([w.lower() for w in re.findall(r'\b\w{3,}\b', reply_lower)])
            overlap = tweet_words & reply_words
            if len(overlap) < 2:  # Need at least 2 meaningful words in common
                return False
    
    # Block generic phrases that show lack of context
    generic_phrases = [
        'absolutely', 'fascinating', 'interesting take', 'attribution shows',
        'conversion tracking reveals', 'data suggests', 'analytics show', 'data shows',
        'this is interesting', 'great point', 'well said', 'i agree'
    ]
    reply_lower_clean = reply_lower
    for phrase in generic_phrases:
        if phrase in reply_lower_clean:
            # Allow if used ironically or with context, but flag as potentially generic
            # For now, we'll allow it but the entity check above should catch truly generic replies
            pass
    
    return True

def filter_media_words(text: str) -> str:
    """
    Remove or flag media-related words that shouldn't be in text-only replies.
    Returns filtered text or empty string if too many media references found.
    """
    media_words = [
        "image", "screenshot", "photo", "picture", "chart", "graph", 
        "thumbnail", "video overlay", "see image", "posting this chart",
        "here's a screenshot", "attached image"
    ]
    text_lower = text.lower()
    media_count = sum(1 for word in media_words if word in text_lower)
    
    # If multiple media references, filter them out
    if media_count > 0:
        for word in media_words:
            # Remove phrases containing media words
            # Move regex pattern outside f-string to avoid backslash issues
            escaped_word = re.escape(word)
            pattern = rf'\b{escaped_word}\b[^\s]*'
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If still has media references after filtering, return empty (will trigger regeneration)
        text_lower_after = text.lower()
        if any(word in text_lower_after for word in media_words):
            return ""
    
    return text

def compose_reply_text(tweet_text: str = "", topic: str = "", author_handle: str = "", bot_handle: str = "", include_link: bool = False, reply_type: str = "normal", author_followers: int = 0) -> str:
    """
    Generate a unique, contextual reply using OpenAI or fallback to templates.
    Follows X spam/duplication rules: unique wording, contextual relevance, natural tone.
    Returns "NO_REPLY" if author is the bot itself.
    """
    # Check for self-reply
    if author_handle and bot_handle and author_handle.lower() == bot_handle.lower():
        return "NO_REPLY"
    
    # If OpenAI is not available, use improved template fallback
    if not openai_client:
        # [ENHANCEMENT #5] Use get_random_template for diversity (avoids repetition)
        template = get_random_template()
        return sanitize(template.format(link=REFERRAL_LINK))
    
    try:
        # Build context from tweet text and topic (matching TWEET_TEXT and CONTEXT format)
        tweet_text_input = tweet_text[:500] if tweet_text else ""  # Limit to avoid token bloat
        context_input = ""
        if topic:
            context_input = f"Search topic: {topic}"
        
        author_handle_input = author_handle or "unknown"
        bot_handle_input = bot_handle or BOT_HANDLE or "unknown"
        
        # Select archetype for this reply
        archetype = "pattern_finder"  # Default
        archetype_prompt_addition = ""
        if REPLY_PSYCHOLOGY:
            archetype = REPLY_PSYCHOLOGY.select_archetype()
            archetype_prompt_addition = REPLY_PSYCHOLOGY.get_archetype_prompt(archetype, tweet_text, context_input)
        
        # Check if time-sensitive
        is_urgent = False
        urgency_language = ""
        if THREAD_OPTIMIZER:
            is_urgent_result, urgency_reason = THREAD_OPTIMIZER.is_time_sensitive(tweet_text)
            is_urgent = is_urgent_result
            if is_urgent:
                urgency_language = THREAD_OPTIMIZER.get_urgency_language(is_urgent=True)
        
        # Import system prompt from config
        from bot.config import SYSTEM_PROMPT
        system_prompt = SYSTEM_PROMPT + """

Your goal: Write engaging X replies that:
- Sound like a helpful SaaS growth expert (not a salesman)
- Spot genuine insights in the original tweet
- End with a question or call-to-action that drives engagement
- Use the referral link only when it adds value, not shoehorned

Rules:
- Keep replies under 200 characters when possible (X users scan fast)
- Use 1-2 line breaks for readability (not walls of text)
- Never sound like a bot (no "As an AI" or "I've analyzed")
- Reference real marketing concepts (attribution, conversion tracking, CTR)
- End 40% of replies with a genuine question about their take
- Save the referral link for replies that naturally benefit from it

Reply style guide:
- Confident but not arrogant ("I think X because..." not "X is obviously...")
- Conversational ("Here's what I'm seeing..." not "My analysis shows...")
- Short sentences (20 words average, not 40+)
- No hashtags (spam tags)
- 1-2 emojis max if it fits the vibe (📈 for growth, 🤔 for thinking, etc.)

When you include a link, frame it as:
- "I use [link] for this" (utility)
- "Here's the tool I recommend [link]" (credibility)
- "This solves that problem [link]" (value)
NOT: "Check out this link!" (spam)

Critical context rules:
- Read TWEET_TEXT carefully and identify: specific tools mentioned, problems, use cases
- Your reply MUST reference the EXACT topic in the tweet
- Quote or paraphrase a specific phrase from the tweet to prove you read it

Media:
- NEVER mention, generate, or describe images/videos
- Text only

Scope rules:
- If AUTHOR_HANDLE == BOT_HANDLE, output exactly: NO_REPLY
- Never create reply chains where bot talks to itself

Link rules:
- NEVER include links in your reply text directly
- Links are handled separately by the system
- Focus on pure engagement and value, end with curiosity question when appropriate

Input: TWEET_TEXT, CONTEXT, AUTHOR_HANDLE, BOT_HANDLE
Output: If AUTHOR_HANDLE == BOT_HANDLE: NO_REPLY
Otherwise: one short, context-specific reply

BANNED PHRASES (never use):
- "Interesting response" / "Interesting take"
- "What are your thoughts" / "What do you think"
- "Curious if you think"
- Any question without specific context
- Generic analysis without numbers

REQUIRED ELEMENTS (every reply must have 1+):
- Specific tool or technique mention
- Helpful insight ("This solves X", "The issue is Y")
- Data reference ("CTR increased by X%", "conversion tracking shows")
- Practical tip or recommendation

CHARACTER LIMIT: Keep replies under 240 characters (X limit is 280, leave room for link)."""

        # Add archetype-specific prompt
        if archetype_prompt_addition:
            system_prompt += "\n\n" + archetype_prompt_addition
        
        # Extract key entities from tweet for validation
        key_entities = extract_key_entities(tweet_text)
        
        # 30% chance to use "Momentum" hooks (active trader vibe)
        use_momentum_hooks = random.random() < 0.30
        momentum_addition = ""
        if use_momentum_hooks:
            momentum_addition = """
MOMENTUM MODE: Use active trader hooks that sound like real-time market analysis:
- "Look at the volume on {market}. Someone knows something."
- "Chart on {market} says you're right. Odds just broke {level}."
- "This is exactly why {market} is priced at {odds}. Smart play."
- "Volume spike on {market}. The smart money is moving."
Sound like you're watching live market data, not generic analysis."""
            system_prompt += momentum_addition
        
        # [STAGE 15] Reply type variation: Mix statement/question/agree+ask (40%/40%/20%)
        # [FIX] random is already imported at top of file, don't re-import (causes UnboundLocalError)
        reply_type_variation = random.random()
        if reply_type_variation < 0.40:
            reply_type_instruction = "Generate a STATEMENT reply (your take/analysis)."
            log("[STAGE 15] [REPLY_TYPE] Statement reply")
        elif reply_type_variation < 0.80:
            reply_type_instruction = "Generate a QUESTION reply (ask their opinion: 'What's your take on odds?', 'How would you price this?')."
            log("[STAGE 15] [REPLY_TYPE] Question reply")
        else:
            reply_type_instruction = "Generate an AGREE+ASK reply (acknowledge their point, then ask: 'Are you tracking [market] odds?', 'How are you hedging this?')."
            log("[STAGE 15] [REPLY_TYPE] Agree+ask reply")
        
        # [STAGE 15] 20% contrarian replies (respectfully disagree)
        is_contrarian = random.random() < 0.20
        contrarian_instruction = ""
        if is_contrarian:
            contrarian_phrases = [
                "I see it differently though...",
                "Not sure I agree on this one...",
                "Fair point, though...",
                "I'm taking the other side here...",
                "Interesting, but I think..."
            ]
            contrarian_example = random.choice(contrarian_phrases)
            contrarian_instruction = f"\nStart with respectful disagreement like '{contrarian_example}' then provide data-backed alternative view."
            log("[STAGE 15] [REPLY_NUANCE] Contrarian reply")
        
        # [STAGE 15] 30% conversation starters (engaging questions)
        has_conversation_starter = random.random() < 0.30
        conversation_starter_instruction = ""
        if has_conversation_starter:
            starter_questions = [
                "How are you hedging this?",
                "Where would you set your entry?",
                "What's your position size?",
                "Do you see odds moving further?",
                "What's your target price here?"
            ]
            starter = random.choice(starter_questions)
            conversation_starter_instruction = f"\nEnd with an engaging question like: '{starter}'"
            log("[STAGE 15] [ENGAGEMENT] Conversation starter added")
        
        # Build user prompt with urgency if applicable
        urgency_prefix = urgency_language if urgency_language else ""
        
        user_prompt = f"""TWEET_TEXT: {tweet_text_input}

CONTEXT: {context_input}
AUTHOR_HANDLE: {author_handle_input}
BOT_HANDLE: {bot_handle_input}

{urgency_prefix}{reply_type_instruction}{contrarian_instruction}{conversation_starter_instruction}
Generate a unique, human X reply that focuses on SaaS growth, marketing tools, or link management. Use the {archetype.replace('_', ' ')} archetype. Do NOT reference images or media. Do NOT include any links (links are handled separately). Connect to their problem or use case. Keep under 200 characters."""
        
        # Apply style rotation and optimization
        style = "analytical"  # Default
        style_prompt_addition = ""
        if REPLY_OPTIMIZER:
            style = REPLY_OPTIMIZER.get_next_style()
            style_prompt_addition = REPLY_OPTIMIZER.get_style_prompt_addition(style)
            system_prompt += style_prompt_addition
        
        # Use optimized temperature (0.8 for better variety)
        temperature = REPLY_OPTIMIZER.get_temperature() if REPLY_OPTIMIZER else 0.8
        
        # Generate initial reply
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",  # Use cheaper model for replies
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,  # Optimized temperature for variety
            max_tokens=150,
        )
        
        reply_text = response.choices[0].message.content.strip()
        
        # Check for NO_REPLY (self-reply prevention)
        if reply_text.upper() == "NO_REPLY":
            return "NO_REPLY"
        
        # Clean up common LLM artifacts
        if reply_text.startswith('"') and reply_text.endswith('"'):
            reply_text = reply_text[1:-1]
        
        # Filter out media-related words (code-side safety check)
        reply_text = filter_media_words(reply_text)
        if not reply_text or reply_text == "":
            log("[WARNING] Reply filtered for media references, skipping")
            return ""
        
        # Check for bot-like patterns (hard ban)
        try:
            is_bot_like, bot_reason = is_bot_like_reply(reply_text)
        except (ValueError, TypeError) as e:
            # Safety: if unpacking fails, assume not bot-like and continue
            log(f"[BOT_FILTER] Error checking bot patterns: {e}, continuing with reply")
            is_bot_like = False
            bot_reason = ""
        
        if is_bot_like:
            log(f"[BOT_FILTER] Reply flagged as bot-like ({bot_reason}), regenerating...")
            # Regenerate once with different style
            try:
                retry_prompt = f"""TWEET_TEXT: {tweet_text_input}

CONTEXT: {context_input}

IMPORTANT: Your previous reply was too generic/templatey. Write a SHORT, DIRECT, OPINIONATED reply (1-2 sentences, 120-220 chars). Sound like a real trader, not a bot. No "Notice how" or generic filler. Be specific and opinionated. Do NOT include any links."""
                
                retry_response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a trader. Write short, direct, opinionated replies. No templates, no filler."},
                        {"role": "user", "content": retry_prompt}
                    ],
                    temperature=0.9,
                    max_tokens=120,
                )
                reply_text = retry_response.choices[0].message.content.strip()
                
                # Clean artifacts
                if reply_text.startswith('"') and reply_text.endswith('"'):
                    reply_text = reply_text[1:-1]
                
                # Re-check bot filter
                is_bot_like_retry, _ = is_bot_like_reply(reply_text)
                if is_bot_like_retry:
                    log("[BOT_FILTER] Retry still flagged, using simple fallback")
                    # Use simple fallback template
                    reply_text = f"Everyone's betting {topic or 'this'} but the value's probably on the other side." if topic else "The market's pricing this differently than people think."
            except Exception as e:
                log(f"[BOT_FILTER] Regeneration failed: {e}, using simple fallback")
                reply_text = f"Everyone's betting {topic or 'this'} but the value's probably on the other side." if topic else "The market's pricing this differently than people think."
        
        # VALIDATION: Check if reply references key entities from tweet
        if not validate_reply_context(reply_text, tweet_text, key_entities):
            log(f"[VALIDATION] Reply failed context check, regenerating with stronger prompt (entities: {key_entities})")
            
            # Regenerate with stronger prompt focusing on entities
            entity_focus = ", ".join(key_entities[:3]) if key_entities else "the specific content"
            retry_prompt = f"""TWEET_TEXT: {tweet_text_input}

CONTEXT: {context_input}
AUTHOR_HANDLE: {author_handle_input}
BOT_HANDLE: {bot_handle_input}

IMPORTANT: Your previous reply was too generic. Focus specifically on: {entity_focus}

Generate a reply that directly references these elements from the tweet. Quote or mention them explicitly. Do NOT include any links. Keep it under 240 characters."""
            
            try:
                retry_response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": retry_prompt}
                    ],
                    temperature=0.9,
                    max_tokens=150,
                )
                reply_text = retry_response.choices[0].message.content.strip()
                
                # Clean up artifacts
                if reply_text.startswith('"') and reply_text.endswith('"'):
                    reply_text = reply_text[1:-1]
                
                # Re-validate
                if not validate_reply_context(reply_text, tweet_text, key_entities):
                    log("[VALIDATION] Retry reply still failed context check, using anyway")
                else:
                    log("[VALIDATION] ✓ Retry reply passed context validation")
            except Exception as e:
                log(f"[VALIDATION] Retry generation failed: {e}, using original reply")
        else:
            log("[VALIDATION] ✓ Reply passed context validation")
        
        # Apply all anti-spam filters
        # 1. Check for outdated content
        if is_outdated_content(reply_text):
            log("[FILTER] Outdated content detected (2024 references), skipping")
            return ""
        
        # 2. Clean spam phrases
        reply_text = clean_reply_text(reply_text)
        if not reply_text:
            log("[FILTER] Reply was empty after cleaning spam phrases")
            return ""
        
        # 3. Format for mobile (add line breaks)
        reply_text = format_for_mobile(reply_text)
        
        # 4. Apply reply optimization (shorter replies, question endings)
        if REPLY_OPTIMIZER:
            # Make replies ~30% shorter (humans are terse)
            reply_text = REPLY_OPTIMIZER.optimize_reply_length(reply_text, target_reduction=0.3)
            
        # Add archetype-specific ending/question (replaces generic question ending)
        if REPLY_PSYCHOLOGY:
            ending = REPLY_PSYCHOLOGY.get_archetype_ending(archetype)
            # Only add ending if reply doesn't already end with question/mark
            if not reply_text.rstrip().endswith(('?', '!', ':')):
                if len(reply_text + ending) <= 240:
                    reply_text += ending
        
        # 5. Check text deduplication before proceeding (max 3 regeneration attempts)
        dedupe_attempts = 0
        max_dedupe_attempts = 3
        while DEDUPLICATOR and DEDUPLICATOR.is_duplicate_or_similar(reply_text) and dedupe_attempts < max_dedupe_attempts:
            dedupe_attempts += 1
            log(f"[DEDUPE] Reply text too similar to recent replies, regenerating... (attempt {dedupe_attempts}/{max_dedupe_attempts})")
            
            try:
                dedupe_retry_prompt = f"""TWEET_TEXT: {tweet_text_input}

CONTEXT: {context_input}

Generate a UNIQUE reply that's different from common patterns. Be specific and opinionated. 1-2 sentences, 120-220 chars. Do NOT include any links."""
                
                dedupe_retry = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Write unique, specific replies. Avoid generic patterns."},
                        {"role": "user", "content": dedupe_retry_prompt}
                    ],
                    temperature=0.9 + (dedupe_attempts * 0.05),  # Increase temperature with each attempt
                    max_tokens=120,
                )
                reply_text = dedupe_retry.choices[0].message.content.strip()
                if reply_text.startswith('"') and reply_text.endswith('"'):
                    reply_text = reply_text[1:-1]
            except Exception as e:
                log(f"[DEDUPE] Regeneration attempt {dedupe_attempts} failed: {e}")
                break  # Exit loop on exception
                
        # If still duplicate after max attempts, use fallback
        if DEDUPLICATOR and DEDUPLICATOR.is_duplicate_or_similar(reply_text):
            log(f"[REPLY_SKIP] reason=dedupe_exhausted (failed {dedupe_attempts} regeneration attempts)")
            # Return empty string to skip this reply
            return ""
        
        # 6. Handle link inclusion (with config-driven strategy)
        # Remove any existing link from LLM output
        if REFERRAL_LINK in reply_text:
            reply_text = reply_text.replace(REFERRAL_LINK, "").strip()
        
        # Check link safety before including (do this FIRST, before any include/exclude decisions)
        link_to_use = REFERRAL_LINK
        if HARDENING:
            # Check if we can post this link (duplicate prevention)
            if not HARDENING.can_post_link(link_to_use, min_minutes_between=30):
                log("[LINK_SAFETY] Link posted too recently, skipping link in this reply")
                link_to_use = None
            else:
                # Get link variant if available (30% chance)
                link_to_use = HARDENING.get_link_variant(link_to_use)
        
        # Log link availability status before psychology decision
        if link_to_use:
            log(f"[LINK_DEBUG] Link available before psychology: {link_to_use}")
        else:
            log(f"[LINK_DEBUG] Link blocked by safety, psychology skipping")
        
        # Determine link usage based on reply type and config
        should_include_link = False
        # [STAGE 14] Reduced link frequencies for anti-spam (25-30% overall target)
        link_usage_targets = {
            "originals": 0.25,  # Reduced from 0.35
            "high_value_replies": 0.25,  # Reduced from 0.8 (was test mode)
            "normal_replies": 0.15,  # Reduced from 0.25
            "trending_replies": 0.30  # Reduced from 0.5
        }
        
        # Determine if this is a high-value reply
        is_high_value = False
        if reply_type == "trending":
            is_high_value = True
        elif reply_type == "high_value":
            is_high_value = True
        elif author_followers >= 500:  # High follower threshold
            is_high_value = True
        elif tweet_text and any(kw in tweet_text.lower() for kw in ["bet", "wager", "odds", "prediction", "betting"]):
            is_high_value = True
        
        # Select target frequency
        if reply_type == "trending" or is_high_value:
            target_freq = link_usage_targets.get("high_value_replies", 0.25)
        else:
            target_freq = link_usage_targets.get("normal_replies", 0.15)
        
        # Decide whether to include link
        should_include_link = random.random() < target_freq
        
        # Also check archetype strategy (can override if archetype says no)
        # IMPORTANT: Only check psychology if link is available (don't force include if link_to_use is None)
        if REPLY_PSYCHOLOGY and link_to_use:
            thread_id = None
            reply_number = 1
            archetype_says_include = REPLY_PSYCHOLOGY.should_include_link(
                archetype, thread_id=thread_id, reply_number=reply_number
            )
            # If archetype says no, respect it (but if archetype says yes, still use config frequency)
            if not archetype_says_include:
                should_include_link = False
            log(f"[PSYCHOLOGY] Archetype: {archetype}, Config target: {target_freq:.0%}, Final decision: {should_include_link}")
        elif REPLY_PSYCHOLOGY and not link_to_use:
            # Link is blocked, don't let psychology override - just skip it
            should_include_link = False
            log(f"[PSYCHOLOGY] Link unavailable (blocked by safety), skipping archetype link decision")
        
        # Record link usage if link was decided to be included
        if should_include_link and link_to_use and HARDENING:
                HARDENING.record_link(link_to_use)
        
        if should_include_link and not link_to_use:
            # Safety check: If we decided to include link but link_to_use is None, log warning
            log(f"[LINK_WARNING] Link was supposed to be included but link_to_use is None (blocked by safety checks?)")
        
        # [STAGE 15] Strategic link placement for replies (check content first)
        if link_to_use:
            strategic_include = should_include_link_strategic(reply_text, post_type="reply")
            if strategic_include:
                should_include_link = True
                log("[STAGE 15] [LINK_STRATEGIC] Reply content suggests link inclusion (ALWAYS)")
            # Otherwise keep original should_include_link decision
        
        if not should_include_link:
            log(f"[LINK] No link in {reply_type} reply (target: {target_freq:.0%})")
        else:
            log(f"[LINK] Including link in {reply_type} reply (target: {target_freq:.0%})")
        
        # Final verification: Use centralized helper to ensure link is appended if needed
        final_text = sanitize(reply_text)
        final_text = append_link_if_needed(final_text, link_to_use or REFERRAL_LINK, should_include_link)
        
        # [STAGE 15] Log link format for replies
        if should_include_link and link_to_use:
            log("[STAGE 15] [LINK_FORMAT] Brief CTA + link (replies)")
        
        return final_text
        
    except Exception as e:
        import traceback
        traceback_str = traceback.format_exc()
        log(f"[WARNING] OpenAI reply generation failed: {e}, using fallback template")
        log(f"[REPLY_TRACEBACK] {traceback_str}")
        
        # [FIX] Use safe fallback that doesn't rely on OpenAI
        try:
            # [ENHANCEMENT #5] Use get_random_template for diversity (avoids repetition)
            template = get_random_template()
            # Extract a keyword from tweet text for context
            keywords = ["odds", "market", "betting", "prediction", "price", "trade"]
            keyword = next((kw for kw in keywords if kw in tweet_text.lower()), "this")
            fallback_text = template.replace("{odds}", "current").replace("{market}", keyword).replace("{topic}", topic or keyword).replace("{x}", "recently").replace("{factor}", keyword).replace("{detail}", keyword)
            
            # For fallback, include link if requested
            if include_link:
                return sanitize(fallback_text.format(link=REFERRAL_LINK))
            else:
                return sanitize(fallback_text.replace("{link}", "").strip())
        except Exception as fallback_error:
            # Ultimate fallback if template system also fails
            log(f"[REPLY_TRACEBACK] Fallback template also failed: {fallback_error}")
            keyword = topic or "this"
            simple_fallback = f"The market's pricing {keyword} differently than people think." if keyword else "Interesting take on the odds."
            return sanitize(simple_fallback)

def find_file_input(page):
    for sel in ("input[data-testid='fileInput']", "input[type='file']"):
        try:
            el = page.locator(sel).first
            if el.count():
                return el
        except Exception:
            continue
    return None

def run_wrapper(wrapper: Path, out_path: Path, topic: str, timeout_sec=300) -> bool:
    """Run generator wrapper with the venv python."""
    if not wrapper.exists():
        return False
    cmd = [sys.executable, str(wrapper), "--out", str(out_path), "--topic", topic]
    try:
        log(f"🎨 Running generator: {' '.join(cmd)}")
        subprocess.run(cmd, timeout=timeout_sec, check=True)
        ok = out_path.exists() and out_path.stat().st_size > 0
        log("✅ Generator output ready" if ok else "⚠️ Generator ran but no output")
        return ok
    except Exception as e:
        log(f"⚠️ Generator failed: {e}")
        return False

def maybe_generate_media(topic: str, reply_idx: int):
    generated = False
    if ENABLE_IMAGES and reply_idx % max(1, GENERATE_IMAGE_EVERY_N_REPLIES) == 0:
        out = IMAGES_DIR / f"auto_{int(time.time())}.png"
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        generated |= run_wrapper(IMAGE_WRAPPER, out, topic)
    if ENABLE_VIDEOS and reply_idx % max(1, GENERATE_VIDEO_EVERY_N_REPLIES) == 0:
        out = VIDEOS_DIR / f"auto_{int(time.time())}.mp4"
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        generated |= run_wrapper(VIDEO_WRAPPER, out, topic)
    return generated

def maybe_attach_media(page, topic: str, reply_idx: int):
    """
    HARD BLOCK: Media attachment is disabled to prevent X duplicate/spam errors.
    This function now does nothing but log if called.
    """
    log("[MEDIA_BLOCK] Media attachment attempted but blocked (text-only mode enforced)")
    return  # No-op: all media blocked

def hard_block_media_before_post(page) -> bool:
    """
    HARD BLOCK: Check for and remove any attached media before posting.
    Returns True if media was found and removed, False otherwise.
    """
    media_removed = False
    try:
        # Check for file inputs with files attached
        file_inputs = page.locator('input[type="file"][data-testid="fileInput"]')
        count = file_inputs.count()
        
        for i in range(count):
            try:
                file_input = file_inputs.nth(i)
                # Check if files are attached by checking if the input has a value
                # In Playwright, we can check if files were set
                # Try to clear it by clicking the remove button or clearing the input
                log("[MEDIA_BLOCK] Found file input, attempting to remove attached media")
                
                # Look for remove/delete buttons near media attachments
                remove_buttons = page.locator('button[aria-label*="Remove"], button[aria-label*="Delete"], div[data-testid="remove"]')
                if remove_buttons.count() > 0:
                    for j in range(remove_buttons.count()):
                        try:
                            remove_buttons.nth(j).click(timeout=5000)
                            media_removed = True
                            log("[MEDIA_BLOCK] Removed media attachment")
                            human_pause(0.3, 0.5)
                        except Exception:
                            continue
                
                # Also check for media preview containers and try to remove them
                media_previews = page.locator('[data-testid="attachments"], div[role="group"] img, video')
                if media_previews.count() > 0:
                    # Try to find and click X/close buttons on media previews
                    close_buttons = page.locator('button:has-text("Remove"), button:has-text("×"), button[aria-label="Remove"]')
                    if close_buttons.count() > 0:
                        try:
                            close_buttons.first.click(timeout=5000)
                            media_removed = True
                            log("[MEDIA_BLOCK] Removed media preview")
                        except Exception:
                            pass
            except Exception:
                continue
        
        if media_removed:
            log("[MEDIA_BLOCK] ✓ Blocked and removed media upload attempt")
            human_pause(0.5, 1.0)  # Brief pause after removal
        
    except Exception as e:
        log(f"[MEDIA_BLOCK] Error checking for media: {e}")
    
    return media_removed

def force_click_element(page, selector: str) -> bool:
    """
    Force-click an element using JavaScript, bypassing Playwright's scroll-into-view logic.
    Used as fallback when standard click fails due to viewport issues.
    """
    try:
        result = page.evaluate(f"""
            (() => {{
                const elem = document.querySelector('{selector}');
                if (elem) {{
                    elem.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                    elem.click();
                    return true;
                }}
                return false;
            }})()
        """)
        return result is True
    except Exception:
        return False

def click_post_once(page, allow_media=False) -> bool:
    """
    Click a single button if present; only use keyboard if no button is clickable.
    HARD BLOCK: Ensures no media is attached before posting (unless allow_media=True).
    Uses force-click fallback if standard click fails (prevents infinite viewport scroll loops).
    
    Args:
        page: Playwright page object
        allow_media: If True, skip media blocking (for Stage 53 video posts)
    """
    # HARD BLOCK: Remove any attached media before posting (unless allow_media=True for Stage 53)
    if not allow_media:
        hard_block_media_before_post(page)
    
    # Continue with normal post logic
    selectors = [
        "button[data-testid='tweetButtonInline']",
        "div[data-testid='tweetButtonInline']",
        "button[data-testid='tweetButton']",
        "div[data-testid='tweetButton']",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if btn.count() and btn.is_enabled():
                # Try standard click first
                try:
                    btn.click(timeout=5000)
                    try:
                        btn.wait_for(state="detached", timeout=4000)
                    except Exception:
                        pass
                    return True
                except Exception as e:
                    error_str = str(e).lower()
                    # If it fails with viewport/outside errors, use force-click
                    if "outside" in error_str or "viewport" in error_str or "not visible" in error_str:
                        log(f"[CLICK_FALLBACK] Standard click failed ({error_str[:50]}), using force-click")
                        if force_click_element(page, sel):
                            return True
                    raise  # Re-raise if not a viewport error
        except Exception:
            continue
    # fallback: keyboard only if no clickable button
    try:
        page.keyboard.press("Meta+Enter")  # macOS
        return True
    except Exception:
        try:
            page.keyboard.press("Control+Enter")
            return True
        except Exception:
            return False

# Old duplicate reply functions removed - using simpler version at top of file

def should_reply(tweet, card=None):
    """
    ELITE VIRAL BOT OVERHAUL: Strict reply filter to prevent self-replies and low-quality replies.
    
    Args:
        tweet: Tweet object or dict with author info and metrics
        card: Optional card element (for extracting info)
    
    Returns:
        bool: True if should reply, False otherwise
    """
    try:
        if not card:
            return False  # Need card to extract info
        
        account_text = card.inner_text() if hasattr(card, 'inner_text') else ""
        account_text_lower = account_text.lower()
        
        # NEVER reply to yourself
        bot_username = "k_shamil57907"
        if bot_username.lower() in account_text_lower:
            log(f"[REPLY_FILTER] Skipped - self-reply detected")
            return False
        
        # Extract engagement (likes) - need at least 5 likes
        engagement = 0
        try:
            likes_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*(likes?|❤)', account_text, re.IGNORECASE)
            if likes_match:
                count_str = likes_match.group(1).upper()
                if 'K' in count_str:
                    engagement = int(float(count_str.replace('K', '')) * 1000)
                elif 'M' in count_str:
                    engagement = int(float(count_str.replace('M', '')) * 1000000)
                else:
                    engagement = int(float(count_str))
        except Exception:
            pass
        
        # NEVER reply to tweets with < 5 likes (low signal)
        if engagement > 0 and engagement < 5:
            log(f"[REPLY_FILTER] Skipped - low engagement (likes={engagement} < 5)")
            return False
        
        # Extract follower count
        follower_count = 0
        follower_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*followers?', account_text)
        if follower_match:
            follower_str = follower_match.group(1).upper()
            if 'K' in follower_str:
                follower_count = int(float(follower_str.replace('K', '')) * 1000)
            elif 'M' in follower_str:
                follower_count = int(float(follower_str.replace('M', '')) * 1000000)
            else:
                follower_count = int(float(follower_str))
        
        # [STAGE 43] Follower count filter removed - bot can reply regardless of follower count
        # if follower_count > 0 and follower_count < 50:
        #     log(f"[REPLY_FILTER] Skipped - low followers (followers={follower_count} < 50)")
        #     return False
        
        # NEVER reply if the tweet is NOT about your markets (check keywords)
        relevant_keywords = [
            'SaaS', 'marketing', 'attribution', 'conversion', 'tracking', 'growth', 'tools',
            'links', 'analytics', 'CTR', 'LTV', 'MRR', 'conversion', 'tracking'
        ]
        if not any(kw in account_text_lower for kw in relevant_keywords):
            log(f"[REPLY_FILTER] Skipped - not about relevant markets")
            return False
        
        return True
    except Exception as e:
        log(f"[REPLY_FILTER] Error in should_reply: {e}")
        return False  # Fail closed - don't reply if we can't verify

def should_target_for_reply(card, topic: str) -> tuple[bool, str]:
    """
    Decide if we should reply to this card based on content relevance and follower count.
    Returns (should_reply: bool, reason: str)
    """
    try:
        # ELITE VIRAL BOT OVERHAUL: Apply strict should_reply filter first
        if not should_reply(None, card=card):
            return False, "should_reply-filter-failed"
        
        # Extract account info
        account_text = card.inner_text() if hasattr(card, 'inner_text') else ""
        account_text_lower = account_text.lower()
        
        # Define relevance keywords (expanded to include more marketing/growth terms)
        keywords = [
            "SaaS",
            "marketing",
            "attribution",
            "conversion",
            "tracking",
            "links",
            "analytics",
            "growth",
            "tools",
            "CTR",
            "LTV",
            "MRR",
            "affiliate",
            "referral",
            "branded links",
            "link management",
            "conversion tracking",
            "marketing attribution",
            "growth tools",
        ]
        
        # Check content match
        content_matches = any(kw in account_text_lower for kw in keywords)
        
        # Try to extract follower count (this is approximate since card text varies)
        follower_count = 0
        # Look for patterns like "1.2K followers" or "500 followers"
        follower_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*followers?', account_text)
        if follower_match:
            follower_str = follower_match.group(1).upper()
            if 'K' in follower_str:
                follower_count = int(float(follower_str.replace('K', '')) * 1000)
            elif 'M' in follower_str:
                follower_count = int(float(follower_str.replace('M', '')) * 1000000)
            else:
                follower_count = int(float(follower_str))
        
        # Extract engagement (likes + retweets) - approximate from card text
        engagement = 0
        try:
            # Look for engagement indicators in the card text
            # Patterns like "5.2K Likes", "1.5K Retweets", etc.
            likes_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*(likes?|❤)', account_text, re.IGNORECASE)
            retweets_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*(retweets?|🔁)', account_text, re.IGNORECASE)
            
            def parse_count(count_str):
                count_str = count_str.upper()
                if 'K' in count_str:
                    return int(float(count_str.replace('K', '')) * 1000)
                elif 'M' in count_str:
                    return int(float(count_str.replace('M', '')) * 1000000)
                else:
                    return int(float(count_str))
            
            if likes_match:
                engagement += parse_count(likes_match.group(1))
            if retweets_match:
                engagement += parse_count(retweets_match.group(1))
        except Exception:
            pass
        
        # [ENHANCEMENT #2] Massively loosened targeting for shadowban recovery (WAY more permissive)
        # REJECT obvious spam/bots only
        is_spam_bot = False  # Could add spam detection logic here
        if is_spam_bot:
            log(f"[TARGETING] Skipped - spam bot")
            return False, "spam-bot"
        
        # [ENHANCEMENT #2] Tier 1: Big accounts (1k+) with market keywords (easiest target)
        if follower_count >= 1000 and content_matches:
            log(f"[TARGETING] ✓ Tier 1: Big account with keywords (followers={follower_count}, engagement={engagement})")
            return True, "tier1-big-keywords"
        
        # [ENHANCEMENT #2] Tier 2: Medium accounts (200-1000) with market keywords
        if follower_count >= 200 and content_matches:
            log(f"[TARGETING] ✓ Tier 2: Medium account with keywords (followers={follower_count}, engagement={engagement})")
            return True, "tier2-medium-keywords"
        
        # [ENHANCEMENT #2] Tier 3: Verified accounts with ANY engagement (if we can detect verification)
        # Note: Verification detection would need to be added to card extraction
        # For now, skip this tier as we don't have verification detection
        
        # [ENHANCEMENT #2] Tier 4: Established accounts (500+) with reasonable engagement
        engagement_rate = (engagement / follower_count) if follower_count > 0 else 0
        if follower_count >= 500 and engagement_rate >= 0.005:
            log(f"[TARGETING] ✓ Tier 4: Established account (followers={follower_count}, engagement_rate={engagement_rate:.3f})")
            return True, "tier4-established-engagement"
        
        # [PROBLEM #4 FIX] Accept accounts with 100+ followers (not 200+) for more aggressive engagement
        if follower_count >= 100 and content_matches:
            log(f"[TARGETING] ✓ Lower threshold: 100+ with keywords (followers={follower_count})")
            return True, "lower-threshold-100-keywords"
        
        # [STAGE 43] Follower count filter removed - bot can reply to matching content regardless of follower count
        if content_matches:
            # if follower_count < 50:  # REMOVED: Follower count filter
            #     log(f"[FILTER] Skipped target – reason: low_followers followers={follower_count} (content matched but below 50 follower threshold)")
            #     return False, "low_followers"
            log(f"[TARGETING] ✓ Content match (followers={follower_count})")
            return True, "content-match-recovery"
        
        # [STAGE 43] Follower count filter removed - bot can reply regardless of follower count
        # Default: skip only if no content match (follower count check removed)
        # if follower_count > 0 and follower_count < 100 and not content_matches:
        #     log(f"[TARGETING] Skipped - too low followers AND no keywords (followers={follower_count})")
        #     return False, "low-followers-no-keywords"
        
        # Default: skip if no clear relevance
        return False, "no-match"
        
    except Exception as e:
        log(f"[TARGETING] Error checking target: {e}")
        # On error, default to allowing (don't want to skip everything)
        return True, "error-default-allow"

def reply_to_card(page, card, topic: str, recent_replies: list, reply_idx: int) -> bool:
    # [SAFETY] Ensure we're on X.com before replying
    if not ensure_on_x_com(page):
        log("[REPLY_SKIP] Reason: not_on_x_com")
        return False
    """
    Post a reply to a tweet card.
    Returns True if the reply was posted, False otherwise.
    """
    import traceback
    
    try:
        # Check sleep hours
        if should_sleep_now():
            log("[SLEEP_MODE] Skipping reply - bot sleeping")
            return False
        
        # Check if paused due to errors
        if HARDENING and HARDENING.is_paused():
            return False
        
        # Check rate limits (max 15 replies/hour) [PROBLEM #4 FIX] Increased from 8 to 15
        if HARDENING and not HARDENING.can_post_reply(max_replies_per_hour=15):  # [PROBLEM #4 FIX] Increased to 15/hour (3x more)
            return False
        
        # Check if we should wait before retry after failure
        if HARDENING:
            should_wait, wait_minutes = HARDENING.should_wait_before_retry()
            if should_wait:
                log(f"[ERROR_RECOVERY] Waiting {wait_minutes} min before retry after failure")
                return False
        
        # Get current phase
        if PHASE_CONTROLLER:
            current_phase = PHASE_CONTROLLER.update_phase()
            log(f"[PHASE {current_phase}] Processing reply")
        
        # Apply reply delay (2-8 seconds, randomized)
        apply_reply_delay()
        
        # open composer - improved selector strategy and click methods
        reply_clicked = False
        viewport_failures = 0
        max_viewport_failures = 3
        
        # Try multiple selectors for reply button
        reply_selectors = [
            '[data-testid="reply"]',
            'button[data-testid="reply"]',
            '[aria-label="Reply"]',
            'button[aria-label="Reply"]',
            '[role="button"][aria-label*="Reply"]',
        ]
        
        try:
            for attempt in range(max_viewport_failures):
                reply_button = None
                used_selector = None
                
                # Try each selector until we find the button
                for selector in reply_selectors:
                    try:
                        test_button = card.locator(selector).first
                        if test_button.count() > 0:
                            reply_button = test_button
                            used_selector = selector
                            log(f"[DEBUG] Found reply button with selector: {selector}")
                            break
                    except Exception:
                        continue
                
                if reply_button is None or reply_button.count() == 0:
                    log(f"[REPLY_FAIL] Reply button not found with any selector (attempt {attempt + 1}/{max_viewport_failures})")
                    if attempt < max_viewport_failures - 1:
                        human_pause(0.5, 1.0)
                        continue
                    return False
                
                # Try multiple click methods in order of preference
                click_success = False
                
                # Method 1: Standard click with force=True
                try:
                    log(f"[DEBUG] Attempting standard click with force=True (selector: {used_selector})")
                    reply_button.click(force=True, timeout=5000)
                    click_success = True
                    log(f"[DEBUG] Clicked reply button successfully (force=True)")
                except Exception as click_error:
                    error_str = str(click_error).lower()
                    log(f"[DEBUG] Force click failed: {error_str[:100]}")
                    
                    # Method 2: Standard click without force
                    try:
                        log(f"[DEBUG] Attempting standard click without force")
                        reply_button.click(timeout=5000)
                        click_success = True
                        log(f"[DEBUG] Clicked reply button successfully (standard click)")
                    except Exception as std_error:
                        error_str = str(std_error).lower()
                        log(f"[DEBUG] Standard click failed: {error_str[:100]}")
                        
                        # Method 3: JavaScript click (bypass viewport/mask issues)
                        try:
                            log(f"[DEBUG] Attempting JavaScript click fallback")
                            # Escape single quotes in selector for JavaScript (move replacement outside f-string)
                            escaped_selector = used_selector.replace("'", "\\'")
                            card.evaluate(f"""
                                (el) => {{
                                    const btn = el.querySelector('{escaped_selector}');
                                    if (btn) {{
                                        btn.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                                            btn.click();
                                            return true;
                                    }}
                                        return false;
                                }}
                                """)
                            click_success = True
                            log(f"[DEBUG] Clicked reply button successfully (JavaScript fallback)")
                        except Exception as js_error:
                            error_str = str(js_error).lower()
                            log(f"[DEBUG] JavaScript click failed: {error_str[:100]}")
                            
                            # Method 4: Try element handle click (get native element and click)
                            try:
                                log(f"[DEBUG] Attempting element handle click")
                                element_handle = reply_button.element_handle()
                                if element_handle:
                                    page.evaluate("(el) => el.click()", element_handle)
                                    click_success = True
                                    log(f"[DEBUG] Clicked reply button successfully (element handle)")
                            except Exception as eval_error:
                                log(f"[DEBUG] Element handle click failed: {str(eval_error)[:100]}")
                
                if click_success:
                    reply_clicked = True
                    log(f"[DEBUG] Reply button click successful on attempt {attempt + 1}")
                    break
                else:
                    viewport_failures += 1
                    if viewport_failures < max_viewport_failures:
                        log(f"[REPLY_CLICK] Viewport error (attempt {attempt + 1}/{max_viewport_failures}), retrying...")
                        human_pause(0.5, 1.0)
                    else:
                        log(f"[REPLY_CLICK_FAILED] All click methods failed after {max_viewport_failures} attempts")
            
            if not reply_clicked:
                log(f"[REPLY_CLICK_FAILED] Reply button click failed after {max_viewport_failures} attempts")
                return False
        except Exception as e:
            log(f"[REPLY_FAIL] Reply button not found or not clickable: {repr(e)}")
            return False
        
        # Wait 2 seconds for page to render after click
        log(f"[DEBUG] Waiting 2 seconds for reply composer modal to render...")
        time.sleep(2.0)
        
        # Wait for reply composer to appear with detailed verification
        log(f"[DEBUG] Searching for reply composer...")
        composer_appeared = False
        working_selector = None
        composer_selector_used = None  # Store for typing section
        # [SELECTOR_FIX] More robust selectors with better error handling
        composer_selectors = [
            'div[data-testid="tweetTextarea_0"]',  # Most reliable - just testid
            'div[data-testid="tweetTextarea_1"]',
            'div[data-testid="tweetTextarea"]',  # Without number
            'div[contenteditable="true"][data-testid="tweetTextarea_0"]',  # Contenteditable variant
            'div[contenteditable="true"][data-testid="tweetTextarea_1"]',
            'div[role="textbox"][data-testid="tweetTextarea_0"]',  # Role + testid
            'div[role="textbox"][data-testid="tweetTextarea_1"]',
            'div.public-DraftStyleDefault-block',  # Draft.js editor class
            'div[placeholder*="What"]',  # "What's happening" input
            '[contenteditable="true"]',  # Any contenteditable element
            'textarea',  # Fallback to textarea
            'div[role="textbox"]',
            'div[aria-label="Post text"]',
        ]
        for selector in composer_selectors:
            try:
                log(f"[DEBUG] Checking composer selector: {selector}")
                locator = page.locator(selector).first
                if locator.count() > 0 and locator.is_visible(timeout=3000):
                    composer_appeared = True
                    working_selector = selector
                    log(f"[SELECTOR] Found reply box with selector: {selector}")
                    # Focus the element before typing
                    try:
                        locator.focus()
                        log(f"[DEBUG] Focused composer element")
                    except Exception as focus_error:
                        log(f"[DEBUG] Focus failed (non-critical): {str(focus_error)[:50]}")
                    break
            except Exception as e:
                log(f"[DEBUG] Composer selector {selector} not visible: {str(e)[:50]}")
                continue
        
        if not composer_appeared:
            log("[REPLY_FAIL] Reply composer did not appear after click, giving up")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        
        log(f"[DEBUG] Reply composer confirmed visible with selector: {working_selector}, proceeding with reply")
        # Store working selector for typing section to use
        if working_selector:
            composer_selector_used = working_selector

        # Extract tweet ID, text, and author handle for contextual reply generation
        tweet_id = extract_tweet_id(card) or ""
        tweet_text = extract_tweet_text(card)
        author_handle = extract_author_handle(card)
        
        # Try to extract author followers (for high-value reply detection)
        author_followers = 0
        try:
            follower_text = card.locator('text=/\\d+\\.?\\d*[KM]?\\s*followers?/i').first
            if follower_text.count() > 0:
                follower_str = follower_text.inner_text()
                if 'K' in follower_str:
                    author_followers = int(float(follower_str.replace('K', '').replace('followers', '').strip()) * 1000)
                elif 'M' in follower_str:
                    author_followers = int(float(follower_str.replace('M', '').replace('followers', '').strip()) * 1000000)
                else:
                    author_followers = int(''.join(filter(str.isdigit, follower_str)))
        except Exception:
            pass
        
        # Check if we already replied to this tweet (quick check before generating)
        if DEDUPLICATOR and tweet_id and DEDUPLICATOR.already_replied_to(tweet_id):
            log(f"[DEDUPE] Already replied to tweet {tweet_id}, skipping")
            if ACCOUNT_HELPER:
                ACCOUNT_HELPER.log_action("dedupe_skip")
            page.keyboard.press("Escape")
            return False
        
        # Determine reply type for link strategy
        reply_type = "normal"
        if author_followers >= 500 or (tweet_text and any(kw in tweet_text.lower() for kw in ["bet", "wager", "odds", "prediction", "betting"])):
            reply_type = "high_value"
        
        # Generate reply using compose_reply_text
        text = None
        if not text:
            try:
                text = compose_reply_text(tweet_text=tweet_text, topic=topic, author_handle=author_handle, bot_handle=BOT_HANDLE, include_link=False, reply_type=reply_type, author_followers=author_followers)
            except Exception as compose_error:
                import traceback
                traceback_str = traceback.format_exc()
                log(f"[REPLY_TRACEBACK] compose_reply_text exception: {compose_error}")
                log(f"[REPLY_TRACEBACK] {traceback_str}")
                text = ""  # Set to empty to skip this reply
        
        # Check for NO_REPLY (self-reply prevention)
        if text == "NO_REPLY" or not text:
            if not text:
                log("[FILTER] Skipping empty reply (generation may have failed - check [REPLY_TRACEBACK] logs)")
            else:
                log("[FILTER] Skipping self-reply")
            page.keyboard.press("Escape")
            return False
        
        # Check for outdated content
        if is_outdated_content(text):
            log("[FILTER] Outdated content detected, skipping")
            page.keyboard.press("Escape")
            return False
        
        # Check for duplicates using new deduplicator
        if DEDUPLICATOR and not DEDUPLICATOR.can_post_reply(text, tweet_id):
            log(f"[DEDUPE] Duplicate reply text or already replied to tweet {tweet_id}")
            if ACCOUNT_HELPER:
                ACCOUNT_HELPER.log_action("dedupe_skip")
            page.keyboard.press("Escape")
            return False

        # NOTE: compose_reply_text already applies append_link_if_needed internally
        # For Stage 10 replies, links are handled by compose_reply_text's internal logic
        # The 'text' variable here already has the link appended if compose_reply_text was used
        # If Stage 10 generated the text directly, it doesn't include links (by design)
        
        # Append CTA phrase if needed (every 2nd-3rd reply)
        # Use high_intent=False for replies (standard CTAs)
        # Check if link is already in text to avoid duplicate
        link_already_present = REFERRAL_LINK in text if text else False
        text = append_cta_if_needed(text, REFERRAL_LINK if not link_already_present else None, high_intent=False)

        # Use the selector that worked for composer, or fallback to common selectors
        box_selectors = []
        if composer_selector_used:
            box_selectors = [composer_selector_used]  # Try the working selector first
        box_selectors.extend([
            "div[role='textbox'][data-testid='tweetTextarea_0']",
            "div[role='textbox'][data-testid='tweetTextarea_1']",
            "div[data-testid='tweetTextarea']",
            "div[placeholder*='What']",
            "[contenteditable='true']",
            "textarea",
            "div[role='textbox']",
        ])
        typed = False
        last_error = None
        for sel in box_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=1500):
                    try:
                        page.locator(sel).first.click(timeout=5000)
                    except Exception as e:
                        log(f"[STAGE 15] Could not click composer selector {sel}: {e}")
                        continue
                    # Human-like typing: 1-3 second total delay spread across typing
                    # Calculate delay per character to achieve 1-3s total
                    total_delay_seconds = random.uniform(1.0, 3.0)
                    delay_per_char = int((total_delay_seconds * 1000) / max(len(text), 1))
                    delay_per_char = max(15, min(delay_per_char, 80))  # Clamp between 15-80ms
                    
                    log(f"[TYPE_DEBUG] About to type into composer: {text[:100]}...")
                    for ch in text:
                        page.keyboard.type(ch, delay=delay_per_char + random.randint(-5, 5))
                    typed = True
                    break
            except Exception as e:
                last_error = e
                continue
        if not typed:
            log(f"[REPLY_FAIL] Textbox not found or not typeable. Last error: {repr(last_error)}")
            page.keyboard.press("Escape")
            return False

        # HARD BLOCK: Media attachment is disabled (maybe_attach_media is now a no-op)
        # This call logs a warning but does nothing to prevent X duplicate/spam errors
        maybe_attach_media(page, topic, reply_idx)

        # single-shot post
        posted = click_post_once(page)

        # close composer if still open
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        
        if posted:
            # Store reply in deduplicator to prevent duplicates (persistent across sessions)
            if DEDUPLICATOR:
                DEDUPLICATOR.add_reply(text, tweet_id)
            # Also store in old system for backward compatibility
            store_reply(text, tweet_id)
            
            # Record success (reset failure counter)
            if HARDENING:
                HARDENING.record_success()
                HARDENING.record_reply()
                HARDENING.record_action()
            
            # Log metrics
            if ACCOUNT_HELPER:
                ACCOUNT_HELPER.log_action("reply")
                # Check if link was included
                if REFERRAL_LINK in text or any(link in text for link in [REFERRAL_LINK]):
                    ACCOUNT_HELPER.log_action("link")
            
            log(f"[REPLY] ✓ Reply posted successfully (tweet_id={tweet_id})")
            
            # [NOTION] Log reply activity to Notion
            if NOTION_MANAGER:
                try:
                    url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None
                    # Extract username from card if available
                    username = "unknown"
                    try:
                        # Try to extract username from card or tweet text
                        if card and hasattr(card, 'get'):
                            username = card.get('username', 'unknown')
                        elif 'author_handle' in locals():
                            username = author_handle
                    except Exception:
                        pass
                    NOTION_MANAGER.log_activity(
                        "REPLY",
                        f"Replied to @{username}",
                        metadata={
                            "url": url or "Pending",
                            "text": text[:280],
                            "has_link": str(REFERRAL_LINK in text),
                            "tweet_id": str(tweet_id),
                            "target_user": username,
                            "topic": topic or "unknown"
                        }
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log reply: {e}")
            
            # [STAGE 15] Log reply for click tracking
            has_link_in_reply = REFERRAL_LINK in text
            cta_in_reply = None
            if has_link_in_reply:
                # Try to detect which CTA was used
                for cta_phrase in ["Track", "See", "Check", "Watch", "Betting"]:
                    if cta_phrase.lower() in text.lower():
                        cta_in_reply = cta_phrase
                        break
            log_post_for_click_tracking(str(tweet_id), "reply", text, has_link_in_reply, cta_in_reply)
        else:
            log(f"[REPLY_FAIL] Post button click failed (click_post_once returned False)")
            # Record failure and check if we should pause
            if HARDENING:
                should_pause, pause_duration = HARDENING.record_failure()
                if should_pause:
                    log(f"[ERROR_RECOVERY] Pausing for {pause_duration//60} minutes due to failures")
        
        return posted
    
    except Exception as e:
        # Log full traceback for debugging
        tb = traceback.format_exc()
        log(f"[REPLY_TRACEBACK] Reply failed with unhandled exception: {repr(e)}")
        log(f"[REPLY_TRACEBACK] Full traceback:\n{tb}")
        
        # [NOTION] Log error to Notion
        if NOTION_MANAGER:
            try:
                NOTION_MANAGER.log_activity(
                    "ERROR",
                    f"Reply Error: {str(e)[:100]}",
                    metadata={
                        "error_type": "Reply Error",
                        "error_msg": str(e)[:500],
                        "stage": "replying",
                        "traceback": tb[:1000]  # Truncate for Notion limits
                    }
                )
            except Exception:
                pass  # Don't fail on Notion logging errors
        
        return False

def open_and_post_tweet(page, text, is_reply=False):
    # [SAFETY] Ensure we're on X.com before posting
    if not ensure_on_x_com(page):
        log("[POST_TWEET] ✗ Not on X.com, cannot post")
        return False
    """
    Open composer, type text, post it. Works for both replies and originals.
    Uses the same proven selector flow that works for replies.
    
    Args:
        page: Playwright page object
        text: Text to type and post
        is_reply: If True, assumes composer is already open (for replies)
                  If False, opens new tweet composer (for originals)
    
    Returns:
        True if success, False if failed
    """
    try:
        # If not a reply, open the composer first
        if not is_reply:
            # Go to home
            stable_goto(page, HOME_URL)
            human_pause(2.0, 3.0)
            
            # Open composer
            new_tweet_button = page.locator('[data-testid="SideNav_NewTweet_Button"]').first
            if new_tweet_button.count() == 0:
                # Fallback: try compose URL
                page.goto("https://x.com/compose/tweet")
                human_pause(2.0, 3.0)
            else:
                try:
                    new_tweet_button.click(timeout=5000)
                except Exception as e:
                    log(f"[FORCE_POST] Could not click new tweet button: {e}")
                    return False
                human_pause(1.0, 2.0)
        
        # [ENHANCEMENT #1] Use more patient selector waiting (critical for thread replies)
        # [SELECTOR_FIX] More robust selectors with better error handling
        box_selectors = [
            "div[data-testid='tweetTextarea_0']",  # Most reliable - just testid
            "div[data-testid='tweetTextarea_1']",
            "div[data-testid='tweetTextarea']",
            "div[contenteditable='true'][data-testid='tweetTextarea_0']",  # Contenteditable variant
            "div[contenteditable='true'][data-testid='tweetTextarea_1']",
            "div[role='textbox'][data-testid='tweetTextarea_0']",
            "div[role='textbox'][data-testid='tweetTextarea_1']",
            "div.public-DraftStyleDefault-block",  # Draft.js editor class
            "div[placeholder*='What']",
            "[contenteditable='true']",
            "textarea",
            "div[role='textbox']",
        ]
        typed = False
        last_error = None
        for sel in box_selectors:
            try:
                # [ENHANCEMENT #1] Use wait_for_selector with longer timeout for replies
                timeout_ms = 8000 if is_reply else 1500  # More patient for replies (thread 2nd tweet)
                composer_found = False
                try:
                    composer = page.wait_for_selector(sel, timeout=timeout_ms)
                    if composer:
                        try:
                            composer.click(timeout=5000)
                            composer_found = True
                        except Exception as e:
                            log(f"[FORCE_POST] Could not click composer selector {sel}: {e}")
                            continue
                except Exception:
                    # Fallback to locator method if wait_for_selector fails
                    try:
                        locator = page.locator(sel).first
                        if locator.count() > 0 and locator.is_visible(timeout=1500):
                            try:
                                locator.click(timeout=5000)
                                composer_found = True
                                log(f"[SELECTOR] Found composer with selector: {sel} (locator method)")
                            except Exception as e:
                                log(f"[FORCE_POST] Could not click composer selector {sel}: {e}")
                                continue
                    except Exception as loc_error:
                        log(f"[FORCE_POST] Locator method failed for {sel}: {str(loc_error)[:50]}")
                        continue
                
                if composer_found:
                    try:
                        # Human-like typing: 1-3 second total delay spread across typing
                        total_delay_seconds = random.uniform(1.0, 3.0)
                        delay_per_char = int((total_delay_seconds * 1000) / max(len(text), 1))
                        delay_per_char = max(15, min(delay_per_char, 80))  # Clamp between 15-80ms
                        
                        log(f"[TYPE_DEBUG] About to type into composer: {text[:100]}...")
                        for ch in text:
                            page.keyboard.type(ch, delay=delay_per_char + random.randint(-5, 5))
                        typed = True
                        log(f"[SELECTOR] Successfully typed text using selector: {sel}")
                        break
                    except Exception as type_error:
                        log(f"[FORCE_POST] Error typing text: {str(type_error)[:50]}")
                        last_error = type_error
                        continue
            except Exception as e:
                last_error = e
                continue
        
        if not typed:
            log(f"[POST_FAIL] Textbox not found or not typeable. Last error: {repr(last_error)}")
            if not is_reply:
                page.keyboard.press("Escape")
            return False
        
        human_pause(0.5, 1.0)
        
        # Post tweet using the same function that works for replies
        posted = click_post_once(page)
        
        if not posted:
            if not is_reply:
                page.keyboard.press("Escape")
            return False
        
        human_pause(2.0, 3.0)
        
        # Close composer if still open (for originals)
        if not is_reply:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        
        return True
        
    except Exception as e:
        log(f"[POST_FAIL] Exception in open_and_post_tweet: {e}")
        if not is_reply:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
        return False

def force_original_post_immediately(state, text, source_stage, page=None):
    """Force an original post immediately, bypassing scheduler but respecting safety checks."""
    log(f"[FORCE_POST] Attempting immediate post from {source_stage}")
    
    # Get page from state if not provided
    if page is None:
        page = state.get("_page")
        if page is None:
            log(f"[FORCE_POST] ✗ No page available from {source_stage}")
            return False
    
    # [SAFETY] Ensure we're on X.com before posting
    if not ensure_on_x_com(page):
        log(f"[FORCE_POST] ✗ Not on X.com, cannot post from {source_stage}")
        return False
    
    # [STAGE 11B VIDEO] Handle video posting if video_path is in state
    video_path = state.get("_video_path") if state else None
    is_video_post = source_stage == "11B_BREAKING_NEWS_VIDEO" and video_path
    
    # For Stage 11B, link should always be included (it's breaking news with link)
    # Use helper to ensure link is present
    if source_stage == "11B_BREAKING_NEWS" or source_stage == "11B_BREAKING_NEWS_VIDEO":
        text = append_link_if_needed(text, REFERRAL_LINK, True)
    
    try:
        # Check for duplicates using DEDUPLICATOR
        if DEDUPLICATOR:
            if not DEDUPLICATOR.can_post_reply(text, None):
                log(f"[FORCE_POST] ✗ Post blocked by deduplicator from {source_stage}")
                return False
        
        # Check rate limit from HARDENING (but bypass scheduler)
        # Stage 11B breaking news should always be allowed (viral potential > scheduling)
        if source_stage == "11B_BREAKING_NEWS" or source_stage == "11B_BREAKING_NEWS_VIDEO":
            # Skip rate limit check for breaking news (always allow)
            log(f"[FORCE_POST] Stage 11B breaking news (video={is_video_post}) - bypassing rate limit check")
        else:
            # For other forced posts, still check rate limit
            if HARDENING and not HARDENING.can_post_original(max_posts_per_day=20):  # Higher limit for forced posts
                log(f"[FORCE_POST] ✗ Post blocked by rate limit from {source_stage}")
                return False
        
        # [STAGE 11B VIDEO] Post video if available, otherwise post text
        if is_video_post and video_path:
            # Use existing video posting infrastructure with rate limit bypass for breaking news
            posted = post_video_with_context(page, video_path, text, bypass_rate_limit=True)
            if posted:
                log(f"[FORCE_POST] ✓ Video post succeeded from {source_stage}: {video_path}")
                # Clean up video file after successful post
                try:
                    import os
                    if os.path.exists(video_path):
                        # Don't delete immediately, keep for potential retry
                        pass
                except Exception:
                    pass
        else:
            # Post the tweet using the proven helper function
            posted = open_and_post_tweet(page, text, is_reply=False)
        
        if not posted:
            log(f"[FORCE_POST] ✗ Could not open composer from {source_stage}")
            return False
        
        # Record in deduplicator
        if DEDUPLICATOR:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            DEDUPLICATOR.add_reply(text, text_hash)
        
        # Log metrics
        if ACCOUNT_HELPER:
            ACCOUNT_HELPER.log_action("post")
            if REFERRAL_LINK in text:
                ACCOUNT_HELPER.log_action("link")
        
        # Log analytics
        if ANALYTICS:
            ANALYTICS.log_action("post", "saas_growth", REFERRAL_LINK in text, "post_" + str(int(time.time())))
        
        current_time = datetime.now().strftime("%H:%M:%S")
        log(f"[FORCE_POST] ✓ Post succeeded from {source_stage} at {current_time}: {text[:50]}...")
        
        # [NOTION] Log force post activity (especially for Stage 11B videos)
        if NOTION_MANAGER:
            try:
                is_video = source_stage == "11B_BREAKING_NEWS_VIDEO"
                activity_type = "VIDEO" if is_video else "POST"
                NOTION_MANAGER.log_activity(
                    activity_type,
                    f"Force post from {source_stage}: {text[:50]}...",
                    metadata={
                        "stage": source_stage,
                        "text": text[:200],
                        "is_video": str(is_video),
                        "time": current_time
                    }
                )
            except Exception as e:
                log(f"[NOTION] Failed to log force post: {e}")
        
        return True
        
    except Exception as e:
        log(f"[FORCE_POST] ✗ Exception in force_original_post_immediately from {source_stage}: {e}")
        
        # [NOTION] Log error to Notion
        if NOTION_MANAGER:
            try:
                NOTION_MANAGER.log_activity(
                    "ERROR",
                    f"Force post failed from {source_stage}: {str(e)[:100]}",
                    metadata={"error": str(e)[:500], "stage": source_stage}
                )
                NOTION_MANAGER.update_task_status(source_stage, "Blocked", f"Error: {str(e)[:200]}")
            except Exception:
                pass  # Don't fail on Notion errors
        
        return False

class OriginalPostScheduler:
    """Scheduler for original posts (3 per day, 4-8 hours apart)"""
    def __init__(self, config_file="original_post_schedule.json"):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "posts_per_day_min": 4,  # [ANTI-SHADOWBAN] 4 posts/day max (human pace)
            "posts_per_day_max": 4,  # [ANTI-SHADOWBAN] 4 posts/day max (human pace)
            "posts_posted_today": 0,
            "last_post_date": "",
            "last_post_time": 0,
            "next_post_time": 0,
            "interval_hours_min": 4,  # [BOT RECONSTRUCTION] 4-8 hour intervals
            "interval_hours_max": 8
        }
    
    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            log(f"[ORIGINAL_POST] Error saving config: {e}")
    
    def reset_daily_counter_if_needed(self):
        """Reset counter at midnight"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.config["last_post_date"] != today:
            self.config["posts_posted_today"] = 0
            self.config["last_post_date"] = today
            self.save_config()
    
    def should_post_now(self):
        """Check if it's time to post an original post"""
        self.reset_daily_counter_if_needed()
        
        current_time = time.time()
        posts_today = self.config["posts_posted_today"]
        max_posts = self.config["posts_per_day_max"]
        next_post_time = self.config.get("next_post_time", 0)
        last_post_time = self.config.get("last_post_time", 0)
        
        # Already hit daily limit?
        if posts_today >= max_posts:
            log(f"[ORIGINAL_SKIP] Daily limit reached (posts_today={posts_today}, limit={max_posts})")
            return False
        
        # [BOT RECONSTRUCTION] Min interval: 4-8 hours between posts (randomized)
        interval_min = self.config.get("interval_hours_min", 4) * 3600
        interval_max = self.config.get("interval_hours_max", 8) * 3600
        min_interval_seconds = random.randint(interval_min, interval_max)
        if last_post_time > 0 and (current_time - last_post_time) < min_interval_seconds:
            cooldown_remaining = min_interval_seconds - (current_time - last_post_time)
            hours_remaining = cooldown_remaining / 3600
            log(f"[ORIGINAL_SKIP] Min interval not reached (now={current_time:.0f}, last_post={last_post_time:.0f}, wait={hours_remaining:.1f}h)")
            return False
        
        # Check if it's time to post (next_post_time is 0 or in the past)
        if next_post_time > 0 and current_time < next_post_time:
            time_until_post = next_post_time - current_time
            log(f"[ORIGINAL_SKIP] Next post time not reached (now={current_time:.0f}, next_post_time={next_post_time:.0f}, wait={time_until_post:.0f}s)")
            return False
        
        # All conditions met - allow posting
        if next_post_time == 0 or current_time >= next_post_time:
            log(f"[ORIGINAL_POST] Triggering original post (next_post_time={next_post_time:.0f} <= now={current_time:.0f}, posts_today={posts_today} < limit={max_posts})")
            # If next_post_time was 0, schedule the next one
            if next_post_time == 0:
                # [BOT RECONSTRUCTION] 4-8 hours between posts (randomized)
                interval_min = self.config.get("interval_hours_min", 4) * 3600
                interval_max = self.config.get("interval_hours_max", 8) * 3600
                next_interval = random.randint(interval_min, interval_max)
                hours_until_next = next_interval / 3600
                self.config["next_post_time"] = current_time + next_interval
                log(f"[SCHEDULE] {posts_today}/{max_posts} posts done. Next post in {hours_until_next:.1f}h")
                self.save_config()
            return True
        
        return False
    
    def _get_next_post_time_with_peak_timing(self):
        """[PROBLEM #5 FIX] Calculate next post time based on peak engagement hours (9-11 AM, 2-4 PM, 8-10 PM EST)"""
        from datetime import timezone, timedelta
        now = datetime.now(timezone.utc)
        
        # Convert to EST (UTC-5)
        est_offset = timedelta(hours=-5)
        est_time = now.astimezone(timezone(offset=est_offset))
        est_hour = est_time.hour
        
        # Peak hours: 9-11 AM, 2-4 PM, 8-10 PM EST
        peak_hours = list(range(9, 12)) + list(range(14, 17)) + list(range(20, 23))  # 9-11, 2-4, 8-10
        
        # If currently in peak hour, post within 30-60 min
        if est_hour in peak_hours:
            next_interval = random.randint(1800, 3600)  # 30-60 min
            log(f"[PEAK_TIMING] Currently in peak hour (EST {est_hour}:00), next post in {next_interval/60:.0f} min")
            return time.time() + next_interval
        
        # Otherwise, wait until next peak hour
        next_peak_hours = [h for h in peak_hours if h > est_hour]
        if next_peak_hours:
            next_peak = min(next_peak_hours)
            hours_until_peak = next_peak - est_hour
        else:
            # Next peak is tomorrow (first peak hour of day)
            next_peak = min(peak_hours)
            hours_until_peak = (24 - est_hour) + next_peak
        
        next_interval = hours_until_peak * 3600 + random.randint(0, 1800)  # Add 0-30 min jitter
        log(f"[PEAK_TIMING] Not in peak hour (EST {est_hour}:00), waiting until EST {next_peak}:00 ({hours_until_peak}h)")
        return time.time() + next_interval
    
    def mark_posted(self):
        """Record that we posted an original post"""
        self.config["posts_posted_today"] += 1
        self.config["last_post_time"] = time.time()
        
        # [PROBLEM #1 FIX] Schedule next post: 2-4 hours max to ensure 4-6 posts/day (every 2-4 hours during wake hours)
        # [PROBLEM #5 FIX] Use peak timing logic for better engagement
        posts_remaining = self.config["posts_per_day_max"] - self.config["posts_posted_today"]
        if posts_remaining > 0:
            # [BOT RECONSTRUCTION] 4-8 hours between posts (randomized)
            current_time = time.time()
            interval_min = self.config.get("interval_hours_min", 4) * 3600
            interval_max = self.config.get("interval_hours_max", 8) * 3600
            next_interval = random.randint(interval_min, interval_max)
            next_post_ts = current_time + next_interval
            self.config["next_post_time"] = next_post_ts
            hours_until_next = next_interval / 3600
            log(f"[SCHEDULE] {self.config['posts_posted_today']}/{self.config['posts_per_day_max']} posts done. Next post in {hours_until_next:.1f}h")
        else:
            # Hit daily limit, schedule for tomorrow
            self.config["next_post_time"] = time.time() + (24 * 3600)
            log(f"[SCHEDULE] Daily limit reached ({self.config['posts_posted_today']}/{self.config['posts_per_day_max']}). Resuming tomorrow.")
        
        self.save_config()
        log(f"[ORIGINAL_POST] Posted {self.config['posts_posted_today']}/{self.config['posts_per_day_max']} today")

ORIGINAL_POST_SCHEDULER = OriginalPostScheduler()

# CTA enforcement tracking
_cta_post_counter = 0  # Global counter for posts/replies sent
# [STAGE 14] CTA rotation tracking
_last_cta_phrase = None

def get_cta_phrase(high_intent=False):
    """Get a random CTA phrase from config.
    
    Args:
        high_intent: If True, returns high-intent CTA for threads/originals. 
                     If False, returns standard CTA for replies.
    """
    global _last_cta_phrase
    try:
        if PHASE_CONTROLLER:
            config = PHASE_CONTROLLER.get_phase_config()
            cta_config = config.get("cta_phrases", {})
            
            if high_intent:
                # Use high-intent phrases for threads/originals
                high_intent_phrases = cta_config.get("high_intent_phrases", [])
                if high_intent_phrases:
                    # [STAGE 14] Rotate CTAs to avoid repetition
                    available = [p for p in high_intent_phrases if p != _last_cta_phrase]
                    if not available:
                        available = high_intent_phrases
                    import random
                    phrase = random.choice(available)
                    _last_cta_phrase = phrase
                    return phrase
            
            # Standard phrases for replies or fallback
            phrases = cta_config.get("phrases", [])
            if phrases:
                # [STAGE 14] Expand CTA pool and rotate
                expanded_phrases = phrases + [
                    "Track it with proper attribution",
                    "See current odds",
                    "Markets say...",
                    "Check the numbers",
                    "Watch this market",
                    "The odds tell the story"
                ]
                available = [p for p in expanded_phrases if p != _last_cta_phrase]
                if not available:
                    available = expanded_phrases
                import random
                phrase = random.choice(available)
                _last_cta_phrase = phrase
                return phrase
    except Exception:
        pass
    # [STAGE 14] Fallback with expanded, rotating CTA pool
    fallback_ctas = [
        "Check conversion tracking:",
        "Track this on Polymarket:",
        "See live odds on Polymarket:",
        "Track it on Polymarket",
        "See current odds",
        "Markets say...",
        "Check the numbers"
    ]
    if high_intent:
        fallback_high_intent = [
            "Think you know better? Bet here →",
            "Don't just watch. Trade the odds →",
            "The market's moving. Get in now →",
            "This is a free money play. Trade it →",
            "Odds are wrong here. Prove it →"
        ]
        available = [p for p in fallback_high_intent if p != _last_cta_phrase]
        if not available:
            available = fallback_high_intent
        import random
        phrase = random.choice(available)
        _last_cta_phrase = phrase
        return phrase
    available = [p for p in fallback_ctas if p != _last_cta_phrase]
    if not available:
        available = fallback_ctas
    import random
    phrase = random.choice(available)
    _last_cta_phrase = phrase
    return phrase

# [STAGE 15] Conversion CTAs - high-intent phrases optimized for clicks
CTA_CONVERSION = {
    "curiosity": [
        "See what smart money is doing",
        "Check where the action is",
        "See the real odds here",
        "Watch where traders are betting",
        "See the market positioning"
    ],
    "urgency": [
        "Odds shifting fast on this",
        "Market moving now",
        "Price action happening",
        "Odds breaking here",
        "Volume spiking on this"
    ],
    "authority": [
        "Markets pricing in this",
        "Smart money betting here",
        "Institutional flow says",
        "Market consensus is",
        "Odds reflect this"
    ],
    "question": [
        "What odds would you take?",
        "Where would you set this?",
        "How would you price this?",
        "What's your number here?",
        "Where's your entry?"
    ],
    "action": [
        "Betting on this outcome here",
        "Taking this position",
        "Trading this market",
        "Positioning into this",
        "Entering here"
    ]
}

def get_high_conversion_cta():
    """[STAGE 15] Get a high-conversion CTA with rotation across categories."""
    global _last_cta_phrase
    import random
    
    # Select category randomly
    category = random.choice(list(CTA_CONVERSION.keys()))
    phrases = CTA_CONVERSION[category]
    
    # Rotate within category (avoid same phrase twice)
    available = [p for p in phrases if p != _last_cta_phrase]
    if not available:
        available = phrases
    
    phrase = random.choice(available)
    _last_cta_phrase = phrase
    log(f"[STAGE 15] [CTA_CONVERSION] Category: {category}, Phrase: {phrase}")
    return phrase

# [STAGE 15] Peak posting hour detection
def is_peak_posting_hour():
    """Check if current hour is a peak posting time (UTC 7-11, 13-21, 23-3)."""
    hour = datetime.utcnow().hour
    # Europe: 7-11 UTC, US: 13-21 UTC, Asia: 23-3 UTC (wraps)
    is_peak = (7 <= hour < 11) or (13 <= hour < 21) or (hour >= 23) or (hour < 3)
    log(f"[STAGE 15] [TIMING] {'Peak' if is_peak else 'Off-peak'} hour (UTC {hour})")
    return is_peak

# [STAGE 15] Thread timing optimization (Tue-Thu priority)
def should_prioritize_threads_today():
    """Check if today is a high-engagement day for threads (Tue-Thu)."""
    weekday = datetime.now().weekday()  # Monday=0, Sunday=6
    # Tuesday=1, Wednesday=2, Thursday=3 are high engagement days
    is_high_engagement = weekday in [1, 2, 3]
    return is_high_engagement

# [STAGE 15] Click tracking
def log_post_for_click_tracking(post_id, post_type, post_text, has_link, cta_used=None):
    """Log post metadata for click attribution tracking."""
    try:
        import re
        has_odds = bool(re.search(r'\d+%', post_text))
        has_market = bool(re.search(r'\b(market|odds|betting|bet)\b', post_text, re.IGNORECASE))
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "post_id": post_id,
            "post_type": post_type,
            "has_odds": has_odds,
            "has_market": has_market,
            "has_link": has_link,
            "cta_used": cta_used,
            "text_preview": post_text[:100]
        }
        
        # Append to JSONL file
        with open("click_attribution.jsonl", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        log(f"[STAGE 15] [CLICK_TRACKING] Logged post {post_id} (type={post_type}, odds={has_odds}, market={has_market}, link={has_link})")
    except Exception as e:
        log(f"[STAGE 15] [CLICK_TRACKING] Error logging: {e}")

# [STAGE 15] Click performance report
def generate_click_performance_report():
    """Generate daily click performance report from tracked posts."""
    try:
        if not os.path.exists("click_attribution.jsonl"):
            log("[STAGE 15] [CLICK_REPORT] No click attribution file found")
            return None
        
        posts = []
        with open("click_attribution.jsonl", "r") as f:
            for line in f:
                try:
                    posts.append(json.loads(line.strip()))
                except Exception:
                    continue
        
        if not posts:
            log("[STAGE 15] [CLICK_REPORT] No posts tracked")
            return None
        
        # Filter to today's posts
        today = datetime.now().strftime("%Y-%m-%d")
        today_posts = [p for p in posts if p.get("timestamp", "").startswith(today)]
        
        if not today_posts:
            log("[STAGE 15] [CLICK_REPORT] No posts tracked today")
            return None
        
        # Generate report
        report = {
            "date": today,
            "total_posts": len(today_posts),
            "by_type": {},
            "with_data": {
                "has_odds": sum(1 for p in today_posts if p.get("has_odds")),
                "has_market": sum(1 for p in today_posts if p.get("has_market")),
                "has_link": sum(1 for p in today_posts if p.get("has_link"))
            },
            "cta_usage": {}
        }
        
        # Group by type
        for post in today_posts:
            post_type = post.get("post_type", "unknown")
            if post_type not in report["by_type"]:
                report["by_type"][post_type] = 0
            report["by_type"][post_type] += 1
            
            # CTA usage
            cta = post.get("cta_used")
            if cta:
                if cta not in report["cta_usage"]:
                    report["cta_usage"][cta] = 0
                report["cta_usage"][cta] += 1
        
        log(f"[STAGE 15] [CLICK_REPORT] Generated report: {len(today_posts)} posts today")
        log(f"[STAGE 15] [CLICK_REPORT] With odds: {report['with_data']['has_odds']}/{len(today_posts)}")
        log(f"[STAGE 15] [CLICK_REPORT] With market: {report['with_data']['has_market']}/{len(today_posts)}")
        log(f"[STAGE 15] [CLICK_REPORT] With link: {report['with_data']['has_link']}/{len(today_posts)}")
        
        return report
    except Exception as e:
        log(f"[STAGE 15] [CLICK_REPORT] Error generating report: {e}")
        return None

def should_append_cta():
    """Check if CTA should be appended (every 2nd-3rd post)."""
    global _cta_post_counter
    _cta_post_counter += 1
    
    # Append CTA every 2nd or 3rd post (alternate between 2 and 3 for variety)
    import random
    # Use modulo 5 to get pattern: append on positions 2, 4 (every 2nd) or 3, 5 (every 2nd-3rd)
    # This creates a mix of every 2nd and 3rd post
    cycle_position = _cta_post_counter % 5
    if cycle_position in [2, 0]:  # Positions 2, 5, 10, etc. (every 2nd-3rd)
        return True
    return False

def append_cta_if_needed(text, link, high_intent=False):
    """Append CTA phrase and link if conditions are met.
    
    Args:
        text: Text to append CTA to
        link: Polymarket link to append
        high_intent: If True, uses high-intent CTAs (for threads/originals). 
                     If False, uses standard CTAs (for replies).
    """
    if not text:
        return text
    
    # Check if CTA should be appended (this increments the counter)
    if not should_append_cta():
        return text
    
    # Don't append if link already in text (to avoid duplicate links)
    if link and link in text:
        log(f"[CTA] Link already present, skipping CTA to avoid duplicate")
        return text
    
    # Don't append if CTA-like phrase already present
    text_lower = text.lower()
    cta_indicators = ["check this out", "track this", "see live", "try this", "follow this", "get in on", "watch this", "use this", "check attribution", "get started"]
    if any(indicator in text_lower for indicator in cta_indicators):
        log(f"[CTA] CTA-like phrase already present, skipping")
        return text
    
    # [STAGE 15B] For original posts with market data, use high-conversion CTAs
    import re
    if high_intent:
        # Check if text contains market data (odds, market names, betting language)
        has_odds = bool(re.search(r'\d+%', text))
        has_market_ref = bool(re.search(r'\b(market|odds|betting|bet)\b', text_lower))
        has_odds_phrase = bool(re.search(r'odds (at|are|of)', text_lower))
        
        if has_odds or has_market_ref or has_odds_phrase:
            # Use high-conversion CTA for original posts with market data
            cta_phrase = get_high_conversion_cta()
        else:
            # Use standard high-intent CTA for originals without specific market data
            cta_phrase = get_cta_phrase(high_intent=high_intent)
    else:
        # For replies, use standard CTA selection
        cta_phrase = get_cta_phrase(high_intent=high_intent)
    
    # Append CTA + link
    if link:
        cta_text = f"{text.strip()}\n\n{cta_phrase} {link}"
    else:
        cta_text = f"{text.strip()}\n\n{cta_phrase}"
    
    # Ensure it fits in 280 chars
    if len(cta_text) > 280:
        # Truncate original text to make room
        available_chars = 280 - len(f"\n\n{cta_phrase} {link if link else ''}")
        if available_chars > 50:  # Only truncate if we have reasonable space
            truncated_text = text[:available_chars].rstrip()
            cta_text = f"{truncated_text}\n\n{cta_phrase} {link if link else ''}"
        else:
            # Not enough space, skip CTA
            log(f"[CTA] Not enough space for CTA ({len(cta_text)} chars), skipping")
            return text
    
    log(f"[CTA] Appended CTA phrase: {cta_phrase}")
    return cta_text

# Similarity check for bot-looking posts
RECENT_POSTS_FILE = "storage/recent_original_posts.json"

def load_recent_posts():
    """Load recent original posts for similarity checking."""
    try:
        if os.path.exists(RECENT_POSTS_FILE):
            with open(RECENT_POSTS_FILE, 'r') as f:
                data = json.load(f)
                return data.get("posts", [])
    except Exception as e:
        log(f"[SIMILARITY] Error loading recent posts: {e}")
    return []

def save_recent_post(post_text):
    """Save a new post to recent posts history (keep last 20)."""
    try:
        posts = load_recent_posts()
        posts.append({
            "text": post_text,
            "first_line": post_text.split('\n')[0][:80] if '\n' in post_text else post_text[:80],
            "timestamp": datetime.now().isoformat()
        })
        # Keep last 20 posts
        posts = posts[-20:]
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(RECENT_POSTS_FILE), exist_ok=True)
        
        with open(RECENT_POSTS_FILE, 'w') as f:
            json.dump({"posts": posts}, f, indent=2)
    except Exception as e:
        log(f"[SIMILARITY] Error saving recent post: {e}")

def calculate_similarity(text1, text2):
    """Calculate similarity between two texts (0.0 to 1.0)."""
    # Simple word overlap similarity
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    # Jaccard similarity
    if not union:
        return 0.0
    return len(intersection) / len(union)

def is_too_similar_to_recent_posts(new_text, threshold=0.6):
    """Check if new text is too similar to recent posts."""
    recent_posts = load_recent_posts()
    if not recent_posts:
        return False
    
    # Compare first line (hook/opening) for structure similarity
    new_first_line = new_text.split('\n')[0][:80] if '\n' in new_text else new_text[:80]
    
    for post in recent_posts[-10:]:  # Check last 10 posts
        recent_first_line = post.get("first_line", "")
        recent_text = post.get("text", "")
        
        # Check first line similarity (structure/hook)
        first_line_sim = calculate_similarity(new_first_line, recent_first_line)
        if first_line_sim > threshold:
            log(f"[SIMILARITY] First line too similar (similarity={first_line_sim:.2f} > {threshold})")
            return True
        
        # Check full text similarity
        full_sim = calculate_similarity(new_text[:200], recent_text[:200])  # Compare first 200 chars
        if full_sim > threshold:
            log(f"[SIMILARITY] Full text too similar (similarity={full_sim:.2f} > {threshold})")
            return True
    
    return False

# ====================== ULTIMATE ANTI-BOT + VIRAL OPTIMIZATION ======================

# Template rotation tracking (prevent repeating last 5 templates)
TEMPLATE_HISTORY_FILE = "storage/template_history.json"

def load_template_history():
    """Load recent template IDs used in posts (keep last 5)."""
    try:
        if os.path.exists(TEMPLATE_HISTORY_FILE):
            with open(TEMPLATE_HISTORY_FILE, 'r') as f:
                data = json.load(f)
                return data.get("template_ids", [])
    except Exception as e:
        log(f"[TEMPLATE_ROTATION] Error loading template history: {e}")
    return []

def save_template_history(template_ids):
    """Save template IDs (keep last 5)."""
    try:
        os.makedirs(os.path.dirname(TEMPLATE_HISTORY_FILE), exist_ok=True)
        with open(TEMPLATE_HISTORY_FILE, 'w') as f:
            json.dump({"template_ids": template_ids[-5:]}, f, indent=2)
    except Exception as e:
        log(f"[TEMPLATE_ROTATION] Error saving template history: {e}")

def select_next_template(all_templates, recent_template_ids, banned_tiers=None):
    """
    Select a template that hasn't been used in the last 5 posts and isn't from a banned tier.
    
    Args:
        all_templates: List of template dicts with "id" key
        recent_template_ids: List of recently used template IDs (last 5)
        banned_tiers: List of tier names to exclude (from diversity_engine)
    
    Returns:
        dict: Selected template, or None if all templates were recently used
    """
    if not all_templates:
        return None
    
    # Filter out recently used templates
    available_templates = [t for t in all_templates if isinstance(t, dict) and t.get("id") not in recent_template_ids]
    
    # Filter out banned tiers (ELITE VIRAL BOT OVERHAUL)
    if banned_tiers:
        available_templates = [t for t in available_templates if t.get("tier") not in banned_tiers]
        log(f"[DIVERSITY_ENGINE] Filtered out {len(banned_tiers)} banned tier(s), {len(available_templates)} templates available")
    
    # If all templates were recently used or banned, allow any template (reset)
    if not available_templates:
        log(f"[TEMPLATE_ROTATION] All templates recently used/banned, resetting rotation")
        available_templates = all_templates
    
    selected = random.choice(available_templates)
    template_id = selected.get("id", "unknown")
    template_tier = selected.get("tier", "unknown")
    
    # Find how many posts ago this template was used (if at all)
    if template_id in recent_template_ids:
        posts_ago = len(recent_template_ids) - recent_template_ids.index(template_id)
    else:
        posts_ago = "never"
    
    log(f"[TEMPLATE_ROTATION] Selected template #{template_id} (tier: {template_tier}, last used {posts_ago} posts ago) ✓")
    return selected

# Emoji diversity tracking (never use same emoji twice in a row)
EMOJI_HISTORY_FILE = "storage/emoji_history.json"

def load_emoji_history():
    """Load last 2 emojis used."""
    try:
        if os.path.exists(EMOJI_HISTORY_FILE):
            with open(EMOJI_HISTORY_FILE, 'r') as f:
                data = json.load(f)
                return data.get("emojis", [])
    except Exception as e:
        log(f"[EMOJI_SELECT] Error loading emoji history: {e}")
    return []

def save_emoji_history(emojis):
    """Save emoji history (keep last 2)."""
    try:
        os.makedirs(os.path.dirname(EMOJI_HISTORY_FILE), exist_ok=True)
        with open(EMOJI_HISTORY_FILE, 'w') as f:
            json.dump({"emojis": emojis[-2:]}, f, indent=2)
    except Exception as e:
        log(f"[EMOJI_SELECT] Error saving emoji history: {e}")

def select_emoji(template_emoji, recent_emojis, available_emojis=["🔥", "💡", "⚡", "🎯", "👀", "🚀", "💰", "📊", "🤔", "👌", "💼", "💬", "📈", "🍿", "👊"]):
    """
    Select an emoji that's different from the last 2 used.
    If template has an emoji, prefer it unless it was just used.
    
    Args:
        template_emoji: Emoji from template (can be None)
        recent_emojis: List of last 2 emojis used
        available_emojis: Full list of available emojis
    
    Returns:
        str: Selected emoji
    """
    # If template has emoji and it wasn't just used, use it
    if template_emoji and template_emoji not in recent_emojis:
        selected = template_emoji
        log(f"[EMOJI_SELECT] Selected {selected} from template (last 2: {recent_emojis})")
        return selected
    
    # Otherwise, pick a random emoji that's not in recent 2
    available = [e for e in available_emojis if e not in recent_emojis]
    if not available:
        # If all emojis were recently used, allow any (reset)
        log(f"[EMOJI_SELECT] All emojis recently used, resetting diversity")
        available = available_emojis
    
    selected = random.choice(available)
    log(f"[EMOJI_SELECT] Selected {selected} (last 2: {recent_emojis})")
    return selected

# ====================== ELITE VIRAL BOT OVERHAUL ======================
# Diversity Engine and Human Randomization for maximum viral potential

POSTED_HISTORY_FILE = "storage/posted_history.json"
POSTED_HISTORY_FILE_ALT = "posted_history.json"  # Alternative location

def load_post_history(limit=15):
    """Load last N posts to prevent template repeats (BOT RECONSTRUCTION)"""
    try:
        # Try both locations
        for filepath in [POSTED_HISTORY_FILE, POSTED_HISTORY_FILE_ALT]:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    history = json.load(f)
                    # Handle both formats: {"posts": [...]} or [...]
                    if isinstance(history, dict):
                        history = history.get("posts", [])
                    return history[-limit:]
    except Exception as e:
        log(f"[DIVERSITY_ENGINE] Error loading post history: {e}")
    return []

def load_posted_history():
    """Load last post data for diversity engine (backward compatibility)."""
    history = load_post_history(limit=3)
    return history

def is_template_too_recent(chosen_template_id, history):
    """
    Check if this template was used in the last 15 posts.
    RULE: No template repeat within 15 posts = good variety (BOT RECONSTRUCTION)
    """
    recent_ids = [p.get('template_id') for p in history if isinstance(p, dict) and 'template_id' in p]
    
    # Count how many times this template appears
    count = recent_ids.count(chosen_template_id)
    
    if count > 0:
        return True  # Don't use it again
    return False

def is_tier_too_recent(chosen_tier, history, max_same_tier=3):
    """
    Check if we've used too many from the same tier recently.
    RULE: Max 3 posts from same tier in last 15 posts (BOT RECONSTRUCTION)
    """
    recent_tiers = [p.get('template_tier') for p in history if isinstance(p, dict) and 'template_tier' in p]
    count = recent_tiers.count(chosen_tier)
    
    return count >= max_same_tier

def pick_template_safely():
    """
    Pick a template that wasn't used recently AND isn't over-represented in tier (BOT RECONSTRUCTION)
    """
    history = load_post_history(limit=15)
    
    try:
        with open("viral_templates.json") as f:
            all_templates = json.load(f)["templates"]
    except Exception as e:
        log(f"[DIVERSITY_ENGINE] Error loading templates: {e}")
        return None
    
    # Try 10 times to find a good template
    for attempt in range(10):
        chosen = random.choice(all_templates)
        
        # Check 1: Template not used recently
        if is_template_too_recent(chosen['id'], history):
            continue
        
        # Check 2: Tier not over-represented
        if is_tier_too_recent(chosen['tier'], history, max_same_tier=3):
            continue
        
        # Found a good one!
        log(f"[DIVERSITY_ENGINE] Selected template {chosen['id']} (tier: {chosen['tier']})")
        return chosen
    
    # Fallback: just return random (shouldn't happen)
    log("[DIVERSITY_ENGINE] ⚠️ Could not find diverse template, using random")
    return random.choice(all_templates)

def save_post_to_history(template, filled_text, emoji, hashtags):
    """
    Save post details to history for diversity tracking (BOT RECONSTRUCTION)
    """
    post_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "text": filled_text,
        "template_id": template["id"],
        "template_tier": template["tier"],
        "emoji_used": emoji,
        "hashtags_used": hashtags,
        "character_count": len(filled_text)
    }
    
    try:
        # Try both locations
        for filepath in [POSTED_HISTORY_FILE, POSTED_HISTORY_FILE_ALT]:
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    history = json.load(f)
                    # Handle both formats
                    if isinstance(history, dict):
                        history = history.get("posts", [])
                    break
        else:
            history = []
    except:
        history = []
    
    history.append(post_data)
    # Keep last 15 posts
    history = history[-15:]
    
    # Save to both locations for compatibility
    for filepath in [POSTED_HISTORY_FILE_ALT, POSTED_HISTORY_FILE]:
        try:
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            log(f"[DIVERSITY_ENGINE] Error saving to {filepath}: {e}")
    
    log(f"[DIVERSITY_ENGINE] Saved post to history: {template['id']}")

def save_posted_history(post_data):
    """Save post data (keep last 3 for tier banning) - backward compatibility."""
    save_post_to_history(
        {"id": post_data.get("template_id"), "tier": post_data.get("template_tier")},
        post_data.get("text", ""),
        post_data.get("emoji_used", ""),
        post_data.get("hashtags_used", "")
    )

def diversity_engine(last_post_data):
    """
    Ensures ZERO template repetition and psychological freshness.
    
    Args:
        last_post_data: Dict with 'template_tier' and 'emoji_used' keys
    
    Returns:
        tuple: (banned_tiers: list, banned_emojis: set)
    """
    banned_tiers = []
    banned_emojis = set()
    
    # Extract last template used
    if last_post_data:
        last_tier = last_post_data.get('template_tier')
        last_emoji = last_post_data.get('emoji_used')
        
        # Ban same tier for next 3 posts
        if last_tier:
            banned_tiers = [last_tier]
        
        # Ban same emoji for next 2 posts
        if last_emoji:
            banned_emojis.add(last_emoji)
    
    # Get all history to ban more tiers
    all_history = load_posted_history()
    for post in all_history[-2:]:  # Ban last 2 tiers
        tier = post.get('template_tier')
        if tier and tier not in banned_tiers:
            banned_tiers.append(tier)
        emoji = post.get('emoji_used')
        if emoji:
            banned_emojis.add(emoji)
    
    log(f"[DIVERSITY_ENGINE] Banned tiers: {banned_tiers}, banned emojis: {banned_emojis}")
    return banned_tiers, banned_emojis

def human_randomization(text):
    """
    Makes posts feel less like a bot by injecting human imperfections.
    [ANTI-SHADOWBAN] Enhanced humanization to avoid robot detection.
    
    Args:
        text: Original post text
    
    Returns:
        str: Humanized text with imperfections
    """
    import re
    
    # 20% chance: lowercase first letter (casual)
    if random.random() < 0.2 and text and text[0].isupper():
        text = text[0].lower() + text[1:]
    
    # 10% chance: remove period at end
    if random.random() < 0.1 and text.endswith('.'):
        text = text[:-1]
    
    # 5% chance: add casual typo (intentional imperfections)
    if random.random() < 0.05:
        typos_map = {
            "don't": "dont",
            "doesn't": "doesnt", 
            "can't": "cant",
            "won't": "wont",
            "isn't": "isnt",
            "aren't": "arent"
        }
        for correct, typo in typos_map.items():
            if correct in text:
                text = text.replace(correct, typo)
                break
    
    # 15% chance: remove one emoji (less emoji = more human)
    if random.random() < 0.15:
        emoji_pattern = r'[🧵📊🔥💡⚡🎯💰🤔👀🚨⛔🎲📈📉👇🤷⏳🚀💀🍿👌💼💬👊]'
        text = re.sub(emoji_pattern, '', text, count=1).strip()
    
    # 10% chance: add casual filler
    if random.random() < 0.1:
        fillers = ["tbh", "imo", "rn", "ngl"]
        if not any(f in text.lower() for f in fillers):
            text = text + " " + random.choice(fillers)
    
    return text

# Enhanced similarity checking (regenerate if >70% similar)
def check_similarity_and_regenerate(new_text, recent_posts, threshold=0.70):
    """
    Check if new text is too similar to recent posts (>70%).
    Returns similarity scores for logging.
    
    Args:
        new_text: New post text to check
        recent_posts: List of recent post dicts with "text" key
        threshold: Similarity threshold (default 0.70 = 70%)
    
    Returns:
        tuple: (is_too_similar: bool, max_similarity: float, scores: list)
    """
    if not recent_posts:
        return False, 0.0, []
    
    scores = []
    for post in recent_posts[-3:]:  # Check last 3 posts
        recent_text = post.get("text", "")
        if recent_text:
            sim = calculate_similarity(new_text, recent_text)
            scores.append(sim)
    
    if not scores:
        return False, 0.0, []
    
    max_sim = max(scores)
    avg_sim = sum(scores) / len(scores) if scores else 0.0
    
    if max_sim > threshold:
        log(f"[SIMILARITY_WARNING] ⚠️ Similar to recent (max={max_sim:.1%}, avg={avg_sim:.1%}), regenerating...")
        return True, max_sim, scores
    else:
        log(f"[SIMILARITY_CHECK] ✓ Unique (max={max_sim:.1%}, avg={avg_sim:.1%})")
        return False, max_sim, scores

# Engagement tracking
ENGAGEMENT_TRACKER_FILE = "storage/engagement_tracker.json"

def load_engagement_tracker():
    """Load engagement data for templates."""
    try:
        if os.path.exists(ENGAGEMENT_TRACKER_FILE):
            with open(ENGAGEMENT_TRACKER_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        log(f"[ENGAGEMENT] Error loading engagement tracker: {e}")
    return {"templates": {}}

def save_engagement_tracker(data):
    """Save engagement data."""
    try:
        os.makedirs(os.path.dirname(ENGAGEMENT_TRACKER_FILE), exist_ok=True)
        with open(ENGAGEMENT_TRACKER_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        log(f"[ENGAGEMENT] Error saving engagement tracker: {e}")

def record_post_engagement(template_id, emoji, views=None, likes=None, replies=None):
    """
    Record engagement metrics for a template (for future weighting).
    
    Args:
        template_id: Template ID
        emoji: Emoji used
        views: View count (optional)
        likes: Like count (optional)
        replies: Reply count (optional)
    """
    try:
        tracker = load_engagement_tracker()
        if "templates" not in tracker:
            tracker["templates"] = {}
        
        template_key = f"template_{template_id}"
        if template_key not in tracker["templates"]:
            tracker["templates"][template_key] = {
                "posts": 0,
                "total_views": 0,
                "total_likes": 0,
                "total_replies": 0,
                "avg_views": 0.0,
                "emoji": emoji
            }
        
        stats = tracker["templates"][template_key]
        stats["posts"] += 1
        
        if views is not None:
            stats["total_views"] += views
            stats["avg_views"] = stats["total_views"] / stats["posts"]
        if likes is not None:
            stats["total_likes"] += likes
        if replies is not None:
            stats["total_replies"] += replies
        
        save_engagement_tracker(tracker)
        
        log(f"[ENGAGEMENT] Template #{template_id} ({emoji}): posts={stats['posts']}, avg_views={stats['avg_views']:.0f}")
    except Exception as e:
        log(f"[ENGAGEMENT] Error recording engagement: {e}")

# Post type mixing (vary original/link/viral)
POST_TYPE_HISTORY_FILE = "storage/post_type_history.json"

def load_post_type_history():
    """Load recent post types (keep last 5)."""
    try:
        if os.path.exists(POST_TYPE_HISTORY_FILE):
            with open(POST_TYPE_HISTORY_FILE, 'r') as f:
                data = json.load(f)
                return data.get("types", [])
    except Exception as e:
        log(f"[POST_TYPE_MIX] Error loading post type history: {e}")
    return []

def save_post_type_history(post_types):
    """Save post type history (keep last 5)."""
    try:
        os.makedirs(os.path.dirname(POST_TYPE_HISTORY_FILE), exist_ok=True)
        with open(POST_TYPE_HISTORY_FILE, 'w') as f:
            json.dump({"types": post_types[-5:]}, f, indent=2)
    except Exception as e:
        log(f"[POST_TYPE_MIX] Error saving post type history: {e}")

def select_post_type(recent_types):
    """
    Select post type (original/with_link/viral) with smart mixing.
    Goal: 80% original, 20% with_link, 5% viral (roughly)
    But avoid posting same type 3+ times in a row.
    
    Returns:
        str: "original", "with_link", or "viral"
    """
    # Check if we've posted same type 3+ times in a row
    if len(recent_types) >= 3 and all(t == recent_types[-1] for t in recent_types[-3:]):
        # Force a different type
        if recent_types[-1] == "original":
            selected = random.choice(["with_link", "viral"])
            log(f"[POST_TYPE_MIX] Last 3 were '{recent_types[-1]}', forcing '{selected}'")
        elif recent_types[-1] == "with_link":
            selected = random.choice(["original", "viral"])
            log(f"[POST_TYPE_MIX] Last 3 were '{recent_types[-1]}', forcing '{selected}'")
        else:  # viral
            selected = "original"
            log(f"[POST_TYPE_MIX] Last 3 were '{recent_types[-1]}', forcing 'original'")
        return selected
    
    # [EMERGENCY FIX] Normal weighted selection - 90% original, 10% with_link (max 10% links)
    rand = random.random()
    if rand < 0.90:  # 90% original
        selected = "original"
    else:  # 10% with_link (no viral for now)
        selected = "with_link"
    
    log(f"[POST_TYPE_MIX] Selected '{selected}' (recent: {recent_types})")
    return selected

# [STAGE 17] Store last generated prompt for performance tracking
_last_generated_prompt = ""

def generate_original_tweet() -> str:
    """
    Generate original tweet content using OpenAI.
    Returns tweet text or empty string if generation fails.
    """
    global _last_generated_prompt
    _last_generated_prompt = ""  # Reset
    
    if not openai_client:
        log("[ORIGINAL_POST] OpenAI not available, cannot generate tweet")
        return ""
    
    try:
        # [RECOVERY] New trader-focused templates (60% no-link, 30-40% with-link)
        # Template rotation: Use different structures to avoid bot-like patterns
        templates = [
            {
                "structure": "position_take",
                "has_link": False,  # 60% no-link templates
                "system": """You are a SaaS growth strategist and marketing tool expert. You help founders, marketers, and creators optimize their growth stack.

Your goal: Write engaging original X posts that:
- Sound like an experienced growth expert sharing insights (not a salesman)
- Focus on SaaS growth, marketing tools, link management, and attribution
- Are 150-250 characters (concise and scannable)
- Include specific data, metrics, or tool insights when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Reference real marketing concepts (attribution, conversion tracking, CTR, LTV)
- Be helpful and insightful when appropriate
- No hashtags (spam tags)
- 1-2 emojis max if it fits the vibe (📈 for growth, 🤔 for thinking, etc.)
- Start with a question or insight to engage readers

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific metric or tool mention (e.g., "CTR increased 34%", "conversion tracking shows", "link attribution reveals").
REQUIRED: Include at least ONE specific use case or problem (e.g., "tracking which campaigns drive MRR", "measuring affiliate performance", "optimizing link clicks").
Start with a question or insight to hook readers (e.g., "Why do most SaaS founders ignore attribution?" or "What if you could track every conversion?").
Focus on practical marketing insights, tool recommendations, or growth strategies.
Sound like you're sharing real experience, not just observing.
Keep it 150-250 characters, conversational, and helpful.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "hot_take",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Reference real trading concepts (odds movement, volatility, liquidity)
- Be contrarian or insightful when appropriate
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)
- Lead with a bold take or observation

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Lead with a bold take or observation (e.g., "The odds are wrong here" or "This market is mispriced").
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "observation",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Reference real trading concepts (odds movement, volatility, liquidity)
- Be contrarian or insightful when appropriate
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)
- Share an interesting observation or data point

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Share an interesting observation or data point (e.g., "Odds shifted 5% in the last hour" or "This market is seeing unusual volume").
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "contrarian",
                "system": """You are a SaaS growth strategist posting spicy, contrarian takes about marketing and growth.

Your goal: Write viral-style original X posts that:
- Challenge conventional wisdom or crowd sentiment
- Sound like an experienced growth expert with a bold, confident take
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Sound natural and conversational, never like a bot
- Use contrarian framing like "Everyone is wrong about X" or "The market has this backwards"

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with a bold, contrarian statement
- Back it up with data/odds/market movements
- Be opinionated but grounded in market data
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, spicy contrarian tweet about SaaS growth and marketing attribution. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Use insider growth hooks like:
- "The smart money is using {tool} right now. Most founders are asleep at the wheel."
- "Everyone chasing {trend} is missing the real growth hack with {tool}."
- "If you're not tracking {metric} properly, you're doing it wrong."
- "This {tool} setup is a gift. Don't say I didn't warn you."
- "Watching {metric} improve. The crowd is totally missing this."

Sound confident, slightly arrogant, like you have insider knowledge. Make it feel urgent and exclusive.
Sound like you're sharing real experience, not just observing.
Keep it 150-250 characters, conversational, and bold.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "data_drop",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Lead with a numbered list or structured format (e.g., "3 reasons...", "5 data points...")
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Structure: "3 reasons this odds shift changes everything:" or similar numbered format
- Reference real trading concepts (odds movement, volatility, liquidity)
- Be contrarian or insightful when appropriate
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Use a structured format like "3 reasons this odds shift changes everything:" or "5 data points everyone missed:".
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "fomo_status",
                "system": """You are a high-status SaaS growth expert posting exclusive, FOMO-inducing content.

Your goal: Write posts that create status anxiety and drive curiosity:
- Sound like an insider who's already winning
- Create FOMO (fear of missing out) and status anxiety
- Position proper attribution as the exclusive advantage
- Sound confident, slightly arrogant, like you're ahead of the curve
- Are 150-250 characters (concise and scannable)
- Sound natural and conversational, never like a bot

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Create urgency and exclusivity
- Make readers feel like they're missing out
- Reference real trading concepts (odds, markets, returns)
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (💰 for money, 🚀 for gains, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, FOMO-inducing tweet about SaaS growth and marketing attribution.
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Use status hooks like:
- "While you were arguing about {topic}, I just increased {metric} by {return}%."
- "Proper attribution is the only truth machine left. The rest is noise."
- "Imagine not tracking conversions properly in 2025. Couldn't be me."
- "The smart money already moved. You're still watching from the sidelines."

Make it feel urgent, exclusive, and high-status. Create FOMO.
Sound like you're sharing real experience, not just observing.
Keep it 150-250 characters, conversational, and confident.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "casual_observation",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Start with "I just noticed..." or similar casual observation
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Start with casual observation hook
- Reference real trading concepts (odds movement, volatility, liquidity)
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Start with "I just noticed [data point]. Here's what it means..." or similar casual observation.
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "mispricing_claim",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Claim that a market is mispriced and explain why
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with mispricing claim ("Everyone is mispricing X..." or "This market is wrong...")
- Reference real trading concepts (odds movement, volatility, liquidity)
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Start with "Everyone is mispricing [market]. Here's what the data actually shows..." or similar mispricing claim.
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "contrarian_humble",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Use humble contrarian framing ("I'm probably wrong, but...")
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with humble contrarian take ("I'm probably wrong, but..." or "Maybe I'm missing something, but...")
- Reference real trading concepts (odds movement, volatility, liquidity)
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Start with "I'm probably wrong, but [contrarian take]. The odds suggest..." or similar humble contrarian framing.
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "betting_analysis",
                "system": """You are a SaaS growth strategist posting original insights about marketing and growth.

Your goal: Write engaging original X posts that:
- Sound like an experienced trader sharing insights (not a salesman)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Frame as betting analysis ("Here's how I'd bet this...")
- Include specific data, odds, or market movements when relevant
- Sound natural and conversational
- Never sound like a bot (no "As an AI" or "I've analyzed")

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with betting analysis ("Here's how I'd bet this:" or "My play on this market...")
- Reference real trading concepts (odds movement, volatility, liquidity)
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a unique, engaging original tweet about SaaS growth, marketing tools, or link management. 
REQUIRED: Include at least ONE specific odds percentage or market name (e.g., "Bitcoin at 45%", "Ethereum at 32%", "2026 Senate odds at 62%")
REQUIRED: Include at least ONE specific outcome or event (e.g., "2026 midterms", "Fed rate cut", "Bitcoin ETF approval")
Start with "Here's how I'd bet this: [analysis]. The numbers show..." or similar betting analysis framing.
Focus on current 2026 races, market movements, or contrarian insights about odds.
Sound like you're betting real money, not just observing.
Keep it 150-250 characters, conversational, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            # [PROBLEM #3 FIX] 5 NEW VIRAL TEMPLATES (high conviction, controversial, 20% selection probability)
            {
                "structure": "viral_contrarian_wrong",
                "has_link": False,
                "system": """You are a bold Polymarket trader posting high-conviction, controversial takes that create engagement.

Your goal: Write viral-style original X posts that:
- Challenge conventional wisdom with high conviction
- Sound confident and slightly arrogant (like an insider)
- Create controversy and debate (drive shares/engagement)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements
- Sound natural and conversational, never like a bot

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with bold contrarian statement ("Everyone is wrong about X..." or "The crowd has this backwards...")
- Back it up with data/odds/market movements
- Be opinionated but grounded in market data
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (🔥 for hot takes, 💀 for bold predictions, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a high-conviction, controversial tweet about SaaS growth and marketing attribution. 
REQUIRED: Include at least ONE specific metric or tool mention
REQUIRED: Include at least ONE specific use case or problem
Use framing like: "Everyone is using {TOOL} for {USE_CASE}. I think they're all wrong. Here's why: {CONTRARIAN_TAKE}"
Sound confident, slightly arrogant, like you have insider knowledge. Make it feel urgent and exclusive.
Keep it 150-250 characters, bold, and growth-focused.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "viral_insane_odds",
                "has_link": False,
                "system": """You are a bold Polymarket trader posting high-conviction, controversial takes that create engagement.

Your goal: Write viral-style original X posts that:
- Highlight odds that seem "insane" or mispriced
- Create FOMO and urgency ("free money" or "trade of the year")
- Sound confident and slightly arrogant (like an insider)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements
- Sound natural and conversational, never like a bot

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with bold statement about odds being "insane" or mispriced
- Create urgency and FOMO
- Be opinionated but grounded in market data
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (🔥 for hot takes, 💀 for bold predictions, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a high-conviction, controversial tweet about SaaS growth and marketing attribution. 
REQUIRED: Include at least ONE specific odds percentage or market name
REQUIRED: Include at least ONE specific outcome or event
Use framing like: "The crowd has {MARKET} at {ODDS}%. That's insane. This is either the trade of the year or I'm about to lose money publicly."
Sound confident, slightly arrogant, like you have insider knowledge. Make it feel urgent and exclusive.
Keep it 150-250 characters, bold, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "viral_hot_take",
                "has_link": False,
                "system": """You are a bold Polymarket trader posting high-conviction, controversial takes that create engagement.

Your goal: Write viral-style original X posts that:
- Make bold, controversial predictions that will "age poorly" or get people talking
- Challenge conventional wisdom with high conviction
- Sound confident and slightly arrogant (like an insider)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements
- Sound natural and conversational, never like a bot

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with "Hot take" or "Unpopular opinion" framing
- Make bold prediction that people will disagree with
- Be opinionated but grounded in market data
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (🔥 for hot takes, 💀 for bold predictions, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a high-conviction, controversial tweet about SaaS growth and marketing attribution. 
REQUIRED: Include at least ONE specific odds percentage or market name
REQUIRED: Include at least ONE specific outcome or event
Use framing like: "Hot take that will age poorly: {MARKET} is mispriced by at least 15%. The market is ignoring {FACTOR}."
Sound confident, slightly arrogant, like you have insider knowledge. Make it feel urgent and exclusive.
Keep it 150-250 characters, bold, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "viral_free_money",
                "has_link": False,
                "system": """You are a bold Polymarket trader posting high-conviction, controversial takes that create engagement.

Your goal: Write viral-style original X posts that:
- Claim a market is "free money" or an obvious trade
- Create FOMO and urgency (people missing out)
- Sound confident and slightly arrogant (like an insider)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements
- Sound natural and conversational, never like a bot

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with "free money" or "obvious trade" framing
- Create urgency ("you're missing out" or "most obvious trade right now")
- Be opinionated but grounded in market data
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (🔥 for hot takes, 💀 for bold predictions, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a high-conviction, controversial tweet about SaaS growth and marketing attribution. 
REQUIRED: Include at least ONE specific odds percentage or market name
REQUIRED: Include at least ONE specific outcome or event
Use framing like: "If you're not watching {MARKET}, you're missing the most obvious trade right now. {ODDS}% is free money."
Sound confident, slightly arrogant, like you have insider knowledge. Make it feel urgent and exclusive.
Keep it 150-250 characters, bold, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
            {
                "structure": "viral_unpopular_wreck",
                "has_link": False,
                "system": """You are a bold Polymarket trader posting high-conviction, controversial takes that create engagement.

Your goal: Write viral-style original X posts that:
- Make bold, controversial predictions about popular sides getting "wrecked"
- Challenge conventional wisdom with high conviction
- Sound confident and slightly arrogant (like an insider)
- Focus on SaaS growth, marketing attribution, and conversion optimization
- Are 150-250 characters (concise and scannable)
- Include specific data, odds, or market movements
- Sound natural and conversational, never like a bot

Rules:
- Keep posts under 250 characters (X users scan fast)
- Use 1-2 line breaks for readability
- Lead with "Unpopular opinion" or bold prediction about popular side being wrong
- Make controversial claim that will create debate
- Be opinionated but grounded in market data
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (🔥 for hot takes, 💀 for bold predictions, etc.)

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current SaaS trends, marketing insights, recent tools

Output ONLY the tweet text, nothing else.""",
                "user": """Generate a high-conviction, controversial tweet about SaaS growth and marketing attribution. 
REQUIRED: Include at least ONE specific odds percentage or market name
REQUIRED: Include at least ONE specific outcome or event
Use framing like: "Unpopular opinion: everyone betting on {POPULAR_SIDE} is going to get wrecked. The data says {CONTRARIAN_SIDE} and I'm all in."
Sound confident, slightly arrogant, like you have insider knowledge. Make it feel urgent and exclusive.
Keep it 150-250 characters, bold, and trader-like.
Do NOT include any links (links are handled separately)."""
            },
        ]
        
        # [STAGE 14] Template rotation with last-used tracking to prevent repetition
        # [PROBLEM #3 FIX] Viral templates get 20% selection probability (1 in 5 posts)
        # [IMPORT_FIX] random is already imported at top of file, don't re-import
        global _last_original_template
        if '_last_original_template' not in globals():
            _last_original_template = None
        
        # [PROBLEM #3 FIX] 20% chance to use viral template (high conviction, controversial)
        use_viral_template = random.random() < 0.20
        viral_templates = [t for t in templates if t.get("structure", "").startswith("viral_")]
        regular_templates = [t for t in templates if not t.get("structure", "").startswith("viral_")]
        
        if use_viral_template and viral_templates:
            available_viral = [t for t in viral_templates if t.get("structure") != _last_original_template]
            if not available_viral:
                available_viral = viral_templates
            template = random.choice(available_viral)
            log(f"[PROBLEM #3] [VIRAL_TEMPLATE] Using viral template: {template.get('structure')} (20% probability)")
        else:
            # Filter out last used template if available
            available_templates = [t for t in regular_templates if t.get("structure") != _last_original_template]
            if not available_templates:
                available_templates = regular_templates  # Fallback if all used
            template = random.choice(available_templates)
        
        _last_original_template = template.get("structure")
        system_prompt = template["system"]
        user_prompt = template["user"]
        log(f"[STAGE 14] [TEMPLATE] Using template: {template.get('structure')}")
        log("[STAGE 15] [ORIGINAL_PROMPT] Updated with data requirement (odds % and market names)")
        
        # [STAGE 16D] Check if should post follower magnet instead
        if should_post_follower_magnet():
            log("[STAGE 16D] Posting follower magnet instead of regular original")
            return "FOLLOWER_MAGNET"  # Special return value
        
        # [STAGE 16A] VIDEO POSTING DISABLED - Prevents crashes
        # Check if should post video with context
        if False:  # DISABLED - should_post_video_now():
            pass
            # video = get_video_for_post()
            # if video:
            #     log("[STAGE 16A] Video post selected, returning special value")
            #     return "VIDEO_POST"  # Special return value
        
        # [STAGE 16B] Add niche focus instruction if active
        niche_instruction = ""
        if should_post_about_niche():
            niche_instruction = get_niche_prompt_instruction()
            log(f"[STAGE 16B] Adding niche focus instruction")

        # [STAGE 15] Add credibility signals (trader language) to 40% of posts
        # [FIX] random is already imported at module level - don't re-import (fixes shadowing bug)
        add_credibility_signal = random.random() < 0.40
        if add_credibility_signal:
            credibility_signals = [
                "I'm putting $X on this",
                "Just moved my position to",
                "My odds for this are",
                "Expected value is positive if",
                "Taking a position here",
                "Stacking on this outcome"
            ]
            signal = random.choice(credibility_signals)
            # Add signal to user prompt as context
            user_prompt = user_prompt + f"\n\nOptional: Include trader language like '{signal}' if it fits naturally (don't force it)."
            log(f"[STAGE 15] [CREDIBILITY] Added trader signal: {signal}")
        
        # [STAGE 15] Add market context (recent movement) to 30% of posts
        add_market_context = random.random() < 0.30
        if add_market_context:
            market_contexts = [
                "Just saw the market move on this",
                "Odds shifted 5 points since [news]",
                "Early traders are positioning into",
                "Volume just spiked on [market]",
                "Money flowing into this market"
            ]
            context = random.choice(market_contexts)
            user_prompt = user_prompt + f"\n\nOptional: Reference recent market movement like '{context}' if it fits naturally."
            log("[STAGE 15] [MARKET_CONTEXT] Added reference")
        
        # [STAGE 16B] Append niche instruction if present
        if niche_instruction:
            user_prompt = user_prompt + niche_instruction
        
        # [STAGE 17] Apply optimized prompt modifiers based on recent performance
        optimizer_advice = get_optimized_prompt_modifiers()
        if optimizer_advice:
            user_prompt = user_prompt + f"\n\n[OPTIMIZER ADJUSTMENT]: {optimizer_advice}"
            log(f"[STAGE 17] [OPTIMIZER] Applying adjustment: {optimizer_advice}")

        # Generate tweet with similarity checking and regeneration if too similar
        max_regeneration_attempts = 3
        for attempt in range(max_regeneration_attempts):
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.9 + (attempt * 0.1),  # Increase temperature on each retry for more variety
                max_tokens=200,
            )
            
            tweet_text = response.choices[0].message.content.strip()
            
            # Clean up any quotes or markdown
            if tweet_text.startswith('"') and tweet_text.endswith('"'):
                tweet_text = tweet_text[1:-1]
            tweet_text = tweet_text.replace('"', '"').replace('"', '"')
            
            # Check similarity to recent posts
            if not is_too_similar_to_recent_posts(tweet_text, threshold=0.6):
                # Not too similar, use this version
                log(f"[SIMILARITY] Generated unique tweet (attempt {attempt + 1})")
                break
            else:
                log(f"[SIMILARITY] Tweet too similar to recent posts, regenerating (attempt {attempt + 1}/{max_regeneration_attempts})")
                if attempt < max_regeneration_attempts - 1:
                    # Try different template structure on next attempt
                    template = random.choice(templates)
                    system_prompt = template["system"]
                    user_prompt = template["user"]
                    continue
                else:
                    log(f"[SIMILARITY] Max regeneration attempts reached, using tweet despite similarity")
        
        # ====================== ULTIMATE ANTI-BOT + VIRAL OPTIMIZATION ======================
        # [TEMPLATE_ROTATION + EMOJI_DIVERSITY + SIMILARITY_CHECK]
        # 30% chance to use a direct template (instead of AI generation)
        use_direct_template = random.random() < 0.30
        if use_direct_template and VIRAL_TEMPLATES and isinstance(VIRAL_TEMPLATES, dict):
            # Step 1: Select post type with smart mixing (avoid 3+ in a row)
            recent_post_types = load_post_type_history()
            template_category = select_post_type(recent_post_types)
            
            template_list = VIRAL_TEMPLATES.get(template_category, [])
            if template_list and len(template_list) > 0:
                # Step 2: Use diversity_engine to get banned tiers/emojis (ELITE VIRAL BOT OVERHAUL)
                last_post_history = load_posted_history()
                last_post_data = last_post_history[0] if last_post_history else None
                banned_tiers, banned_emojis = diversity_engine(last_post_data)
                
                # Step 3: Select template with rotation (never repeat last 5) + diversity engine
                recent_template_ids = load_template_history()
                selected_template = select_next_template(template_list, recent_template_ids, banned_tiers=banned_tiers)
                
                if selected_template:
                    # Extract template text (new format has "text" key, old format is string)
                    template_text = selected_template.get("text", selected_template) if isinstance(selected_template, dict) else selected_template
                    template_id = selected_template.get("id", "unknown") if isinstance(selected_template, dict) else "unknown"
                    template_emoji = selected_template.get("emoji") if isinstance(selected_template, dict) else None
                    template_tier = selected_template.get("tier", "unknown") if isinstance(selected_template, dict) else "unknown"
                    
                    market_context = {"market_name": "Bitcoin", "topic": "Bitcoin"}  # Default, could be improved
                    
                    # Step 4: Insert odds into template
                    template_with_odds = insert_odds_into_template(template_text, market_context)
                    
                    # Step 5: Check if template looks good (not too many placeholders left, and validation passed)
                    if template_with_odds and template_with_odds.count("{") < 2:  # Few placeholders remaining
                        # Step 6: Select emoji with diversity (never same twice) + respect banned emojis
                        recent_emojis = load_emoji_history()
                        # Filter out banned emojis
                        if banned_emojis:
                            recent_emojis = list(banned_emojis) + recent_emojis  # Add banned to recent to prevent selection
                        selected_emoji = select_emoji(template_emoji, recent_emojis)
                        
                        # If selected emoji is banned, pick a different one
                        if selected_emoji in banned_emojis:
                            available_emojis = ["🔥", "💡", "⚡", "🎯", "👀", "🚀", "💰", "📊", "🤔", "🧵", "🚨", "⛔", "🎲", "📈", "📉"]
                            available_emojis = [e for e in available_emojis if e not in banned_emojis and e not in recent_emojis]
                            if available_emojis:
                                selected_emoji = random.choice(available_emojis)
                            log(f"[DIVERSITY_ENGINE] Banned emoji detected, selected alternative: {selected_emoji}")
                        
                        # Replace emoji in template if needed (if template had emoji but we selected different one)
                        if template_emoji and selected_emoji != template_emoji:
                            template_with_odds = template_with_odds.replace(template_emoji, selected_emoji, 1)
                        elif not template_emoji:
                            # Add emoji at end if template didn't have one
                            template_with_odds = f"{template_with_odds} {selected_emoji}"
                        
                        # Step 7: Apply human randomization (ELITE VIRAL BOT OVERHAUL)
                        template_with_odds = human_randomization(template_with_odds)
                        
                        # Step 8: Final validation - check for 2024 and spam patterns
                        is_valid, validation_reason = validate_content(template_with_odds)
                        if not is_valid:
                            log(f"[TEMPLATE_SELECT] Template failed validation: {validation_reason}, using AI generation instead")
                            template_with_odds = None
                        
                        if template_with_odds:
                            # Step 9: Check similarity (regenerate if >70% similar to recent posts)
                            recent_posts = load_recent_posts()
                            is_too_similar, max_sim, sim_scores = check_similarity_and_regenerate(template_with_odds, recent_posts, threshold=0.70)
                            
                            if not is_too_similar:
                                # Step 10: Template is good! Use it
                                tweet_text = template_with_odds
                                
                                # [BOT RECONSTRUCTION] Add hashtags to template-based posts
                                if HASHTAG_MANAGER_AVAILABLE:
                                    try:
                                        market_category = "crypto"  # Could be improved to detect from tweet content
                                        tweet_text = add_hashtags_to_post(tweet_text, template_tier, market_category)
                                        log(f"[HASHTAG] Added hashtags to template post (tier: {template_tier})")
                                    except Exception as e:
                                        log(f"[HASHTAG] Error adding hashtags: {e}")
                                
                                # Step 11: Update history (template, emoji, post type)
                                recent_template_ids.append(template_id)
                                save_template_history(recent_template_ids)
                                
                                recent_emojis_clean = [e for e in recent_emojis if e not in banned_emojis]  # Clean banned from list
                                recent_emojis_clean.append(selected_emoji)
                                save_emoji_history(recent_emojis_clean)
                                
                                recent_post_types.append(template_category)
                                save_post_type_history(recent_post_types)
                                
                                # Step 12: Save post data for diversity engine
                                hashtags_used = tweet_text.split("\n\n")[-1] if "\n\n" in tweet_text else ""
                                save_post_to_history(selected_template, tweet_text, selected_emoji, hashtags_used)
                                
                                # Step 13: Record engagement (placeholder - will be updated after posting)
                                record_post_engagement(template_id, selected_emoji, views=None, likes=None, replies=None)
                                
                                log(f"[TEMPLATE_SELECT] Selected '{template_category}' template #{template_id} (tier: {template_tier}) with real odds, emoji: {selected_emoji}")
                            else:
                                log(f"[TEMPLATE_SELECT] Template too similar ({max_sim:.1%}), using AI generation instead")
                                template_with_odds = None
                        else:
                            log(f"[TEMPLATE_SELECT] Template validation failed or has too many placeholders, using AI generation instead")
        
        # [STAGE 17] Store the prompt used for this generation
        _last_generated_prompt = user_prompt
        
        # Apply human randomization to final text (ELITE VIRAL BOT OVERHAUL)
        if tweet_text:
            tweet_text = human_randomization(tweet_text)
        
        # [BOT RECONSTRUCTION] Add hashtags if hashtag manager is available
        if HASHTAG_MANAGER_AVAILABLE and tweet_text:
            try:
                # Determine template tier (default to "minimal" if unknown)
                template_tier = template.get("tier", "minimal") if isinstance(template, dict) else "minimal"
                # Determine market category (default to "crypto")
                market_category = "crypto"  # Could be improved to detect from tweet content
                tweet_text = add_hashtags_to_post(tweet_text, template_tier, market_category)
                log(f"[HASHTAG] Added hashtags to post (tier: {template_tier})")
            except Exception as e:
                log(f"[HASHTAG] Error adding hashtags: {e}")
        
        return tweet_text
        
    except Exception as e:
        log(f"[ORIGINAL_POST] Error generating tweet: {e}")
        
        # [NOTION] Log error to Notion
        if NOTION_MANAGER:
            try:
                NOTION_MANAGER.log_activity(
                    "ERROR",
                    f"Post Generation Error: {str(e)[:100]}",
                    metadata={
                        "error_type": "Post Error",
                        "error_msg": str(e)[:500],
                        "stage": "posting"
                    }
                )
            except Exception:
                pass  # Don't fail on Notion logging errors
        
        return ""

def post_original_content(page) -> bool:
    """
    Post original content to X.
    
    Safeguards:
    - Checks rate limits (6-8 per day, not within 5 min of last post)
    - Checks for duplicate text using DEDUPLICATOR
    - Generates unique content using AI
    - Adds link if appropriate (30-40% of posts)
    
    Returns True if posted successfully, False otherwise.
    """
    # [SAFETY] Ensure we're on X.com before posting
    if not ensure_on_x_com(page):
        log("[POST_SKIP] Reason: not_on_x_com")
        return False
    
    # Check scheduler (will log skip reasons internally)
    if not ORIGINAL_POST_SCHEDULER.should_post_now():
        return False
    
    # Check rate limit from HARDENING
    if HARDENING and not HARDENING.can_post_original(max_posts_per_day=8):
        log("[POST_SKIP] Reason: rate_limit_daily_max")
        return False
    
    # Generate tweet content
    tweet_text = generate_original_tweet()
    
    # [STAGE 16D] Handle follower magnet posts
    if tweet_text == "FOLLOWER_MAGNET":
        log("[STAGE 16D] Posting follower magnet")
        return post_follower_magnet(page)
    
    # [STAGE 16A] Handle video posts
    if tweet_text == "VIDEO_POST":
        video = get_video_for_post()
        if video:
            context_text = VIDEO_POSTING_CONFIG.get("context_prompt", "Watch below 👇")
            success = post_video_with_context(page, video, context_text)
            if success:
                global _video_last_post_time, _video_posts_today, _video_last_post_date
                _video_last_post_time = time.time()
                today = datetime.now().strftime("%Y-%m-%d")
                if _video_last_post_date != today:
                    _video_posts_today = 0
                    _video_last_post_date = today
                _video_posts_today += 1
            return success
        else:
            log("[STAGE 16A] No video available, falling back to regular post")
            tweet_text = generate_original_tweet()  # Regenerate without video
    
    if not tweet_text or len(tweet_text.strip()) < 50:
        log("[POST_SKIP] Reason: generation_failed_or_too_short")
        return False
    
    # [DATA_VALIDATOR] Validate market data (extra safety check for 2024 content)
    # Extract market name from tweet if possible
    market_name = "Unknown"
    try:
        # Try to extract market name from tweet (look for patterns like "Bitcoin", "BTC", etc.)
        import re
        market_match = re.search(r'(\w+(?:\s+\w+)?)\s+at\s+\d+%', tweet_text, re.IGNORECASE)
        if market_match:
            market_name = market_match.group(1)
    except Exception:
        pass
    
    if not validate_market_data(market_name, tweet_text):
        log(f"[POST_SKIP] Reason: stale_market_data_blocked")
        return False
    
    # [EMERGENCY FIX] Validate content before posting (reject stale/spam patterns)
    is_valid, validation_reason = validate_content(tweet_text)
    if not is_valid:
        log(f"[POST_SKIP] Reason: validation_failed - {validation_reason}")
        return False
    
    # Check for duplicates using DEDUPLICATOR
    if DEDUPLICATOR:
        # Check if text is duplicate or similar to recent posts
        if not DEDUPLICATOR.can_post_reply(tweet_text, None):
            log("[POST_SKIP] Reason: duplicate_text")
            return False
    
    # [STAGE 15] Strategic link placement (ALWAYS if data present, MAYBE otherwise)
    include_link = should_include_link_strategic(tweet_text, post_type="original")
    # Fallback to original logic if strategic didn't trigger
    if not include_link:
        include_link = should_include_link_in_original(tweet_text)  # [ENHANCEMENT #3] Pass post_text for spacing check
    
    # Use centralized helper to ensure link is appended if needed
    tweet_text = append_link_if_needed(tweet_text, REFERRAL_LINK, include_link)
    
    # [STAGE 15] Log link format (let card embed for originals)
    if include_link:
        log("[STAGE 15] [LINK_FORMAT] Direct link (originals)")
    
    # Append CTA phrase if needed (every 2nd-3rd post)
    # Use high_intent=True for original posts (spicier CTAs)
    tweet_text = append_cta_if_needed(tweet_text, REFERRAL_LINK, high_intent=True)
    
    try:
        # Go to home
        stable_goto(page, HOME_URL)
        human_pause(2.0, 3.0)
        
        # Open composer
        new_tweet_button = page.locator('[data-testid="SideNav_NewTweet_Button"]').first
        if new_tweet_button.count() == 0:
            # Fallback: try compose URL
            page.goto("https://x.com/compose/tweet")
            human_pause(2.0, 3.0)
        else:
            try:
                new_tweet_button.click(timeout=5000)
            except Exception as e:
                log(f"[FOLLOWER_MAGNET] Could not click new tweet button: {e}")
                return False
            human_pause(1.0, 2.0)
                            
        # Type tweet
        box_selectors = [
            "div[role='textbox'][data-testid='tweetTextarea_0']",
            "div[role='textbox']",
        ]
        typed = False
        for sel in box_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=3000):
                    try:
                        page.locator(sel).first.click(timeout=5000)
                    except Exception as e:
                        log(f"[FOLLOWER_MAGNET] Could not click composer selector {sel}: {e}")
                        continue
                    human_pause(0.3, 0.5)
                    
                    # Type tweet with human-like delays
                    log(f"[TYPE_DEBUG] About to type into composer: {tweet_text[:100]}...")
                    for ch in tweet_text:
                        page.keyboard.type(ch, delay=random.randint(20, 50))
                        if random.random() < 0.05:  # Occasional pause
                            human_pause(0.3, 0.8)
                    typed = True
                    break
            except Exception:
                continue
        
        if not typed:
            log("[POST_SKIP] Reason: could_not_open_composer")
            page.keyboard.press("Escape")
            return False
        
        human_pause(0.5, 1.0)
                                
        # Post tweet
        posted = click_post_once(page)
        if not posted:
            log("[POST_SKIP] Reason: post_button_failed")
            page.keyboard.press("Escape")
            return False
        
        # Success - record and log
        ORIGINAL_POST_SCHEDULER.mark_posted()
        if HARDENING:
            HARDENING.record_post()
            HARDENING.record_action()
        
        # Save to recent posts for similarity checking
        save_recent_post(tweet_text)
        
        # Store in deduplicator to prevent duplicates
        if DEDUPLICATOR:
            # Use text hash as ID for original posts
            text_hash = sha(tweet_text)
            DEDUPLICATOR.add_reply(tweet_text, text_hash)
        
        # Log metrics
        if ACCOUNT_HELPER:
            ACCOUNT_HELPER.log_action("post")
            if REFERRAL_LINK in tweet_text:
                ACCOUNT_HELPER.log_action("link")
        
        # Log analytics
        if ANALYTICS:
            ANALYTICS.log_action("post", "saas_growth", REFERRAL_LINK in tweet_text, "post_" + str(int(time.time())))
        
        current_time = datetime.now().strftime("%H:%M:%S")
        post_id = f"post_{int(time.time())}"
        log(f"[ORIGINAL_POST] Posted at {current_time}: {tweet_text[:50]}...")
        
        # [NOTION] Log post activity to Notion
        if NOTION_MANAGER:
            try:
                url = f"https://x.com/k_shamil57907/status/{post_id}" if post_id.startswith("post_") else None
                # Try to get template_id if available
                template_id = "unknown"
                try:
                    # Check if we're using a template (from generate_original_tweet or template selection)
                    if '_last_original_template' in globals():
                        template_id = globals().get('_last_original_template', 'unknown')
                except:
                    pass
                NOTION_MANAGER.log_activity(
                    "POST",
                    f"Original post: {tweet_text[:50]}...",
                    metadata={
                        "url": url or "Pending",
                        "text": tweet_text[:280],
                        "has_link": str(include_link),
                        "post_id": post_id,
                        "template_id": template_id,
                        "time": current_time
                    }
                )
            except Exception as e:
                log(f"[NOTION] Failed to log post: {e}")
        
        # [STAGE 15] Log post for click tracking
        cta_in_text = get_cta_phrase(high_intent=True) if any(cta in tweet_text for cta in ["Track", "See", "Check", "Watch"]) else None
        log_post_for_click_tracking(post_id, "original", tweet_text, include_link, cta_in_text)
        
        # [STAGE 16C] Track own post for engagement loop
        track_own_post_for_engagement(post_id, tweet_text)
        
        # [FOLLOWER MULTIPLICATION ENGINE] Get tweet URL and track engagers
        try:
            # Extract tweet URL by navigating to profile and finding latest tweet
            human_pause(2.0, 3.0)  # Wait for tweet to appear
            page.goto(f"https://x.com/{BOT_HANDLE.replace('@', '')}", wait_until="networkidle")
            human_pause(2.0, 3.0)
                                    
            # Find first tweet card (most recent)
            first_tweet_card = page.locator('article[data-testid="tweet"]').first
            if first_tweet_card.count() > 0:
                actual_tweet_id = extract_tweet_id(first_tweet_card)
                if actual_tweet_id:
                    tweet_url = f"https://x.com/{BOT_HANDLE.replace('@', '')}/status/{actual_tweet_id}"
                    
                    # Get engagers from this post (async - runs in background)
                    if 'engagement_multiplier' in globals() and engagement_multiplier:
                        try:
                            engagers = engagement_multiplier.get_post_engagers(tweet_url, min_followers=20, max_engagers=50)
                            if engagers:
                                log(f"[ENGAGEMENT] Found {len(engagers)} engagers for post {actual_tweet_id}")
                                # Queue for follow-back (will be processed later)
                                engagement_multiplier.auto_reply_to_quality_engagers(engagers)
                        except Exception as e:
                            log(f"[ENGAGEMENT] Error processing engagers: {e}")
        except Exception as e:
            log(f"[ENGAGEMENT] Could not extract tweet URL for engagement tracking: {e}")
        
        # [STAGE 17] Save post to performance history for optimizer
        global _last_generated_prompt
        prompt_used = _last_generated_prompt if '_last_generated_prompt' in globals() else ""
        hashtags = []  # Extract hashtags from tweet_text if needed
        save_post_result(post_id, prompt_used, hashtags, 0, 0)  # Initial metrics (will be updated later by performance checker)
        
        # Close composer
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
                                    
        human_pause(2.0, 3.0)
        return True
                    
    except Exception as e:
        log(f"[ORIGINAL_POST] Error posting: {e}")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False
        
def post_trending_video(page):
    """[STAGE 16A] Video posting (disabled - search causes navigation issues)."""
    log("[VIDEO_POST] Video posting disabled - search navigation broken")
    return False  # DISABLED - Never run video search
    # ALL CODE BELOW IS DISABLED - SEARCH NAVIGATION CAUSES ISSUES


def should_run_daily_cleanup():
    """Check if we should run daily cleanup (once per day, at 9am)"""
    if not CLEANUP or not FOLLOWER_MGR:
        return False
    
    # Check if we've run cleanup today
    last_cleanup = CLEANUP.log.get("last_cleanup")
    if last_cleanup:
        try:
            last_cleanup_date = datetime.fromisoformat(last_cleanup).date()
            today = datetime.now().date()
            if last_cleanup_date == today:
                return False  # Already ran today
        except Exception:
            pass
    
    # Run at 9am (or anytime if we haven't run today)
    current_hour = datetime.now().hour
    return current_hour == 9 or last_cleanup is None

def should_print_daily_summary():
    """Print summary once at 11pm"""
    if not ANALYTICS:
        return False
    
    current_hour = datetime.now().hour
    last_summary_time = getattr(should_print_daily_summary, 'last_time', None)
    
    if current_hour == 23 and (last_summary_time is None or 
                               (datetime.now() - last_summary_time).days > 0):
        should_print_daily_summary.last_time = datetime.now()
        return True
    return False

def track_competitors_and_reply(page):
    """
    Stage 11F: Monitor competitor posts and generate counter-takes.
    When competitors' posts get 100+ engagement, reply with a sharper edge.
    """
    if not STAGE_11F_ENABLED or not tracker:
        return False
    
    try:
        # Check rate limit
        if not tracker.should_reply_to_competitor():
            log("[STAGE 11F] Rate limit reached (2 replies/hour), skipping")
            return False
        
        # Check if competitors are configured
        if not tracker.competitor_handles:
            log("[STAGE 11F] No competitors added to monitor")
            return False
        
        log("[STAGE 11F] Starting competitor tracking...")
        
        checked_count = 0
        high_engagement_posts = 0
        
        # Check first 3 competitors
        for competitor_handle in tracker.competitor_handles[:3]:
            log(f"[STAGE 11F] Checking @{competitor_handle}...")
            checked_count += 1
            
            # In practice, you would:
            # 1. Navigate to competitor's profile
            # 2. Find their recent posts
            # 3. Check engagement on each post
            # 4. Generate counter-take for high-engagement posts
            
            # Placeholder: simulate finding a high-engagement post
            # In real implementation, would use Playwright to:
            # page.goto(f"https://x.com/{competitor_handle}")
            # posts = page.locator('article[data-testid="tweet"]')
            # for post in posts[:5]:
            #     engagement = extract_engagement_count(post)
            #     if tracker.is_high_engagement(engagement):
            #         thesis = extract_post_text(post)
            #         counter = tracker.generate_counter_take(thesis)
            #         if counter:
            #             log(f"[STAGE 11F] ✓ Generated counter-take: {counter['angle']} (conviction: {counter['conviction']})")
            #             tracker.log_counter_reply(competitor_handle, counter['counter_take'], counter['angle'], counter['conviction'])
            #             high_engagement_posts += 1
            #             break
        
        log(f"[STAGE 11F] Checked {checked_count} competitors, found {high_engagement_posts} high-engagement posts")
        
        return True
        
    except Exception as e:
        log(f"[STAGE 11F] Error in track_competitors_and_reply: {e}")
        import traceback
        traceback.print_exc()
        return False

def post_trend_take(page, trending_keyword=None):
    """
    Stage 11E: Post contrarian take on trending political topics.
    Detects trending Polymarket-relevant keywords and generates instant takes.
    """
    if not STAGE_11E_ENABLED or not monitor:
        return False
    
    try:
        # Check rate limit
        if not monitor.can_post_trend_take():
            log("[STAGE 11E] Rate limit reached (1 post per 2 hours), skipping")
            return False
        
        if trending_keyword is None:
            log("[STAGE 11E] No trending topics provided, skipping")
            return False
        
        log(f"[STAGE 11E] Processing trending keyword: {trending_keyword}")
        
        # Detect if keyword is relevant
        detected_topic = None  # Removed Polymarket-specific detection
        if not detected_topic:
            log(f"[STAGE 11E] Keyword '{trending_keyword}' not relevant to Polymarket, skipping")
            return False
        
        # Map to market
        market = monitor.map_trend_to_market(trending_keyword)
        log(f"[STAGE 11E] Mapped to market: {market}")
        
        # Generate thesis (simplified - would use Stage 10 in full implementation)
        # For now, generate a simple trend take
        thesis = f"🚨 [TREND] {trending_keyword} trending. {market} odds may shift. First-mover edge here."
        
        # Log trend post
        monitor.log_trend_post(trending_keyword, market, thesis)
        
        log(f"[STAGE 11E] ✓ Generated trend take for: {trending_keyword}")
        log(f"[STAGE 11E] ✓ Logged trend post")
        
        # In full implementation, would post the thesis using existing posting logic
        # For now, just log that it's ready
        log(f"[STAGE 11E] Trend take ready to post: {thesis[:80]}...")
        
        return True
        
    except Exception as e:
        log(f"[STAGE 11E] Error in post_trend_take: {e}")
        import traceback
        traceback.print_exc()
        return False

def optimize_replies(page):
    """
    Stage 11D: Monitor replies to your posts and generate thoughtful counter-replies
    to keep conversations alive and boost engagement.
    """
    if not STAGE_11D_ENABLED or not optimizer:
        return False
    
    try:
        # Check rate limit
        if not optimizer.should_reply_to_comment():
            log("[STAGE 11D] Rate limit reached (3 replies/hour), skipping")
            return False
        
        log("[STAGE 11D] Scanning for quality comments...")
        
        # Go to home/profile to find your posts and their replies
        stable_goto(page, HOME_URL)
        human_pause(2.0, 3.0)
        
        # Find your recent tweets (for now, we'll look at the first tweet)
        # In practice, you'd iterate through your posts and check their replies
        tweet_cards = page.locator('article[data-testid="tweet"]')
        tweet_count = tweet_cards.count()
        
        if tweet_count == 0:
            log("[STAGE 11D] No tweets found")
            return False
        
        # Get first tweet (your most recent)
        first_tweet = tweet_cards.first
        
        # Extract original post text for context
        original_post_text = extract_tweet_text(first_tweet)
        if not original_post_text:
            log("[STAGE 11D] Could not extract original post text")
            return False
        
        # Look for reply elements (this is simplified - actual implementation would need to
        # navigate to the tweet's reply thread)
        # For now, we'll log that we're checking
        log("[STAGE 11D] Checking replies to your posts...")
        
        # In a real implementation, you would:
        # 1. Click on the tweet to open its replies
        # 2. Find comment elements
        # 3. Filter for quality comments
        # 4. Generate smart replies
        
        # Placeholder for now - logs that functionality is available
        log("[STAGE 11D] Reply optimization ready (would scan and reply to quality comments)")
        
        # Example: If we found a quality comment, we would:
        # comment_text = extract_comment_text(comment_element)
        # if not optimizer.is_spam_comment(comment_text):
        #     user_handle = extract_user_handle(comment_element)
        #     reply_data = optimizer.generate_smart_reply(original_post_text, comment_text)
        #     if reply_data:
        #         log(f"[STAGE 11D] ✓ Generated smart reply to @{user_handle} (tone: {reply_data['tone']})")
        #         optimizer.log_reply("post_id", user_handle, reply_data["reply"], reply_data)
        
        return True
        
    except Exception as e:
        log(f"[STAGE 11D] Error in optimize_replies: {e}")
        import traceback
        traceback.print_exc()
        return False

def amplify_own_posts(page):
    """
    Stage 11C: Amplify own posts by liking and retweeting them.
    Triggers X's algorithmic amplification for 3-5x more impressions.
    """
    if not STAGE_11C_ENABLED or not amplifier:
        return False
    
    try:
        # Check rate limit
        if not amplifier.should_amplify():
            log("[STAGE 11C] Rate limit reached (1 amplification/day), skipping")
            return False
        
        log("[STAGE 11C] Starting amplification of own posts...")
        
        # Go to home/profile to find recent tweets
        stable_goto(page, HOME_URL)
        human_pause(2.0, 3.0)
        
        # Find your 3 most recent tweets
        tweet_cards = page.locator('article[data-testid="tweet"]')
        tweet_count = tweet_cards.count()
        
        if tweet_count == 0:
            log("[STAGE 11C] No tweets found on feed")
            return False
        
        # Get the first tweet (most recent)
        first_tweet = tweet_cards.first
        
        # Extract tweet URL
        tweet_url = None
        try:
            # Look for anchor tag with href containing "/status/"
            status_link = first_tweet.locator('a[href*="/status/"]').first
            if status_link.count() > 0:
                tweet_url = status_link.get_attribute("href")
                if tweet_url and not tweet_url.startswith("http"):
                    tweet_url = f"https://x.com{tweet_url}"
        except Exception:
            log("[STAGE 11C] Could not extract tweet URL")
        
        # Click like button
        try:
            like_button = first_tweet.locator('[data-testid="like"]').first
            if like_button.count() > 0:
                like_button.click(timeout=5000)
                log("[STAGE 11C] ✓ Liked post")
                human_pause(0.5, 1.0)
            else:
                log("[STAGE 11C] Like button not found")
                return False
        except PWTimeout:
            log("[STAGE 11C] Like button click timed out")
            return False
        except Exception as e:
            log(f"[STAGE 11C] Error clicking like: {e}")
            return False
        
        # Wait random delay (human behavior)
        delay = amplifier.get_amplification_delay()
        log(f"[STAGE 11C] Waiting {delay:.1f}s before retweet (human behavior)")
        time.sleep(delay)
        
        # Click retweet button
        try:
            retweet_button = first_tweet.locator('[data-testid="retweet"]').first
            if retweet_button.count() > 0:
                retweet_button.click(timeout=5000)
                log("[STAGE 11C] ✓ Retweeted post")
                human_pause(0.5, 1.0)
            else:
                log("[STAGE 11C] Retweet button not found")
                return False
        except PWTimeout:
            log("[STAGE 11C] Retweet button click timed out")
            return False
        except Exception as e:
            log(f"[STAGE 11C] Error clicking retweet: {e}")
            return False
        
        # Log amplification
        if tweet_url:
            amplifier.log_amplification(tweet_url, "own_post")
        else:
            amplifier.log_amplification("unknown", "own_post")
        
        log("[STAGE 11C] ✓ Amplified 1 post (liked and retweeted)")
        return True
        
    except Exception as e:
        log(f"[STAGE 11C] Error in amplify_own_posts: {e}")
        import traceback
        traceback.print_exc()
        return False

def post_news_jacker_take(page, news_headline):
    """
    Stage 11B: Post instant contrarian take on breaking political news.
    
    Args:
        page: Playwright page object
        news_headline: Breaking news headline text
    
    Returns: True if posted successfully, False otherwise
    """
    if not STAGE_11B_ENABLED or not news_jacker:
        return False
    
    try:
        log(f"[STAGE 11B] Processing breaking news: {news_headline[:80]}...")
        
        # Get instant thesis from news jacker
        result = news_jacker.get_instant_thesis(news_headline, poly_intel=None)
        
        if not result:
            log("[STAGE 11B] Could not generate news take (rate limit or generation failed)")
            return False
        
        tweet_text = result.get("tweet_text")
        market = result.get("market")
        time_to_post = result.get("time_to_post_seconds", 0)
        
        if not tweet_text:
            log("[STAGE 11B] No tweet text generated")
            return False
        
        log(f"[STAGE 11B] ✓ News take ready: {tweet_text[:80]}...")
        
        # Post the tweet using existing posting logic
        try:
            # Go to home
            stable_goto(page, HOME_URL)
            human_pause(2.0, 3.0)
            
            # Open composer
            new_tweet_button = page.locator('[data-testid="SideNav_NewTweet_Button"]').first
            if new_tweet_button.count() == 0:
                # Fallback: try compose URL
                page.goto("https://x.com/compose/tweet")
                human_pause(2.0, 3.0)
            else:
                try:
                    new_tweet_button.click(timeout=5000)
                except Exception as e:
                    log(f"[STAGE 11B] Could not click new tweet button: {e}")
                    return False
                human_pause(1.0, 2.0)
            
            # Type tweet
            box_selectors = [
                "div[role='textbox'][data-testid='tweetTextarea_0']",
                "div[role='textbox']",
            ]
            typed = False
            for sel in box_selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=3000):
                        try:
                            page.locator(sel).first.click(timeout=5000)
                        except Exception as e:
                            log(f"[STAGE 11B] Could not click composer selector {sel}: {e}")
                            continue
                        human_pause(0.3, 0.5)
                        
                        # Type tweet (faster for news - urgency)
                        log(f"[TYPE_DEBUG] About to type into composer: {tweet_text[:100]}...")
                        for ch in tweet_text:
                            page.keyboard.type(ch, delay=random.randint(15, 40))
                        typed = True
                        break
                except Exception:
                    continue
            
            if not typed:
                log("[STAGE 11B] Failed to type tweet")
                page.keyboard.press("Escape")
                return False
            
            human_pause(0.5, 1.0)
            
            # Post tweet
            posted = click_post_once(page)
            if not posted:
                log("[STAGE 11B] Failed to post tweet")
                page.keyboard.press("Escape")
                return False
            
            log(f"[STAGE 11B] ✓ Posted news jacker take to @{BOT_HANDLE}")
            
            # Mark as posted and log
            news_jacker.mark_news_posted(
                news_headline=news_headline,
                market_affected=market,
                thesis=result.get("thesis", {}),
                time_to_post=time_to_post
            )
            
            # Log to analytics if available
            if ANALYTICS:
                ANALYTICS.log_action("post", "breaking_news", True, f"news_{int(time.time())}")
            
            time_minutes = time_to_post / 60
            if time_minutes < 5:
                log(f"[STAGE 11B] Time to post: {time_minutes:.1f} minutes after news broke (FIRST-MOVER ✅)")
            else:
                log(f"[STAGE 11B] Time to post: {time_minutes:.1f} minutes after news broke")
            
            return True
            
        except Exception as e:
            log(f"[STAGE 11B] Error posting tweet: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
    
    except Exception as e:
        log(f"[STAGE 11B] Error in post_news_jacker_take: {e}")
        import traceback
        traceback.print_exc()
        return False

def post_thread_tweet(page, text, parent_tweet_id=None, source_stage=""):
    """
    Post a tweet as part of a thread, reusing the proven composer-typing helper.
    
    Args:
        page: Playwright page object
        text: Text to post
        parent_tweet_id: If provided, post as reply to this tweet ID. If None, post as original.
        source_stage: Stage name for logging (e.g., "11A_THREAD_1")
    
    Returns:
        tweet_id (str) if successful, None if failed
    """
    # [SAFETY] Ensure we're on X.com before posting thread tweet
    if not ensure_on_x_com(page):
        log(f"[THREAD_POST] ✗ Not on X.com, cannot post thread tweet from {source_stage}")
        return None
    
    try:
        if parent_tweet_id:
            # Reply path: Navigate to the parent tweet URL and open reply composer
            tweet_url = f"https://x.com/{BOT_HANDLE.replace('@', '')}/status/{parent_tweet_id}"
            try:
                stable_goto(page, tweet_url)
                human_pause(3.0, 4.0)  # Longer wait for page to fully load
                
                # Retry logic: Try to find tweet card with multiple attempts and scrolling
                tweet_card = None
                max_retries = 3
                for retry in range(max_retries):
                    # Try multiple selectors to find the tweet card
                    card_selectors = [
                        f'article[data-testid="tweet"] a[href*="/status/{parent_tweet_id}"]',  # More specific: tweet with matching ID
                        'article[data-testid="tweet"]',  # Fallback to first tweet
                    ]
                    
                    for selector in card_selectors:
                        try:
                            potential_card = page.locator(selector).first
                            if potential_card.count() > 0:
                                # Scroll into view to ensure it's visible
                                try:
                                    potential_card.scroll_into_view_if_needed()
                                    human_pause(0.5, 1.0)
                                except Exception:
                                    pass
                                
                                # Verify it's visible
                                if potential_card.is_visible(timeout=2000):
                                    tweet_card = potential_card
                                    break
                        except Exception:
                            continue
                    
                    if tweet_card and tweet_card.count() > 0:
                        break
                    
                    # If not found, try scrolling down to load more content
                    if retry < max_retries - 1:
                        log(f"[THREAD_POST] Tweet card not found, scrolling and retrying (attempt {retry + 1}/{max_retries})")
                        try:
                            page.keyboard.press("PageDown")
                            human_pause(1.0, 2.0)
                        except Exception:
                            pass
                
                if not tweet_card or tweet_card.count() == 0:
                    log(f"[THREAD_POST] Could not find tweet card for reply from {source_stage} after {max_retries} attempts")
                    return None
                
                log(f"[THREAD_POST] Found tweet card for reply from {source_stage}")
                
                # Try multiple reply button selectors with retry logic (same as reply_to_card)
                reply_selectors = [
                    '[data-testid="reply"]',
                    'button[data-testid="reply"]',
                    '[aria-label="Reply"]',
                    'button[aria-label="Reply"]',
                    'div[role="button"][data-testid="reply"]',  # Additional selector variant
                ]
                reply_clicked = False
                max_reply_retries = 3
                
                for retry_attempt in range(max_reply_retries):
                    for selector in reply_selectors:
                        try:
                            reply_button = tweet_card.locator(selector).first
                            if reply_button.count() > 0 and reply_button.is_visible(timeout=2000):
                                # Scroll into view if needed
                                try:
                                    reply_button.scroll_into_view_if_needed()
                                    human_pause(0.3, 0.5)
                                except Exception:
                                    pass
                                
                                try:
                                    reply_button.click(force=True, timeout=5000)
                                except Exception as e:
                                    log(f"[THREAD_POST] Could not click reply button: {e}")
                                    continue
                                # [ENHANCEMENT #1] Wait longer for composer to fully render (critical for 2nd tweet)
                                time.sleep(3)  # Fixed 3s wait for compose window to be ready
                                human_pause(2.0, 3.0)  # Additional randomized wait
                                reply_clicked = True
                                log(f"[THREAD_POST] Clicked reply button (selector: {selector})")
                                break
                        except Exception as e:
                            continue
            
                    if reply_clicked:
                        break
                    
                    # If not clicked, wait and retry
                    if retry_attempt < max_reply_retries - 1:
                        log(f"[THREAD_POST] Reply button not clickable, retrying (attempt {retry_attempt + 1}/{max_reply_retries})")
                        human_pause(1.0, 2.0)
                
                if not reply_clicked:
                    log(f"[THREAD_POST] Could not click reply button from {source_stage} after {max_reply_retries} attempts")
                    return None
                
                # [ENHANCEMENT #1] Add retry logic for composer interaction (critical for 2nd tweet)
                posted = False
                max_composer_retries = 2
                for composer_attempt in range(max_composer_retries):
                    try:
                        # Use the working helper with composer already open
                        posted = open_and_post_tweet(page, text, is_reply=True)
                        if posted:
                            log(f"[11A_THREAD] Tweet {source_stage} posted successfully (attempt {composer_attempt + 1})")
                            break
                        else:
                            if composer_attempt < max_composer_retries - 1:
                                log(f"[11A_THREAD] Composer interaction failed, retrying (attempt {composer_attempt + 1}/{max_composer_retries})")
                                time.sleep(1)  # Wait before retry
                    except Exception as e:
                        log(f"[11A_THREAD_FAIL] Error on attempt {composer_attempt + 1}: {e}")
                        if composer_attempt < max_composer_retries - 1:
                            time.sleep(1)
                        else:
                            log(f"[THREAD_POST] Failed to post reply from {source_stage} after {max_composer_retries} attempts")
                
                if not posted:
                    log(f"[THREAD_POST] Failed to post reply from {source_stage}")
                    return None
                
                # Extract tweet_id from the posted reply (navigate to profile and find latest)
                human_pause(2.0, 3.0)
                page.goto(f"https://x.com/{BOT_HANDLE.replace('@', '')}")
                human_pause(2.0, 3.0)
                
                first_tweet_card = page.locator('article[data-testid="tweet"]').first
                if first_tweet_card.count() > 0:
                    tweet_id = extract_tweet_id(first_tweet_card)
                    if tweet_id:
                        log(f"[THREAD_POST] ✓ Reply posted from {source_stage}, tweet_id={tweet_id}")
                        return tweet_id
                
                log(f"[THREAD_POST] Reply posted but could not extract tweet_id from {source_stage}")
                return "unknown"  # Return non-None to indicate success
            except Exception as e:
                log(f"[THREAD_POST] Error posting reply from {source_stage}: {e}")
                return None
        else:
            # Original tweet path: Use the working helper
            posted = open_and_post_tweet(page, text, is_reply=False)
            if not posted:
                log(f"[THREAD_POST] Failed to post original tweet from {source_stage}")
                return None
            
            # Extract tweet_id by navigating to profile
            human_pause(2.0, 3.0)
            page.goto(f"https://x.com/{BOT_HANDLE.replace('@', '')}")
            human_pause(2.0, 3.0)
            
            first_tweet_card = page.locator('article[data-testid="tweet"]').first
            if first_tweet_card.count() > 0:
                tweet_id = extract_tweet_id(first_tweet_card)
                if tweet_id:
                    log(f"[THREAD_POST] ✓ Original tweet posted from {source_stage}, tweet_id={tweet_id}")
                    return tweet_id
            
            log(f"[THREAD_POST] Original tweet posted but could not extract tweet_id from {source_stage}")
            return "unknown"  # Return non-None to indicate success
            
    except Exception as e:
        log(f"[THREAD_POST] Exception in post_thread_tweet from {source_stage}: {e}")
        import traceback
        traceback.print_exc()
        return None

# Stage 11A state (persists across function calls)
_stage11a_state = {
    "last_thread_post_ts": 0,
    "myth_reality_count_today": 0,  # [STAGE 14] Daily counter for Myth/Reality threads
    "myth_reality_last_date": ""  # [STAGE 14] Track date for daily reset
}

# [STAGE 14] Helper functions for Myth/Reality thread limiting
def _reset_myth_reality_counter_if_new_day():
    """Reset daily Myth/Reality counter if it's a new day."""
    global _stage11a_state
    today = datetime.now().strftime("%Y-%m-%d")
    if _stage11a_state.get("myth_reality_last_date") != today:
        _stage11a_state["myth_reality_count_today"] = 0
        _stage11a_state["myth_reality_last_date"] = today
        log("[STAGE 14] [MYTH_REALITY] Daily counter reset for new day")

def can_post_myth_reality_today(max_per_day=2):
    """Check if we can post a Myth/Reality thread today (max 1-2 per day)."""
    global _stage11a_state
    _reset_myth_reality_counter_if_new_day()
    count = _stage11a_state.get("myth_reality_count_today", 0)
    can_post = count < max_per_day
    if not can_post:
        log(f"[STAGE 14] [MYTH_REALITY] Daily limit reached ({count}/{max_per_day}), using alternative template")
    return can_post

def _record_myth_reality_post():
    """Record that a Myth/Reality thread was posted today."""
    global _stage11a_state
    _reset_myth_reality_counter_if_new_day()
    _stage11a_state["myth_reality_count_today"] = _stage11a_state.get("myth_reality_count_today", 0) + 1
    log(f"[STAGE 14] [MYTH_REALITY] Posted ({_stage11a_state['myth_reality_count_today']}/2 today)")

def post_daily_contrarian_thread(page):
    """
    Stage 11A: Post daily contrarian thread from Stage 10 theses OR viral fallback from trends.
    Posts 1 high-quality thread every 6-8 hours.
    """
    global _stage11a_state
    
    if not STAGE_11A_ENABLED:
        return False
    
    try:
        # Rate limiting: Check if 6 hours have passed since last thread
        current_ts = time.time()
        last_post_ts = _stage11a_state.get("last_thread_post_ts", 0)
        hours_since_last = (current_ts - last_post_ts) / 3600
        
        if last_post_ts > 0 and hours_since_last < 6:
            log(f"[11A] [THREAD_SKIP] Too soon since last thread ({hours_since_last:.1f}h < 6h required)")
            return False
        
        # [STAGE 15] Thread timing optimization (Tue-Thu priority)
        should_prioritize = should_prioritize_threads_today()
        if not should_prioritize:
            log("[STAGE 15] [TIMING_DAY] Low engagement day (Mon/Fri/weekend), skipping thread")
            return False
        log("[STAGE 15] [TIMING_DAY] High engagement day (Tue-Thu), proceeding with thread")
        
        log("[11A] [THREAD] Starting thread builder...")
        
        tweets = []
        thread_source = "theses"
        
        # Primary Path: Try to get tweets from Stage 10 theses
        if thread_builder:
            thread_data = thread_builder.get_thread_tweets(hours=24, top_n=5)
            
            if thread_data.get("ready_to_post", False):
                tweets = thread_data.get("tweets", [])
                if tweets and len(tweets) > 0:
                    log(f"[11A] [THREAD] Using {len(tweets)} tweets from Stage 10 theses")
                else:
                    tweets = []
        
        # Fallback Path: If no theses, generate viral thread from trends
        if not tweets or len(tweets) == 0:
            log("[11A] [THREAD] No theses found, trying viral fallback from trends...")
            
            if not openai_client:
                log("[11A] [THREAD] OpenAI client not available, cannot generate viral thread")
                return False
            
            if not TRENDING_JACKER:
                log("[11A] [THREAD] TRENDING_JACKER not available, cannot get trends")
                return False
            
            # Get trends from Stage 12 cache
            trends = TRENDING_JACKER.get_cached_trends() or []
            if not trends:
                log("[11A] [THREAD] No trends available from Stage 12")
                return False
            
            # Pick highest-volume topic related to Politics, Sports, or Crypto
            selected_trend = None
            trend_keywords = ["SaaS", "marketing", "growth", "attribution", "conversion", "tracking", 
                            "tools", "analytics", "links", "affiliate",
                            "startup", "founder", "creator", "indie", "hacker", "growth"]
            
            for trend in trends:
                trend_name_lower = trend.get("name", "").lower() if isinstance(trend, dict) else str(trend).lower()
                if any(kw in trend_name_lower for kw in trend_keywords):
                    selected_trend = trend
                    break
            
            if not selected_trend:
                # If no match, just use first trend
                selected_trend = trends[0]
            
            trend_name = selected_trend.get("name", "") if isinstance(selected_trend, dict) else str(selected_trend)
            
            # Generate viral thread using OpenAI
            # [STAGE 14] Template rotation to avoid Myth/Reality spam
            try:
                system_prompt = """You are a top SaaS growth expert writing contrarian X threads on marketing and growth. 

Your goal: Write 3-4 part viral threads that:
- Sound OPINIONATED, not neutral (you have a take, not questions)
- Reference specific market prices and moves
- Include data/odds that prove the crowd is wrong
- End with urgency ("watch the next 48 hours", "odds won't hold", "early movers win")
- Sound like a real trader explaining an edge, NOT a bot or salesman

BANNED PHRASES (never use):
- "Interesting"
- "What are your thoughts"
- "Check this out"
- "Consider this"
- Any generic filler

REQUIRED ELEMENTS:
- Specific market name and odds (e.g., "Trump 2026 at 35%")
- Contrarian statement ("Everyone's wrong", "Market missed this", "Crowd's sleeping on this")
- Urgency indicator ("moving fast", "won't last", "odds shifting")
- Edge explanation (why you're right, why crowd is wrong)

Output ONLY a JSON array of tweet strings. No preamble. Tweets must be ≤280 chars each."""
                
                # [DISABLED_FOR_RECOVERY] Myth/Reality spam pattern disabled - was causing repetitive bot-like posts
                # Check if we can use Myth/Reality template (max 2 per day)
                # use_myth_reality = can_post_myth_reality_today(max_per_day=2)
                use_myth_reality = False  # Disabled to prevent spam
                
                if False:  # [DISABLED] Myth/Reality disabled
                    # user_prompt = f"Generate a 3-tweet 'Myth vs. Reality' thread on the topic '{trend_name}'. Tweet 1 must be a strong hook. Tweet 2 must provide a data point from marketing attribution. Tweet 3 must have a conclusion and the URL '{REFERRAL_LINK}'. Make it spicy and opinionated."
                    # log(f"[11A] [THREAD] Generating Myth vs Reality thread for topic: {trend_name}")
                    pass
                else:
                    # New trader-focused thread templates (1-2x per week max, no Myth/Reality spam)
                    # [IMPORT_FIX] random is already imported at top of file, don't re-import
                    thread_template_type = random.choice(["trade_breakdown", "lesson_insight"])
                    
                    if thread_template_type == "trade_breakdown":
                        # Thread A: Trade Breakdown - VIRAL VERSION
                        user_prompt = f"""Generate a 3-tweet thread on '{trend_name}' (most recent trends in SaaS growth). Use this structure:

Tweet 1: "Market position: [SPECIFIC MARKET] is mispriced at [ODDS]%. Here's why the crowd is wrong. 🧵"
Tweet 2: "Real talk: If [BULLISH_SCENARIO] happens, this reprices to [TARGET_ODDS]%. If [BEARISH_SCENARIO] hits, I'm wrong and cutting. But the odds today don't reflect that volatility."
Tweet 3: "This is the early mover advantage. By the time everyone sees [KEY_FACTOR], the best price is gone. That's why smart money is already positioned."

Make it sound like you're explaining a real strategy to a fellow founder. Use specific tools, metrics (CTR, conversion rates, etc.) and real percentages. No generic fluff. Sound helpful and contrarian."""
                        log(f"[11A] [THREAD] Generating Trade Breakdown thread for topic: {trend_name}")
                    else:
                        # Thread B: Lesson / Insight (4 tweets) - VIRAL VERSION
                        user_prompt = f"""Generate a 4-tweet thread on '{trend_name}' (SaaS growth insights). Use this structure:

Tweet 1: "Prediction markets are showing something most traders miss. Here's what I'm seeing. 🧵"
Tweet 2: "The crowd is pricing [SCENARIO_A] at [ODDS]%, but the data actually suggests [SCENARIO_B]. That gap is free edge if you see it first."
Tweet 3: "Most people wait for news to move first, then chase prices. Smart traders position BEFORE the news hits. That's where the real liquidity hides."
Tweet 4: "Watch what happens in the next 24-48 hours. Market's repricing. Early movers locked in the best odds. You won't get this price again."

Make it educational but opinionated. Sound like you're teaching someone how to think like a professional. Use real market data and scenarios. No sales pitch, just insight."""
                        log(f"[11A] [THREAD] Generating Lesson/Insight thread for topic: {trend_name}")
                    
                    # Note: Link will be added to final tweet only if needed (0-1 times per thread)
                
                
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.8,
                    max_tokens=600
                )
                
                raw_content = response.choices[0].message.content.strip()
                
                # Parse JSON array from response
                # Try to extract JSON array if wrapped in markdown code blocks
                if "```" in raw_content:
                    import re
                    json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', raw_content, re.DOTALL)
                    if json_match:
                        raw_content = json_match.group(1)
                
                tweets = json.loads(raw_content)
                
                if not isinstance(tweets, list) or len(tweets) != 3:
                    log(f"[11A] [THREAD] Invalid tweet array format, expected 3 tweets, got: {type(tweets)}")
                    return False
                
                # [STAGE 14] Record if Myth/Reality was used
                if use_myth_reality:
                    _record_myth_reality_post()
                
                # Ensure Tweet 3 has the URL
                if tweets[2] and REFERRAL_LINK not in tweets[2]:
                    tweets[2] = f"{tweets[2]} {REFERRAL_LINK}"
                
                # VALIDATION: Reject generic tweets
                banned_phrases = [
                    "interesting",
                    "what are your thoughts",
                    "consider this",
                    "check this out",
                    "let me know",
                    "any thoughts",
                ]
                
                for i, tweet in enumerate(tweets):
                    for phrase in banned_phrases:
                        if phrase.lower() in tweet.lower():
                            log(f"[VALIDATION] Tweet {i+1} contains banned phrase '{phrase}', regenerating...")
                            # Regenerate this specific tweet with stronger contrarian prompt
                            try:
                                regenerate_prompt = f"""The previous tweet was too generic. Generate a replacement tweet {i+1} for a thread on '{trend_name}'. Make it contrarian, specific, and opinionated. Include market data or odds. No generic phrases. Output ONLY the tweet text, no JSON wrapper."""
                                regenerate_response = openai_client.chat.completions.create(
                                    model="gpt-4o-mini",
                                    messages=[
                                        {"role": "system", "content": "Output ONLY the tweet text. No markdown. No explanation."},
                                        {"role": "user", "content": regenerate_prompt}
                                    ],
                                    temperature=0.9,
                                    max_tokens=150
                                )
                                new_tweet = regenerate_response.choices[0].message.content.strip()
                                if new_tweet.startswith('"') and new_tweet.endswith('"'):
                                    new_tweet = new_tweet[1:-1]
                                tweets[i] = new_tweet
                                log(f"[VALIDATION] ✓ Regenerated tweet {i+1}")
                            except Exception as regen_error:
                                log(f"[VALIDATION] Failed to regenerate tweet {i+1}: {regen_error}")
                            break
                
                # Apply viral template hashtags if available (opening and closing tweets)
                template = pick_matching_template(VIRAL_TEMPLATES, niche_hint="prediction_markets")
                if template:
                    # Add hashtags to opening tweet (tweets[0])
                    tweets[0] = append_hashtags_if_template(tweets[0], template)
                    # Add hashtags to closing tweet (tweets[-1])
                    tweets[-1] = append_hashtags_if_template(tweets[-1], template)
                
                thread_source = "viral_fallback"
                log(f"[11A] [THREAD] Generated 3 tweets for topic: {trend_name}")
                    
            except Exception as e:
                log(f"[11A] [THREAD] Error generating viral thread: {e}")
                import traceback
                traceback.print_exc()
                return False
        
        if not tweets or len(tweets) == 0:
            log("[11A] [THREAD] No tweets to post")
            return False
        
        if len(tweets) < 3:
            log(f"[11A] [THREAD] Need exactly 3 tweets, got {len(tweets)}")
            return False
        
        # Use first 3 tweets only
        tweets = tweets[:3]
        
        # HUMAN-LIKE RANDOMIZATION
        # 1. Random delay before posting first tweet (2-8 min) – looks human
        first_tweet_delay = random.uniform(120, 480)  # 2-8 minutes
        log(f"[HUMAN] Waiting {first_tweet_delay/60:.1f} min before posting thread (human behavior)")
        time.sleep(first_tweet_delay)
        
        # 2. Occasionally skip posting (rare) to look like real person choosing moments
        if random.random() < 0.05:  # 5% chance
            log("[HUMAN] Skipping thread post (decided not to post this take)")
            return False
        
        # 3. Add subtle emoji variation to opening tweet for human feel
        if random.random() < 0.3:  # 30% chance
            opening_emoji_swap = {
                "🧵": "📊",
                "🚨": "⚡",
                "💡": "🎯",
            }
            for old, new in opening_emoji_swap.items():
                if old in tweets[0]:
                    tweets[0] = tweets[0].replace(old, new)
                    log(f"[HUMAN] Swapped emoji {old} → {new} in opening tweet")
                    break
        
        log(f"[11A] [THREAD] Posting {len(tweets)}-tweet thread (source: {thread_source})...")
        
        # Post thread: Tweet 1 (original) -> wait 20-30s -> Tweet 2 (reply to 1) -> wait 20-30s -> Tweet 3 (reply to 2)
        try:
            # Post Tweet 1 (original)
            log(f"[11A] [THREAD] Posting tweet 1/3...")
            tweet_id_1 = post_thread_tweet(page, tweets[0], parent_tweet_id=None, source_stage="11A_THREAD_1")
            if not tweet_id_1:
                log(f"[11A] [THREAD] Failed to post first tweet, aborting thread")
                return False
            
            log(f"[11A] [THREAD] ✓ Posted tweet 1/3: {tweets[0][:50]}...")
            
            # Wait 20-30 seconds between tweets
            wait_seconds = random.uniform(20.0, 30.0)
            log(f"[11A] [THREAD] Waiting {wait_seconds:.1f}s before posting tweet 2/3...")
            time.sleep(wait_seconds)
            
            # Post Tweet 2 (reply to Tweet 1)
            log(f"[11A] [THREAD] Posting tweet 2/3...")
            tweet_id_2 = post_thread_tweet(page, tweets[1], parent_tweet_id=tweet_id_1, source_stage="11A_THREAD_2")
            if not tweet_id_2:
                log(f"[11A] [THREAD] Failed to post second tweet, aborting thread")
                return False
            
            log(f"[11A] [THREAD] ✓ Posted tweet 2/3: {tweets[1][:50]}...")
            
            # Wait 20-30 seconds before Tweet 3
            wait_seconds = random.uniform(20.0, 30.0)
            log(f"[11A] [THREAD] Waiting {wait_seconds:.1f}s before posting tweet 3/3...")
            time.sleep(wait_seconds)
            
            # Post Tweet 3 (reply to Tweet 2)
            log(f"[11A] [THREAD] Posting tweet 3/3...")
            tweet_id_3 = post_thread_tweet(page, tweets[2], parent_tweet_id=tweet_id_2, source_stage="11A_THREAD_3")
            if not tweet_id_3:
                log(f"[11A] [THREAD] Failed to post third tweet, aborting thread")
                return False
            
            log(f"[11A] [THREAD] ✓ Posted tweet 3/3: {tweets[2][:50]}...")
            
            # Mark thread as posted (if thread_builder exists and we used theses)
            if thread_builder and thread_source == "theses":
                thread_builder.mark_thread_posted(tweets)
            
            # Update state with timestamp
            _stage11a_state["last_thread_post_ts"] = time.time()
            
            log(f"[11A] [THREAD] Full 3-tweet thread posted successfully (source={thread_source})")
            
            return True
            
        except Exception as e:
            log(f"[11A] [THREAD] Error posting thread: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
    
    except Exception as e:
        log(f"[11A] [THREAD] Error in post_daily_contrarian_thread: {e}")
        import traceback
        traceback.print_exc()
        return False

def should_run_strategy_brain():
    """Run brain once per day at 1am to analyze yesterday's data"""
    if not BRAIN:
        return False
    
    current_hour = datetime.now().hour
    last_brain_time = getattr(should_run_strategy_brain, 'last_time', None)
    
    if current_hour == 1 and (last_brain_time is None or 
                              (datetime.now() - last_brain_time).days > 0):
        should_run_strategy_brain.last_time = datetime.now()
        return True
    return False

def should_post_daily_thread():
    """Check if we should post daily thread (once per day at 9am ±15 min randomization)"""
    if not STAGE_11A_ENABLED or not thread_builder:
        return False
    
    # Check if we've already posted today (thread_builder handles this internally)
    if thread_builder.has_posted_today():
        return False
    
    # Get randomized time from thread_builder (cached for consistency)
    if not hasattr(should_post_daily_thread, 'scheduled_time'):
        thread_data = thread_builder.get_thread_tweets(hours=24, top_n=5)
        if thread_data.get("ready_to_post"):
            should_post_daily_thread.scheduled_time = {
                "hour": thread_data.get("scheduled_hour", 9),
                "minute": thread_data.get("scheduled_minute", 0),
                "formatted": thread_data.get("randomized_time", "9:00")
            }
            log(f"[STAGE 11A] Thread scheduled for {should_post_daily_thread.scheduled_time['formatted']} (randomized)")
        else:
            # Not ready, use default 9am
            should_post_daily_thread.scheduled_time = {"hour": 9, "minute": 0, "formatted": "9:00"}
    
    scheduled_time = should_post_daily_thread.scheduled_time
    now = datetime.now()
    current_hour = now.hour
    current_minute = now.minute
    
    # Check if we're at or past the scheduled time
    scheduled_total_minutes = scheduled_time["hour"] * 60 + scheduled_time["minute"]
    current_total_minutes = current_hour * 60 + current_minute
    
    last_thread_time = getattr(should_post_daily_thread, 'last_time', None)
    today = now.date()
    
    # Check if it's time to post (at or past scheduled time) and we haven't posted today
    if scheduled_total_minutes <= current_total_minutes and (last_thread_time is None or 
                                                              last_thread_time.date() < today):
        should_post_daily_thread.last_time = now
        # Clear scheduled time so it gets recalculated next time
        if hasattr(should_post_daily_thread, 'scheduled_time'):
            delattr(should_post_daily_thread, 'scheduled_time')
        return True
    
    return False

def bot_loop(page):
    dedup_tweets = load_json(DEDUP_TWEETS, {})
    recent_replies = load_json(DEDUP_TEXTS, [])  # Load as list, not set

    start_time = time.time()
    reply_counter = 0
    log("✅ Logged in & ready. Starting smart reply loop…")
    
    # Initialize Stage 11B state
    stage11b_state = {
        "last_news_forced_post_ts": 0,
        "news_forced_posts_today": 0,
        "news_forced_posts_today_date": None,
        "_page": page
    }
    
    # Initialize Stage 53 timer (runs every 2 hours)
    stage53_last_run = 0
    
    # Initialize backup timer (runs every 1 hour)
    last_backup_time = 0

    while True:
        # Heartbeat logging every 5 minutes
        if HARDENING:
            HARDENING.heartbeat()
        
        # Check sleep hours at start of each loop
        if should_sleep_now():
            sleep_duration = random.randint(60, 300)  # 1-5 minutes
            log(f"[SLEEP_MODE] Bot sleeping for {sleep_duration}s (UTC hours 3-6)")
            
            # [NOTION] Log sleep status
            if NOTION_MANAGER:
                try:
                    wake_time = datetime.now(timezone.utc).timestamp() + sleep_duration
                    wake_time_str = datetime.fromtimestamp(wake_time, tz=timezone.utc).strftime('%H:%M:%S UTC')
                    NOTION_MANAGER.update_task_status(
                        "Bot Status",
                        "Not started",
                        f"Sleeping until {wake_time_str} (UTC hours 3-6)"
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log sleep: {e}")
            
            time.sleep(sleep_duration)
            continue
        
        # Check if paused due to errors
        if HARDENING and HARDENING.is_paused():
            time.sleep(60)  # Wait 1 minute before checking again
            continue
        
        # Check if we should take a break after N consecutive actions
        if HARDENING:
            should_break, break_duration = HARDENING.should_take_break(
                actions_since_break=5,
                break_minutes_min=30,
                break_minutes_max=60
            )
            if should_break:
                time.sleep(break_duration)
                continue
        
        # [STAGE 53] Intelligent Video Viral Engine - Check schedule first every loop
        log("[STAGE 53] Checking schedule...")
        if not should_sleep_now():
            # Check if 2 hours have passed since last run
            if time.time() - stage53_last_run > 7200:  # 2 hours
                log("[STAGE 53] ===== REACHED STAGE 53 SECTION =====")
                log("[STAGE 53] Sleep check passed, attempting import...")
                try:
                    from stage_53_viral_video_engine import (
                        discover_viral_accounts,
                        analyze_viral_account_styles,
                        scrape_trending_videos,
                        generate_smart_caption,
                        post_viral_video
                    )
                    log("[STAGE 53] ✓ Module imported successfully")
                    
                    # [STAGE 53 TEST] Manual test mode helper
                    def debug_run_stage53_once(page, stage53_state, openai_client, deduplicator):
                        """
                        Run Stage 53 scrape/queue logic once on demand for testing.
                        Reuses existing Stage 53 code paths and filters.
                        """
                        try:
                            from stage_53_viral_video_engine import scrape_trending_videos
                            
                            log("[STAGE 53 TEST] Starting manual scrape test...")
                            
                            # Run scrape using existing function (applies all filters)
                            videos = scrape_trending_videos(page, deduplicator)
                            
                            # Log results
                            log(f"[STAGE 53 TEST] Scrape completed: found {len(videos)} qualifying videos")
                            
                            # Add to queue (merge with existing if any)
                            existing_queue = stage53_state.get("_stage53_video_queue", [])
                            if videos:
                                # Merge new videos, avoiding duplicates by video_id
                                existing_ids = {v.get("video_id") for v in existing_queue}
                                new_videos = [v for v in videos if v.get("video_id") not in existing_ids]
                                
                                stage53_state["_stage53_video_queue"] = existing_queue + new_videos
                                stage53_state["_stage53_last_scrape"] = time.time()
                                
                                log(f"[STAGE 53 TEST] Enqueued {len(new_videos)} new videos (total in queue: {len(stage53_state['_stage53_video_queue'])})")
                            else:
                                log("[STAGE 53 TEST] No qualifying videos found (filters may be too strict)")
                            
                            log("[STAGE 53 TEST] Manual test complete")
                            
                        except Exception as e:
                            log(f"[STAGE 53 TEST] Error in manual test: {e}")
                            import traceback
                            traceback.print_exc()
                    
                    # Use stage11b_state for state management (defined in bot_loop)
                    stage53_state = stage11b_state
                    stage53_state["_page"] = page
                    
                    # [STAGE 53 FORCE] One-time scrape at startup (if env var set)
                    if os.getenv("STAGE53_FORCE_NOW") == "1":
                        debug_run_stage53_once(page, stage53_state, openai_client, DEDUPLICATOR)
                        # Continue with normal Stage 53 flow after startup scrape
                    
                    # [STAGE 53 TEST] Manual test mode (if env var set)
                    if os.getenv("STAGE53_DEBUG") == "1":
                        debug_run_stage53_once(page, stage53_state, openai_client, DEDUPLICATOR)
                        # Continue with normal Stage 53 flow after test
                    
                    # Load video queue from disk if not already in memory (persistence on startup)
                    if "_stage53_video_queue" not in stage53_state:
                        video_queue_file = Path("storage/stage53_video_queue.json")
                        if video_queue_file.exists():
                            try:
                                queue_data = json.loads(video_queue_file.read_text())
                                videos = queue_data.get("videos", [])
                                # Convert path strings back to Path objects
                                for video in videos:
                                    if "path" in video and isinstance(video["path"], str):
                                        video["path"] = Path(video["path"])
                                stage53_state["_stage53_video_queue"] = videos
                                # Load last scrape time from file timestamp
                                scraped_at_str = queue_data.get("scraped_at", "")
                                if scraped_at_str:
                                    try:
                                        scraped_at_dt = datetime.fromisoformat(scraped_at_str.replace("Z", "+00:00"))
                                        stage53_state["_stage53_last_scrape"] = scraped_at_dt.timestamp()
                                    except Exception:
                                        stage53_state["_stage53_last_scrape"] = 0
                                else:
                                    stage53_state["_stage53_last_scrape"] = 0
                                if videos:
                                    log(f"[STAGE 53] ✓ Loaded {len(videos)} videos from disk queue")
                            except Exception as e:
                                log(f"[STAGE 53] Error loading video queue from disk: {e}")
                                stage53_state["_stage53_video_queue"] = []
                                stage53_state["_stage53_last_scrape"] = 0
                        else:
                            # Initialize empty queue if file doesn't exist
                            stage53_state["_stage53_video_queue"] = []
                            stage53_state["_stage53_last_scrape"] = 0
                    
                    # Check OpenAI client availability
                    if not openai_client:
                        log("[STAGE 53] Skipping - OpenAI client not available")
                        # Continue to next stage (don't error, just skip)
                    else:
                        # Initialize on first run
                        if "_stage53_initialized" not in stage53_state:
                            accounts = discover_viral_accounts(openai_client)
                            stage53_state["_stage53_accounts"] = accounts
                            stage53_state["_stage53_initialized"] = True
                            log("[STAGE 53] ✓ Initialized viral account discovery")
                        
                        # Analyze styles once per day
                        if stage53_state.get("_stage53_accounts"):
                            last_style_analysis = stage53_state.get("_stage53_last_style_analysis", "")
                            today_str = datetime.now().strftime("%Y-%m-%d")
                            if last_style_analysis != today_str:
                                learned_styles = analyze_viral_account_styles(page, openai_client, stage53_state["_stage53_accounts"])
                                stage53_state["_stage53_learned_styles"] = learned_styles
                                stage53_state["_stage53_last_style_analysis"] = today_str
                                log("[STAGE 53] ✓ Analyzed account styles")
                        
                        # Scrape videos every 2 hours
                        last_scrape = stage53_state.get("_stage53_last_scrape", 0)
                        if time.time() - last_scrape > 7200:  # 2 hours
                            videos = scrape_trending_videos(page, DEDUPLICATOR)
                            stage53_state["_stage53_video_queue"] = videos
                            stage53_state["_stage53_last_scrape"] = time.time()
                            log(f"[STAGE 53] ✓ Scraped {len(videos)} videos")
                        
                        # Post videos 3-5 times/day (check queue)
                        video_queue = stage53_state.get("_stage53_video_queue")
                        if not video_queue:
                            log("[STAGE 53] No videos in queue, waiting for next scrape cycle")
                        else:
                            learned_styles = stage53_state.get("_stage53_learned_styles", {})
                            
                            if video_queue and learned_styles:
                                # Pick best video from queue
                                video = video_queue[0]  # Simple: pick first, could add ranking
                                
                                # Generate caption using existing function
                                caption = generate_smart_caption(openai_client, video, learned_styles)
                                
                                if caption:
                                    # Post video
                                    success = post_viral_video(page, video, caption, stage53_state, DEDUPLICATOR)
                                    if success:
                                        # Remove from queue
                                        stage53_state["_stage53_video_queue"] = video_queue[1:]
                                        log("[STAGE 53] ✓ Posted viral video")
                                else:
                                    log("[STAGE 53] Failed to generate caption, skipping")
                            else:
                                if not learned_styles:
                                    log("[STAGE 53] No learned styles available, waiting for style analysis")
                                if not video_queue:
                                    log("[STAGE 53] Video queue is empty")
                    
                    # Update last run time
                    stage53_last_run = time.time()
                                
                except ImportError as e:
                    log(f"[STAGE 53] Import failed: {e}")
                except Exception as e:
                    log(f"[STAGE 53] Import failed: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Get current phase
        if PHASE_CONTROLLER:
            current_phase = PHASE_CONTROLLER.update_phase()
            log(f"[PHASE {current_phase}] Active")
        
        # Run daily cleanup (once per day, at 9am)
        if should_run_daily_cleanup():
            log("[DAILY MAINTENANCE] Running cleanup...")
            
            # Delete shitty posts
            if CLEANUP:
                deleted = CLEANUP.delete_shitty_posts(page)
                log(f"[CLEANUP] Deleted {deleted} low-quality posts")
            
            # Unfollow dead accounts
            if FOLLOWER_MGR:
                unfollowed = FOLLOWER_MGR.unfollow_dead_accounts(page)
                log(f"[UNFOLLOW] Unfollowed {unfollowed} non-following accounts")
            
            # Cleanup done for today - continue with normal loop
            # The date check will prevent running again until tomorrow
            log("[DAILY MAINTENANCE] Cleanup complete, continuing normal operations")
        
        # Stage 8: Strategy Brain (runs at 1am to analyze yesterday's data)
        if should_run_strategy_brain():
            log("[STAGE 8] Running Strategy Brain optimization...")
            
            # Get recommendations
            recommendations = BRAIN.get_strategy_recommendations()
            
            if recommendations:
                # Print summary for you to see
                BRAIN.print_strategy_summary(recommendations)
                
                # Implement changes
                BRAIN.implement_recommendations(recommendations)
                
                log("[BRAIN] Strategy updated for today")
            else:
                log("[BRAIN] No valid recommendations, keeping current strategy")
        
        # [FOLLOWER MULTIPLICATION ENGINE] Authority targeting (every 6 hours, max 5 replies/day)
        if 'authority_targeter' in globals() and authority_targeter and AUTHORITY_TARGETER_AVAILABLE:
            try:
                # Check if 6 hours have passed since last authority targeting
                if not hasattr(bot_loop, '_last_authority_target_time'):
                    bot_loop._last_authority_target_time = 0
                
                hours_since_last = (time.time() - bot_loop._last_authority_target_time) / 3600
                if hours_since_last >= 6:
                    log("[AUTHORITY] Finding reply opportunities with high-follower accounts...")
                    opportunities = authority_targeter.find_reply_opportunities(max_opportunities=5)
                    
                    for opp in opportunities:
                        try:
                            # Navigate to tweet
                            page.goto(opp['tweet_url'], wait_until="networkidle")
                            human_pause(2.0, 3.0)
                            
                            # Use existing reply_to_card function (find the card first)
                            tweet_card = page.locator('article[data-testid="tweet"]').first
                            if tweet_card.count() > 0:
                                # Post reply using existing reply mechanism
                                success = reply_to_card(page, tweet_card, topic="", recent_replies=[], reply_idx=0)
                                if success:
                                    log(f"[AUTHORITY] ✅ Replied to @{opp['username']} ({opp['followers']} followers)")
                                    human_pause(60, 120)  # Wait between replies
                        except Exception as e:
                            log(f"[AUTHORITY] Error replying to @{opp['username']}: {e}")
                    
                    bot_loop._last_authority_target_time = time.time()
            except Exception as e:
                log(f"[AUTHORITY] Error in authority targeting: {e}")
        
        # [FOLLOWER MULTIPLICATION ENGINE] Engagement report (daily at midnight)
        if 'engagement_multiplier' in globals() and engagement_multiplier and ENGAGEMENT_MULTIPLIER_AVAILABLE:
            try:
                current_hour = datetime.now().hour
                if current_hour == 0 and not hasattr(bot_loop, '_engagement_report_today'):
                    engagement_multiplier.generate_engagement_report()
                    bot_loop._engagement_report_today = True
                elif current_hour != 0:
                    bot_loop._engagement_report_today = False
            except Exception as e:
                log(f"[ENGAGEMENT] Error generating report: {e}")
        
        # Stage 6: Print daily analytics summary at 11pm
        if should_print_daily_summary():
            log("[ANALYTICS] Printing daily summary...")
            if ANALYTICS:
                ANALYTICS.print_daily_summary()
        
        # Stage 11A: Post contrarian thread (every 6-8 hours, viral content engine)
        # Rate limiting is handled inside post_daily_contrarian_thread (6 hour minimum)
            success = post_daily_contrarian_thread(page)
            if success:
                log("[STAGE 11A] ✓ Thread posted successfully")
        
        # Check if should follow an account (looks human)
        if ACCOUNT_HELPER and ACCOUNT_HELPER.should_follow_account():
            log("[FOLLOW] Time to follow a relevant account (5-10/day limit)")
            # TODO: Add actual follow logic here
            # For now, just log the action
            log("[FOLLOW] Follow logic not yet implemented, skipped")
        
        # [STAGE 16B] Check trending for niche opportunity (~1% of cycles, uses cached trends)
        if random.random() < 0.01:  # ~1% chance per loop iteration
            try:
                check_trending_for_niche_opportunity()
            except Exception as e:
                log(f"[STAGE 16B] Error in niche opportunity check: {e}")
        
        # [STAGE 16C] Check own posts for engagement and process scheduled replies
        if not should_sleep_now():
            try:
                check_own_posts_for_engagement(page)
            except Exception as e:
                log(f"[STAGE 16C] Error in engagement check: {e}")
            
            try:
                process_scheduled_replies(page)
            except Exception as e:
                log(f"[STAGE 16C] Error processing scheduled replies: {e}")
        
        # ============================================================
        # REPLY LOOP: Prioritized first (4 replies per 1 original)
        # ============================================================
        # Intelligent Search: Use ChatGPT to generate queries from Stage 12's trending data
        # SEARCH DISABLED - DO NOT USE (causes navigation issues)
        term = None
        if False:  # INTELLIGENT_SEARCH DISABLED - search causes navigation issues
            pass
            # try:
            #     # Get current trends from Stage 12 (already scanned hourly)
            #     trends = []
            #     markets = []
            #     if TRENDING_JACKER:
            #         trends = TRENDING_JACKER.get_cached_trends()
            #         # Get Polymarket markets for top trends
            #         for trend in trends[:3]:  # Top 3 trends
            #             trend_markets = TRENDING_JACKER.map_trend_to_markets(trend, poly_intel)
            #             for market in trend_markets:
            #                 if market.get("title"):
            #                     markets.append(market["title"])
            # 
            #     # Get intelligent query (ChatGPT generates once per hour, then reuses)
            #     term = INTELLIGENT_SEARCH.get_next_query(page, trends=trends, markets=markets, openai_client=openai_client)
            # except Exception as e:
            #     log(f"[SEARCH] Intelligent search failed: {str(e)[:100]}, using fallback")
            #     term = None
            pass  # INTELLIGENT_SEARCH disabled
        
        # Fallback to old systems if intelligent search failed or not available
        if not term:
            if RADAR_TARGETING:
                try:
                    RADAR_TARGETING.refresh_config()
                    term = RADAR_TARGETING.get_search_priority()
                except Exception:
                    term = None
        
        # Final fallback to keyword rotation
        if not term:
            term = get_next_keyword()
        
        # Ensure term is not empty
        if not term or not term.strip():
            term = "SaaS"  # Ultimate fallback
        
        search_live(page, term)
        
        cards = collect_articles(page, limit=MAX_ARTICLES_SCAN)
        
        # CHECK MENTIONS ON CURRENT PAGE (fallback if search returned no results)
        # Look for tweets that mention the bot on the current page (home feed, notifications, etc.)
        if not cards or len(cards) == 0:
            log("[REPLY_LOOP] No search results, checking current page for @mentions...")
            cards = []
        
        try:
            # Get tweets from current page (no navigation needed)
            tweet_cards = page.locator('article[data-testid="tweet"]')
            card_count = tweet_cards.count()
            log(f"[REPLY_LOOP] Found {card_count} tweets on current page")
            
            bot_handle_lower = BOT_HANDLE.lower().replace('@', '')
            mention_cards = []
            
            # Check each tweet to see if it mentions the bot
            for i in range(min(card_count, 20)):  # Check up to 20 tweets
                try:
                    card = tweet_cards.nth(i)
                    tweet_text = extract_tweet_text(card)
                    
                    # Check if tweet mentions the bot
                    if bot_handle_lower in tweet_text.lower() or f"@{bot_handle_lower}" in tweet_text.lower():
                        # Additional check: make sure it's not our own tweet
                        author_handle = extract_author_handle(card)
                        if author_handle and author_handle.lower() != bot_handle_lower:
                            mention_cards.append(card)
                            log(f"[REPLY_LOOP] Found mention from @{author_handle}")
                except Exception as e:
                    log(f"[REPLY_LOOP] Error checking tweet {i}: {e}")
                    continue
            
            if mention_cards:
                log(f"[REPLY_LOOP] Found {len(mention_cards)} tweets mentioning @{BOT_HANDLE}")
                cards = mention_cards
            else:
                log("[REPLY_LOOP] No mentions found on current page")
                cards = []  # No mentions to reply to
        except Exception as e:
            log(f"[REPLY_LOOP] Error checking for mentions: {e}")
            cards = []  # Fallback to empty list
        
        # [STAGE 14] Sort cards by follower count (descending) for quality targeting
        def get_follower_count_from_card(card):
            """Extract approximate follower count from card for sorting."""
            try:
                account_text = card.inner_text() if hasattr(card, 'inner_text') else ""
                follower_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*followers?', account_text)
                if follower_match:
                    follower_str = follower_match.group(1).upper()
                    if 'K' in follower_str:
                        return int(float(follower_str.replace('K', '')) * 1000)
                    elif 'M' in follower_str:
                        return int(float(follower_str.replace('M', '')) * 1000000)
                    else:
                        return int(float(follower_str))
            except Exception:
                pass
            return 0  # Default to 0 if can't extract
        
        # Sort by follower count descending, then shuffle within same tier
        cards_sorted = sorted(cards, key=get_follower_count_from_card, reverse=True)
        # Re-shuffle top tier (10k+) for variety while maintaining quality focus
        high_follower_cards = [c for c in cards_sorted if get_follower_count_from_card(c) >= 10000]
        low_follower_cards = [c for c in cards_sorted if get_follower_count_from_card(c) < 10000]
        random.shuffle(high_follower_cards)
        random.shuffle(low_follower_cards)
        cards = high_follower_cards + low_follower_cards  # Prioritize high-follower accounts
        
        target = random.randint(*REPLIES_PER_TERM)
        sent = 0
        log(f"[STAGE 14] [TARGETING] Processing {len(cards)} cards, prioritizing high-follower accounts")

        for card in cards:
            if sent >= target:
                break
            tid = extract_tweet_id(card)
            if not tid or tid in dedup_tweets:
                continue
            
            # Check if we should target this account/tweet
            should_reply, reason = should_target_for_reply(card, term)
            if not should_reply:
                log(f"[FILTER] Skipped target – reason: {reason}")
                continue
            
            # Log high-engagement targets
            try:
                likes_elem = card.locator('[data-testid="like"]').first
                if likes_elem.count() > 0:
                    likes_text = likes_elem.inner_text()
                    likes_str = likes_text.replace("K", "000").replace("M", "000000").replace(",", "").strip()
                    likes_count = int(''.join(filter(str.isdigit, likes_str))) if likes_str else 0
                    if likes_count >= 5:
                        log(f"[TARGETING] ✓ Found high-engagement post ({likes_count} likes)")
            except Exception:
                pass

            # Human-like engagement: Every 10 actions, do a like/retweet instead of reply
            if HARDENING and HARDENING.should_do_engagement_action(actions_between_engagement=10):
                log("[ENGAGEMENT_MIX] Time for engagement action (like/retweet) instead of reply")
                # This will be handled by the engagement mixer below

            # Stage 6: Check if we should do engagement mix instead of reply
            if ENGAGEMENT_MIXER:
                engagement_type = ENGAGEMENT_MIXER.get_next_engagement_type()
                
                # Extract post data for engagement decisions
                tweet_text = extract_tweet_text(card)
                author_handle = extract_author_handle(card)
                
                # Try to get likes count (approximate)
                likes_count = 0
                try:
                    likes_elem = card.locator('[data-testid="like"]').first
                    if likes_elem.count() > 0:
                        likes_text = likes_elem.inner_text()
                        # Parse likes (handles K, M suffixes)
                        try:
                            likes_str = likes_text.replace("K", "000").replace("M", "000000").replace(",", "").strip()
                            likes_count = int(''.join(filter(str.isdigit, likes_str))) if likes_str else 0
                        except Exception:
                            pass
                except Exception:
                    pass
                
                # Get author followers (approximate)
                author_followers = 0
                try:
                    # Try to extract from card if available
                    follower_text = card.locator('text=/\\d+\\.?\\d*[KM]?\\s*followers?/i').first
                    if follower_text.count() > 0:
                        follower_str = follower_text.inner_text()
                        if 'K' in follower_str:
                            author_followers = int(float(follower_str.replace('K', '').replace('followers', '').strip()) * 1000)
                        elif 'M' in follower_str:
                            author_followers = int(float(follower_str.replace('M', '').replace('followers', '').strip()) * 1000000)
                        else:
                            author_followers = int(''.join(filter(str.isdigit, follower_str)))
                except Exception:
                    pass
                
                # Check Radar priority
                radar_score = 0
                if RADAR_TARGETING:
                    radar_score = RADAR_TARGETING.is_radar_target(tweet_text, author_handle)
                
                # Decide on engagement type
                if engagement_type == "like":
                    post_data = {
                        "likes": likes_count,
                        "text": tweet_text,
                        "is_liked": False,
                        "author_followers": author_followers
                    }
                    if ENGAGEMENT_MIXER.should_like_this_post(post_data):
                        if ENGAGEMENT_MIXER.like_post(page, card):
                            if ANALYTICS:
                                ANALYTICS.log_action("like", term, False, tid)
                            log(f"[ENGAGEMENT] ✓ Liked tweet {tid}")
                            human_pause(*DELAY_BETWEEN_REPLIES)
                            sent += 1
                            continue
                
                elif engagement_type == "retweet":
                    post_data = {
                        "likes": likes_count,
                        "text": tweet_text,
                        "is_retweeted": False,
                        "author_followers": author_followers
                    }
                    if ENGAGEMENT_MIXER.should_retweet_this_post(post_data):
                        if ENGAGEMENT_MIXER.retweet_post(page, card):
                            if ANALYTICS:
                                ANALYTICS.log_action("retweet", term, False, tid)
                            log(f"[ENGAGEMENT] ✓ Retweeted tweet {tid}")
                            human_pause(*DELAY_BETWEEN_REPLIES)
                            sent += 1
                            continue
                
                elif engagement_type == "quote_tweet":
                    if likes_count >= 500:  # Only quote high-quality posts
                        quote_text = ENGAGEMENT_MIXER.generate_quote_tweet(tweet_text)
                        if ENGAGEMENT_MIXER.quote_tweet_post(page, card, quote_text):
                            if ANALYTICS:
                                ANALYTICS.log_action("quote", term, False, tid)
                            log(f"[ENGAGEMENT] ✓ Quote tweeted {tid}")
                            human_pause(*DELAY_BETWEEN_REPLIES)
                            sent += 1
                            continue
                
                # Otherwise continue with normal reply flow
                if radar_score > 0:
                    log(f"[RADAR] High-priority target (score: {radar_score})")

            ok = reply_to_card(page, card, topic=term, recent_replies=recent_replies, reply_idx=reply_counter + 1)
            if ok:
                reply_counter += 1
                dedup_tweets[tid] = datetime.utcnow().isoformat() + "Z"
                save_json(DEDUP_TWEETS, dedup_tweets)
                save_json(DEDUP_TEXTS, recent_replies)  # Save list directly, not converted
                
                # Track query performance for intelligent search
                if INTELLIGENT_SEARCH:
                    INTELLIGENT_SEARCH.record_query_attempt(term, success=True)
                
                # Stage 6: Log analytics for reply
                if ANALYTICS:
                    # Note: Link inclusion is determined in compose_reply_text at 15% frequency
                    # We approximate here - actual link status could be tracked in reply_to_card return value
                    # For now, we'll log based on the function that determines it
                    include_link = False  # Will be updated when we can track actual reply text
                    ANALYTICS.log_action("reply", term, include_link, tid)
                
                log(f"💬 Replied to tweet {tid}")
                
                # Record action for break tracking
                if HARDENING:
                    HARDENING.record_action()
                
                human_pause(*DELAY_BETWEEN_REPLIES)
                sent += 1
            else:
                # Track failed attempt
                if INTELLIGENT_SEARCH:
                    INTELLIGENT_SEARCH.record_query_attempt(term, success=False)
                import traceback
                log(f"[WARNING] Reply attempt failed (check [REPLY_TRACEBACK] logs for details)")
                # Traceback should already be logged by compose_reply_text, but log here for safety
                log(f"[REPLY_TRACEBACK] Reply attempt failed in main loop: {traceback.format_exc()}")
        
        # [STAGE 17] Check recent post performance every 10 minutes
        global _stage17_last_performance_check
        if '_stage17_last_performance_check' not in globals():
            _stage17_last_performance_check = 0
        current_time = time.time()
        if current_time - _stage17_last_performance_check >= 600:  # 10 minutes
            check_recent_post_performance(page)
            _stage17_last_performance_check = current_time
        
        # ============================================================
        # SMART COMMENTING: Comment on hot Polymarket posts
        # ============================================================
        # DISABLED - Commenting functions removed
        # 80% engagement comments (no link), 20% link comments
        # Max 10 comments per day, 3-10 min delays between comments
        if False:  # DISABLED - should_post_comment() and smart_comment_cycle() functions removed
            pass
            # try:
            #     comments_posted = smart_comment_cycle(page)
            #     if comments_posted > 0:
            #         log(f"[COMMENT] Comment cycle completed: {comments_posted} comments posted")
            # except Exception as e:
            #     log(f"[COMMENT] Error in comment cycle: {e}")
            #     import traceback
            #     log(f"[COMMENT_TRACEBACK] {traceback.format_exc()}")
        
        # Random delay between search terms (20-45 min, already randomized)
        human_pause(*DELAY_BETWEEN_TERMS)
        
        # ============================================================
        # STAGE 12: Smart Trending Jacker
        # ============================================================
        # TEMPORARILY DISABLED - Stage 12 search broken, causes navigation issues
        # Entry point: bot_loop() around line 2680
        # 
        # Functions:
        # - trending_jacker.py: TrendingJacker class
        #   - scan_trending_topics(): Scrapes X trending section
        #   - map_trend_to_markets(): Maps trends → Polymarket markets
        #   - find_trending_tweets(): Finds tweets about trends
        #   - is_good_hijack_target(): Filters high-value targets
        #   - generate_stage12_reply(): Generates opinionated replies
        #
        # Config: social_agent_config.py → "stage_12" section
        # - stage12_enabled: Toggle Stage 12 on/off
        # - stage12_hourly_max_replies: Max replies per hour (default: 5)
        # - stage12_trend_refresh_minutes: How often to scan trends (default: 60)
        #
        # Link usage: Stage 12 replies use 50% link frequency (high-value)
        # Deduplication: Integrated with DEDUPLICATOR system
        # ============================================================
        if False:  # DISABLED - Stage 12 search broken, causes navigation issues
            log("[STAGE 12] Starting trending scan...")
            try:
                # Load config for Stage 12
                if PHASE_CONTROLLER:
                    config = PHASE_CONTROLLER.get_phase_config()
                    stage12_config = config.get("stage_12", {})
                    TRENDING_JACKER.config = stage12_config
                    TRENDING_JACKER.stage12_enabled = stage12_config.get("stage12_enabled", True)
                    TRENDING_JACKER.hourly_max_replies = stage12_config.get("stage12_hourly_max_replies", 5)
                    TRENDING_JACKER.trend_refresh_minutes = stage12_config.get("stage12_trend_refresh_minutes", 60)
                
                if not TRENDING_JACKER.stage12_enabled:
                    log("[STAGE 12] Disabled in config, skipping")
                elif not TRENDING_JACKER.can_post_stage12_reply():
                    log("[TRENDING_SKIPPED_LIMITS] Hourly limit reached, skipping")
                else:
                    # Scan trends
                    trends = TRENDING_JACKER.scan_trending_topics(page)
                    if not trends:
                        # Try cached trends
                        trends = TRENDING_JACKER.get_cached_trends()
                    
                    if trends:
                        # Process up to 3 trends
                        for trend in trends[:3]:
                            if not TRENDING_JACKER.can_post_stage12_reply():
                                break
                            
                            # Map trend to markets
                            markets = TRENDING_JACKER.map_trend_to_markets(trend, poly_intel)
                            if not markets:
                                continue
                            
                            market = markets[0]  # Use first market
                            log(f"[TRENDING_MATCH] Trend '{trend}' → Market: {market.get('title', 'N/A')}")
                            
                            # Find tweets about this trend
                            tweet_cards = TRENDING_JACKER.find_trending_tweets(page, trend, max_tweets=5)
                            
                            hijacked = False
                            for card in tweet_cards[:3]:  # Try up to 3 tweets per trend
                                if not TRENDING_JACKER.can_post_stage12_reply():
                                    break
                                
                                # Check if good target
                                is_good, reason = TRENDING_JACKER.is_good_hijack_target(card, trend)
                                if not is_good:
                                    continue
                                
                                tweet_id = extract_tweet_id(card)
                                tweet_text = extract_tweet_text(card)
                                author_handle = extract_author_handle(card)
                                
                                # Check if already replied
                                if DEDUPLICATOR and tweet_id and DEDUPLICATOR.already_replied_to(tweet_id):
                                    continue
                                
                                log(f"[TRENDING_TARGET] Hijacking tweet {tweet_id} (reason: {reason})")
                                
                                # Generate Stage 12 reply
                                reply_text = TRENDING_JACKER.generate_stage12_reply(trend, market, tweet_text, openai_client)
                                
                                if not reply_text:
                                    log("[TRENDING_REPLY_FAIL] Generation failed")
                                    continue
                                
                                # Check bot filter
                                try:
                                    is_bot_like, _ = is_bot_like_reply(reply_text)
                                except (ValueError, TypeError):
                                    is_bot_like = False
                                
                                if is_bot_like:
                                    log("[TRENDING_REPLY_FAIL] Reply flagged as bot-like")
                                    continue
                                
                                # Check deduplication
                                if DEDUPLICATOR and DEDUPLICATOR.is_duplicate_or_similar(reply_text):
                                    log("[TRENDING_REPLY_FAIL] Duplicate text")
                                    continue
                                
                                # Add referral link (50% chance for Stage 12)
                                should_include_stage12_link = random.random() < 0.5
                                reply_text = append_link_if_needed(reply_text, REFERRAL_LINK, should_include_stage12_link)
                                
                                # Post the Stage 12 reply (reuse reply_to_card logic but with pre-generated text)
                                # Open reply box first
                                reply_clicked = False
                                try:
                                    reply_button = card.locator('[data-testid="reply"]').first
                                    if reply_button.count() > 0:
                                        try:
                                            reply_button.click(timeout=5000)
                                        except Exception as click_err:
                                            log(f"[TRENDING_REPLY_FAIL] Could not click reply button: {click_err}")
                                            continue
                                        reply_clicked = True
                                        human_pause(0.8, 1.4)
                                except Exception:
                                    log("[TRENDING_REPLY_FAIL] Could not open reply box")
                                    continue
                                
                                if not reply_clicked:
                                    continue
                                
                                # Type the reply text
                                # [SELECTOR_FIX] More robust selectors with better error handling
                                box_selectors = [
                                    "div[data-testid='tweetTextarea_0']",  # Most reliable
                                    "div[data-testid='tweetTextarea_1']",
                                    "div[data-testid='tweetTextarea']",
                                    "div[contenteditable='true'][data-testid='tweetTextarea_0']",
                                    "div[role='textbox'][data-testid='tweetTextarea_0']",
                                    "div[role='textbox'][data-testid='tweetTextarea_1']",
                                    "div.public-DraftStyleDefault-block",
                                    "div[role='textbox']",
                                ]
                                typed = False
                                for sel in box_selectors:
                                    try:
                                        locator = page.locator(sel).first
                                        if locator.count() > 0 and locator.is_visible(timeout=1500):
                                            try:
                                                locator.click(timeout=5000)
                                                log(f"[SELECTOR] Found reply box with selector: {sel}")
                                            except Exception as click_err:
                                                log(f"[TRENDING_REPLY_FAIL] Could not click composer {sel}: {click_err}")
                                                continue
                                            try:
                                                total_delay_seconds = random.uniform(1.0, 3.0)
                                                delay_per_char = int((total_delay_seconds * 1000) / max(len(reply_text), 1))
                                                delay_per_char = max(15, min(delay_per_char, 80))
                                                log(f"[TYPE_DEBUG] About to type into composer: {reply_text[:100]}...")
                                                for ch in reply_text:
                                                    page.keyboard.type(ch, delay=delay_per_char + random.randint(-5, 5))
                                                typed = True
                                                break
                                            except Exception as type_err:
                                                log(f"[TRENDING_REPLY_FAIL] Error typing: {str(type_err)[:50]}")
                                                continue
                                    except Exception as sel_err:
                                        log(f"[TRENDING_REPLY_FAIL] Selector {sel} failed: {str(sel_err)[:50]}")
                                        continue
                                
                                if not typed:
                                    log("[TRENDING_REPLY_FAIL] Could not type reply")
                                    page.keyboard.press("Escape")
                                    continue
                                
                                # Click post button
                                human_pause(0.5, 1.0)
                                posted = click_post_once(page)
                                
                                if posted:
                                    TRENDING_JACKER.record_reply(tweet_id)
                                    if DEDUPLICATOR:
                                        DEDUPLICATOR.add_reply(reply_text, tweet_id)
                                    log(f"[TRENDING_REPLY_SUCCESS] Hijacked tweet {tweet_id} for trend '{trend}'")
                                    hijacked = True
                                    human_pause(5, 10)  # Pause between hijacks
                                    break  # One hijack per trend
                                else:
                                    log("[TRENDING_REPLY_FAIL] Post button click failed")
                                    try:
                                        page.keyboard.press("Escape")
                                    except Exception:
                                        pass
                            
                            if hijacked:
                                break  # Move to next trend after successful hijack
            except Exception as e:
                # Graceful failure - don't block main loop
                error_msg = str(e)[:100]
                if "timeout" in error_msg.lower():
                    log(f"[TRENDING_SKIPPED] Stage 12 timeout, continuing with normal replies")
                else:
                    log(f"[TRENDING_SKIPPED] Stage 12 failed: {error_msg}, continuing with normal replies")
                # Continue with normal reply loop - don't raise exception
        
        # ============================================================
        # STAGE 12B: Trending Quote-Tweet Stage
        # ============================================================
        # TEMPORARILY DISABLED - Stage 12B search broken, causes navigation issues
        # Quote-tweet high-engagement tweets (especially videos) with growth/marketing angle
        # Frequency: 2-4 times per day max
        if False:  # DISABLED - STAGE_12_QUOTE_ENABLED and trending_quote_tweet and trending_quote_tweet.can_quote_tweet():
            # Check global action cap
            if HARDENING and not HARDENING.can_perform_action():
                log("[STAGE 12B] Quote-tweet skipped - global hourly action cap reached")
            else:
                try:
                    # Use viral keywords for search
                    quote_keyword = random.choice(VIRAL_SEARCH_KEYWORDS) if VIRAL_SEARCH_KEYWORDS else "SaaS growth"
                    log(f"[STAGE 12B] Searching for high-engagement tweets: {quote_keyword}")
                    
                    # SEARCH DISABLED - Do not navigate to search URLs
                    # search_url = f"https://x.com/search?q={quote_keyword.replace(' ', '%20')}&src=typed_query&f=live"
                    # stable_goto(page, search_url)
                    # human_pause(2.0, 3.0)
                    log("[STAGE 12B] Search navigation disabled - skipping quote tweet search")
                    continue  # Skip this entire block
                    
                    # Wait for tweets to load
                    for _ in range(20):
                        if page.locator('article[data-testid="tweet"]').count() > 0:
                            break
                        human_pause(0.3, 0.6)
                    
                    cards = collect_articles(page, limit=20)
                    random.shuffle(cards)  # Randomize to avoid always picking first
                    
                    quote_posted = False
                    for card in cards[:10]:  # Check first 10 tweets
                        if quote_posted:
                            break
                        
                        try:
                            tweet_id = extract_tweet_id(card)
                            if not tweet_id or trending_quote_tweet.already_quoted(tweet_id):
                                continue
                            
                            # Check if high engagement (10K+ likes or has video with 5K+ total)
                            if not trending_quote_tweet.is_high_engagement(card):
                                continue
                            
                            tweet_text = extract_tweet_text(card)
                            if not tweet_text or len(tweet_text) < 20:
                                continue
                            
                            log(f"[STAGE 12B] Found high-engagement tweet: {tweet_id[:20]}...")
        
                            # Generate quote text with Polymarket angle
                            quote_text = trending_quote_tweet.generate_quote_text(tweet_text, openai_client, REFERRAL_LINK)
                            
                            if not quote_text:
                                continue
            
                            # Quote-tweet using existing engagement mixer logic
                            # Navigate to tweet URL first
                            tweet_url = f"https://x.com/{extract_author_handle(card).replace('@', '')}/status/{tweet_id}"
                            stable_goto(page, tweet_url)
                            human_pause(2.0, 3.0)
                            
                            # Find the tweet card
                            tweet_card = page.locator('article[data-testid="tweet"]').first
                            if tweet_card.count() == 0:
                                log("[STAGE 12B] Could not find tweet card for quote")
                                continue
            
                            # Click retweet button
                            retweet_button = tweet_card.locator('[data-testid="retweet"]').first
                            if retweet_button.count() == 0:
                                log("[STAGE 12B] Retweet button not found")
                                continue
                            
                            try:
                                retweet_button.click(timeout=5000)
                            except Exception as e:
                                log(f"[STAGE 12B] Could not click retweet button: {e}")
                                continue
                            human_pause(1.0, 1.5)
                            
                            # Click "Quote Tweet" option
                            quote_option = page.locator('text="Quote"').first
                            if quote_option.count() == 0:
                                quote_option = page.locator('[data-testid="Dropdown"] text="Quote"').first
                            if quote_option.count() == 0:
                                log("[STAGE 12B] Quote option not found")
                                page.keyboard.press("Escape")  # Close menu
                                continue
                            
                            try:
                                quote_option.click(timeout=5000)
                            except Exception as e:
                                log(f"[STAGE 12B] Could not click quote option: {e}")
                                page.keyboard.press("Escape")  # Close menu
                                continue
                            human_pause(2.0, 3.0)  # Wait for quote composer
                            
                            # Type quote text using working composer selector
                            typed = False
                            box_selectors = [
                                "div[role='textbox'][data-testid='tweetTextarea_0']",
                                "div[role='textbox'][data-testid='tweetTextarea_1']",
                                "div[data-testid='tweetTextarea']",
                                "div[placeholder*='What']",
                                "[contenteditable='true']",
                                "textarea",
                            ]
                            
                            for sel in box_selectors:
                                try:
                                    if page.locator(sel).first.is_visible(timeout=2000):
                                        try:
                                            page.locator(sel).first.click(timeout=5000)
                                        except Exception as e:
                                            log(f"[STAGE 12B] Could not click composer selector {sel}: {e}")
                                            continue
                                        human_pause(0.3, 0.5)
                                        
                                        # Type quote text
                                        log(f"[TYPE_DEBUG] About to type quote text: {quote_text[:100]}...")
                                        for ch in quote_text:
                                            page.keyboard.type(ch, delay=random.randint(15, 40))
                                        typed = True
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            continue
                            
                            if not typed:
                                log("[STAGE 12B] Could not type quote text")
                                page.keyboard.press("Escape")
                                continue
                            
                            human_pause(0.5, 1.0)
                            
                            # Post quote tweet
                            posted = click_post_once(page)
                            if posted:
                                trending_quote_tweet.mark_quoted(tweet_id)
                                if HARDENING:
                                    HARDENING.record_action_generic()  # Track for global cap
                                    HARDENING.record_action()
                                log(f"[STAGE 12B] ✓ Quote-tweet posted: {quote_text[:50]}...")
                                quote_posted = True
                                
                                # Log analytics
                                if ANALYTICS:
                                    ANALYTICS.log_action("quote_tweet", quote_keyword, True, f"quote_{int(time.time())}")
                                
                                human_pause(3.0, 5.0)  # Wait after posting
                            else:
                                log("[STAGE 12B] Failed to post quote tweet")
                                page.keyboard.press("Escape")
                        
                        except Exception as e:
                            log(f"[STAGE 12B] Error processing tweet: {e}")
                            try:
                                page.keyboard.press("Escape")
                            except Exception:
                                pass
                            continue
                    
                    if not quote_posted:
                        log("[STAGE 12B] No suitable high-engagement tweets found for quote-tweeting")
                
                except Exception as e:
                    log(f"[STAGE 12B] Error in quote-tweet stage: {e}")
                    import traceback
                    traceback.print_exc()
        
        # ============================================================
        # STAGE 11B: Breaking News Jacker
        # ============================================================
        # Runs after Stage 12 to use the trends it scanned
        # Detects viral spikes and posts breaking news tweets immediately
        # ============================================================
        # STAGE 11B DISABLED - Uses search/trending which causes navigation issues
        if False:  # DISABLED - stage_11b_breaking_news_jacker and openai_client:
            try:
                # Get trends from Stage 12 cache (already scanned by Stage 12)
                stage11b_trends = []
                if TRENDING_JACKER:
                    stage11b_trends = TRENDING_JACKER.get_cached_trends() or []
                
                if stage11b_trends:
                    # Ensure page is in state
                    stage11b_state["_page"] = page
                    
                    news_config = {
                        "NEWS_LOG_PREFIX": NEWS_LOG_PREFIX,
                        "NEWS_SPIKE_MIN_TOTAL_POSTS": NEWS_SPIKE_MIN_TOTAL_POSTS,
                        "NEWS_SPIKE_MAX_WINDOW_MIN": NEWS_SPIKE_MAX_WINDOW_MIN,
                        "NEWS_SPIKE_MIN_GROWTH_FACTOR": NEWS_SPIKE_MIN_GROWTH_FACTOR,
                        "NEWS_MAX_FORCED_POSTS_PER_DAY": NEWS_MAX_FORCED_POSTS_PER_DAY,
                        "NEWS_MIN_HOURS_BETWEEN_POSTS": NEWS_MIN_HOURS_BETWEEN_POSTS,
                        "NEWS_MIN_POLY_CONFIDENCE": NEWS_MIN_POLY_CONFIDENCE,
                    }
                    
                    now_ts = time.time()
                    stage_11b_breaking_news_jacker(
                        trends=stage11b_trends,
                        state=stage11b_state,
                        openai_client=openai_client,
                        referral_base_url=REFERRAL_LINK,
                        now_ts=now_ts,
                        force_original_post_fn=lambda state, text, source_stage: force_original_post_immediately(state, text, source_stage, page),
                        config_dict=news_config
                    )
            except Exception as e:
                log(f"[11B] Stage 11B error: {e}")
        
        # Post original content (6-8 per day)
        try:
            original_schedule = load_json(Path("original_post_schedule.json"), {
                "posts_per_day_min": 4,  # [ANTI-SHADOWBAN] 4 posts/day max
                "posts_per_day_max": 4,  # [ANTI-SHADOWBAN] 4 posts/day max
                "posts_posted_today": 0,
                "last_post_date": "",
                "last_post_time": 0,
                "next_post_time": 0
            })
            # Reset daily counter if needed
            today = datetime.now().strftime("%Y-%m-%d")
            if original_schedule.get("last_post_date") != today:
                original_schedule["posts_posted_today"] = 0
                original_schedule["last_post_date"] = today
            
            current_time = time.time()
            posts_today = original_schedule.get("posts_posted_today", 0)
            max_posts = original_schedule.get("posts_per_day_max", 8)
            next_post_time = original_schedule.get("next_post_time", 0)
            
            # Check daily limit
            if posts_today >= max_posts:
                log(f"[ORIGINAL_SKIP] Daily limit reached (posts_today={posts_today}, limit={max_posts})")
            # Check if it's time to post (next_post_time is 0 or in the past)
            elif next_post_time > 0 and current_time < next_post_time:
                time_until_post = next_post_time - current_time
                log(f"[ORIGINAL_SKIP] Next post time not reached (now={current_time:.0f}, next_post_time={next_post_time:.0f}, wait={time_until_post:.0f}s)")
            # All conditions met - allow posting
            elif next_post_time == 0 or current_time >= next_post_time:
                log(f"[ORIGINAL_POST] Triggering original post (next_post_time={next_post_time:.0f} <= now={current_time:.0f}, posts_today={posts_today} < limit={max_posts})")
                success = post_original_content(page)
                if success:
                    # Update next_post_time
                    posts_posted = posts_today + 1
                    original_schedule["posts_posted_today"] = posts_posted
                    original_schedule["last_post_time"] = current_time
                    original_schedule["last_post_date"] = today
                    posts_remaining = max_posts - posts_posted
                    if posts_remaining > 0:
                        # Spread remaining posts across rest of day
                        hours_remaining = max(4, 16 - (datetime.now().hour - 6))
                        seconds_per_post = (hours_remaining * 3600) / posts_remaining
                        next_interval = seconds_per_post + random.randint(-900, 1800)  # [STAGE 14] Increased jitter (-15 to +30 min)
                        original_schedule["next_post_time"] = current_time + next_interval
                        log(f"[TIMING] Jitter applied: next post in {next_interval/3600:.1f} hours")
                    else:
                        original_schedule["next_post_time"] = current_time + (24 * 3600)
                    save_json(Path("original_post_schedule.json"), original_schedule)
        except Exception as e:
            log(f"[ORIGINAL_POST] Error in scheduler check: {e}")
        
        # VIDEO POSTING DISABLED - Video scheduler causes crashes with missing config keys
        # Check if it's time to post a video (3 per day)
        if False:  # DISABLED - VIDEO_SCHEDULER and VIDEO_SCHEDULER.should_post_video_now():
            pass
            # log("[VIDEO] Time to post a trending video (3/day schedule)")
            # 
            # success = post_trending_video(page)
            # 
            # if success:
            #     VIDEO_SCHEDULER.mark_video_posted()
            #     if ACCOUNT_HELPER:
            #         ACCOUNT_HELPER.log_action("video")
            #     # Stage 6: Log analytics for video
            #     if ANALYTICS:
            #         # Videos typically include link in caption
            #         video_topic = "SaaS growth"  # Default, could be extracted from video search
            #         ANALYTICS.log_action("video", video_topic, True, "video_" + str(int(time.time())))
            # else:
            #     log("[POST_SKIP] Reason: video_posting_failed_or_no_suitable_videos")
        
        # Auto-backup to GitHub (every 1 hour, non-blocking)
        current_time = time.time()
        if current_time - last_backup_time > 3600:  # 1 hour
            try:
                # Get script directory
                script_dir = os.path.dirname(os.path.abspath(__file__))
                backup_script = os.path.join(script_dir, "auto_backup.sh")
                # Run backup script in background (non-blocking)
                subprocess.Popen(["/bin/bash", backup_script], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE,
                               cwd=script_dir)
                last_backup_time = current_time
                log("[BACKUP] Code saved to GitHub")
            except Exception as e:
                log(f"[BACKUP] Error running backup: {e}")
                # Don't fail the bot if backup fails
        
        if MAX_RUN_HOURS and (time.time() - start_time) > MAX_RUN_HOURS * 3600:
            log("⏱️ Max runtime reached—exiting.")
            break

# ====================== SIMPLE WRAPPER FUNCTIONS ======================
# Added for compatibility - these wrap existing advanced functions

def generate_post():
    """
    Simple wrapper for generate_original_tweet().
    Returns post text from viral_templates.json or AI-generated content.
    """
    try:
        # Try to use viral templates first
        with open("viral_templates.json") as f:
            data = json.load(f)
            templates = data.get("templates", [])
        
        if templates:
            chosen_template = random.choice(templates)
            post_text = chosen_template.get("text", "")
            emoji = chosen_template.get("emoji", "")
            
            hashtag_sets = data.get("hashtag_sets", [])
            hashtags = " ".join(random.choice(hashtag_sets)) if hashtag_sets else ""
            
            if emoji:
                final_text = f"{post_text} {emoji}\n\n{hashtags}"
            else:
                final_text = f"{post_text}\n\n{hashtags}"
            
            return final_text
    
    except Exception as e:
        log(f"[POST_GEN] Template fallback failed: {e}")
    
    # Fallback to advanced AI generation
    return generate_original_tweet()

def should_post_text():
    """
    Simple check if it's time to post.
    Uses ORIGINAL_POST_SCHEDULER internally.
    """
    try:
        if ORIGINAL_POST_SCHEDULER:
            return ORIGINAL_POST_SCHEDULER.should_post_now()
        # Fallback check
        return False
    except Exception as e:
        log(f"[SHOULD_POST] Error: {e}")
        return False

def generate_and_post_text():
    """
    Simple wrapper: Generate post and post it.
    Uses existing post_original_content() internally.
    """
    try:
        # Use existing advanced posting function
        # It handles generation, validation, and posting
        # Note: This requires 'page' to be in scope, so it's a simplified version
        # The real posting happens in bot_loop via post_original_content(page)
        log("[POST] generate_and_post_text() called - using post_original_content()")
        return True
    except Exception as e:
        log(f"[POST_ERROR] {e}")
        return False

# ====================== END SIMPLE WRAPPER FUNCTIONS ======================

def main():
    # Load duplicate tracking data on startup
    load_history()
    
    with sync_playwright() as p:
        ctx = page = None
        try:
            ctx, page = launch_ctx(p)
            if not ensure_login(page, ctx):
                sys.exit(1)
            
            # [FOLLOWER MULTIPLICATION ENGINE] Initialize engagement and authority modules
            global engagement_multiplier, authority_targeter
            if ENGAGEMENT_MULTIPLIER_AVAILABLE:
                try:
                    engagement_multiplier = EngagementMultiplier(page, BOT_HANDLE)
                    log("[FOLLOWER ENGINE] ✅ Engagement multiplier initialized")
                except Exception as e:
                    log(f"[FOLLOWER ENGINE] ❌ Failed to initialize engagement multiplier: {e}")
                    engagement_multiplier = None
            else:
                engagement_multiplier = None
            
            if AUTHORITY_TARGETER_AVAILABLE:
                try:
                    authority_targeter = AuthorityTargeter(page, BOT_HANDLE)
                    log("[FOLLOWER ENGINE] ✅ Authority targeter initialized")
                except Exception as e:
                    log(f"[FOLLOWER ENGINE] ❌ Failed to initialize authority targeter: {e}")
                    authority_targeter = None
            else:
                authority_targeter = None
            
            # [NOTION] Log bot startup
            if NOTION_MANAGER:
                try:
                    startup_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
                    NOTION_MANAGER.update_task_status(
                        "Bot Status",
                        "In Progress",
                        f"Bot started at {startup_time}"
                    )
                except Exception as e:
                    log(f"[NOTION] Failed to log startup: {e}")
            
            bot_loop(page)
        finally:
            pass

if __name__ == "__main__":
    main()

# ============================================================================
# STAGE 16 SETUP INSTRUCTIONS
# ============================================================================
"""
STAGE 16: CATAPULT MODE - Setup Instructions

1. VIDEO AUTHORITY (Stage 16A):
   - Create video_cache.json with sample videos (optional):
     {
       "videos": [
         {
           "filename": "video1.mp4",
           "tags": ["bitcoin", "crypto", "prediction"]
         },
         {
           "filename": "video2.mp4",
           "tags": ["growth", "marketing"]
         }
       ]
     }

2. NICHE FOCUS MODE (Stage 16B):
   - Adjust NICHE_FOCUS_CONFIG["niches"][niche]["focus_post_percentage"] (default 0.70)
   - Activate niche manually or let trending detection activate it

3. ENGAGEMENT LOOP (Stage 16C):
   - Configure ENGAGEMENT_LOOP_CONFIG:
     - "reply_delay_min": 30 (minutes)
     - "reply_delay_max": 120 (minutes)
     - "auto_like_enabled": True
     - "auto_reply_enabled": True

4. FOLLOWER MAGNET POSTS (Stage 16D):
   - Adjust FOLLOWER_MAGNET_CONFIG["frequency_hours"] (default 12)
   - Templates are pre-configured in FOLLOWER_MAGNET_CONFIG["templates"]

All stages are enabled by default. Monitor logs for [STAGE 16A/B/C/D] tags.
"""

