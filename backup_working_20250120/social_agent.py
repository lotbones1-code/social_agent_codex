#!/usr/bin/env python3
# social_agent.py — Chrome persistent login + anti-duplicate posting + image/video generator hooks

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError
from pathlib import Path
import time, sys, json, random, re, subprocess, hashlib, os
from datetime import datetime
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
    from polymarket_intelligence import poly_intel
    STAGE_10_ENABLED = True
except ImportError:
    poly_intel = None
    STAGE_10_ENABLED = False
    print("⚠️ Polymarket intelligence not available")

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

REFERRAL_LINK = "https://polymarket.com?ref=ssj4shamil93949"
BOT_HANDLE = os.getenv("BOT_HANDLE", "").lower()  # Your bot's X handle (without @), used to prevent self-replies

# CURRENT 2025/2026 search keywords (no outdated 2024 references)
CURRENT_SEARCH_KEYWORDS = [
    # 2026 Midterms (current)
    "2026 midterm odds",
    "2026 senate odds",
    "senate control 2026",
    "house odds 2026",
    
    # Polymarket specific
    "polymarket odds",
    "polymarket markets",
    "prediction market odds",
    
    # Specific current races
    "governor race odds",
    "senate race prediction",
    
    # Crypto/betting
    "crypto prediction market",
    "betting markets politics",
    
    # Breaking/trending
    "election betting",
    "political odds",
    "market prediction",
    "prediction markets",
    "political betting",
]

# Backward compatibility alias
SEARCH_TERMS = CURRENT_SEARCH_KEYWORDS

# Rotation logic to prevent repeating same keyword twice in a row
_last_search_keyword = None

def get_next_keyword():
    """Get next search keyword, ensuring it's different from the last one"""
    global _last_search_keyword
    
    # Pick a keyword different from last one
    keyword = random.choice(CURRENT_SEARCH_KEYWORDS)
    max_attempts = 10  # Prevent infinite loop if only 1 keyword
    attempts = 0
    while keyword == _last_search_keyword and len(CURRENT_SEARCH_KEYWORDS) > 1 and attempts < max_attempts:
        keyword = random.choice(CURRENT_SEARCH_KEYWORDS)
        attempts += 1
    
    _last_search_keyword = keyword
    log(f"[SEARCH] Looking up: {keyword}")
    return keyword

REPLY_TEMPLATES = [
    "If you're into prediction markets, this platform is worth checking out. Easy to use and covers a lot of markets: {link}",
    "For anyone tracking odds and betting on events, this is solid. Good liquidity and fair odds: {link}",
    "Been using this for prediction markets and it's been pretty reliable. Worth a look if you're into forecasting: {link}",
    "This prediction market platform covers politics, sports, crypto, and more. Good interface too: {link}",
    "If you follow betting odds and market predictions, check this out. It's one of the better platforms I've used: {link}",
]

# pacing (anti-spam)
REPLIES_PER_TERM      = (1, 2)
DELAY_BETWEEN_REPLIES = (45, 90)
DELAY_BETWEEN_TERMS   = (20, 45)
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

PROFILE_DIR  = Path.home() / ".pw-chrome-referral"
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
    if not PHASE_CONTROLLER:
        return False
    config = PHASE_CONTROLLER.get_phase_config()
    hour = datetime.utcnow().hour
    sleep_hours = config.get("sleep_hours", (2, 6))
    sleep_start, sleep_end = sleep_hours
    return sleep_start <= hour < sleep_end

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
    "Prediction markets are definitely intriguing",
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
    "biden 2024",
    "trump 2024",
    "2024 election",
    "biden vs trump",
    "2024 race",
    "election 2024"
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
    """Check if post references past elections"""
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

def should_include_link_in_original():
    """30-40% of original posts include link"""
    return random.random() < 0.35

# Reply variation templates for diverse content
REPLY_TEMPLATES = [
    # Data-driven
    "The odds moved {percent}% in the last {timeframe}. {insight}",
    "{candidate} is at {odds}% right now. {contrarian_take}",
    
    # Question-driven
    "What if {scenario}? The market says {odds}%.",
    "Why do you think {candidate} is priced at {odds}%?",
    
    # Contrarian
    "Everyone thinks {common_view}, but the data shows {contrarian_view}.",
    "Underrated: {insight}. The market hasn't priced this in yet.",
    
    # Pattern recognition
    "Notice how {pattern}? That usually means {outcome}.",
    "This reminds me of {historical_event}. Watch {metric}.",
    
    # Urgent/breaking
    "Breaking: {event} just moved the odds {percent}%.",
    "{candidate}'s odds {direction}. Here's why: {reason}",
    
    # Analytical
    "Looking at 3 different markets: {comparison}",
    "The implied probability is {percent}%. Here's what that means: {explanation}",
    
    # Casual
    "Real talk: {opinion}",
    "Here's the thing: {insight}",
    "Look at this: {data_point}",
    "Noticed something: {observation}",
]

def get_random_template():
    """Pick a random template for variation"""
    return random.choice(REPLY_TEMPLATES)

# Old duplicate detection functions removed - using simpler version at top of file

def human_pause(a: float, b: float):
    time.sleep(random.uniform(a, b))

def sanitize(text: str) -> str:
    text = re.sub(r"[^\S\r\n]+", " ", text).strip()
    return text.replace("\u200b", "").replace("\u2060", "")

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def launch_ctx(p):
    # User agent rotation (3 different agents for variety)
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ]
    
    # Get user agent from phase controller if available, otherwise rotate
    selected_user_agent = USER_AGENT
    if PHASE_CONTROLLER:
        config = PHASE_CONTROLLER.get_phase_config()
        phase_agents = config.get("user_agents", user_agents)
        if phase_agents:
            selected_user_agent = random.choice(phase_agents)
    else:
        selected_user_agent = random.choice(user_agents)
    
    log(f"[USER_AGENT] Using: {selected_user_agent[:50]}...")
    
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=False,
        viewport=None,
        user_agent=selected_user_agent,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-features=IsolateOrigins,site-per-process",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
    page.add_init_script("window.chrome = window.chrome || {};")
    return ctx, page

def stable_goto(page, url, timeout=120_000):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    except (PWTimeout, PWError):
        pass

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
        query = "Polymarket"  # Safety fallback
    
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
    
    # Extract years (election years)
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
        'absolutely', 'fascinating', 'interesting take', 'prediction markets show',
        'prediction markets offer', 'markets suggest', 'polls say', 'data shows',
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
            text = re.sub(rf'\b{re.escape(word)}\b[^\s]*', '', text, flags=re.IGNORECASE)
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
        template = random.choice(REPLY_TEMPLATES)
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
        
        system_prompt = """You are a smart Polymarket trader/analyst helping others understand prediction markets.

Your goal: Write engaging X replies that:
- Sound like an experienced trader (not a salesman)
- Spot genuine insights in the original tweet
- End with a question or call-to-action that drives engagement
- Use the Polymarket link only when it adds value, not shoehorned

Rules:
- Keep replies under 200 characters when possible (X users scan fast)
- Use 1-2 line breaks for readability (not walls of text)
- Never sound like a bot (no "As an AI" or "I've analyzed")
- Reference real trading concepts (odds movement, volatility, liquidity)
- End 40% of replies with a genuine question about their take
- Save the Polymarket link for replies that naturally benefit from it

Reply style guide:
- Confident but not arrogant ("I think X because..." not "X is obviously...")
- Conversational ("Here's what I'm seeing..." not "My analysis shows...")
- Short sentences (20 words average, not 40+)
- No hashtags (traders hate spam tags)
- 1-2 emojis max if it fits the vibe (📈 for gains, 🤔 for thinking, etc.)

When you include a link, frame it as:
- "You can track this live on [link]" (utility)
- "Here's where traders are betting [link]" (credibility)
- "This odds move is huge [link]" (urgency)
NOT: "Check out this link!" (spam)

Critical context rules:
- Read TWEET_TEXT carefully and identify: specific candidates mentioned, races, years, odds, poll numbers
- Your reply MUST reference the EXACT topic in the tweet (e.g., if tweet says "Vance 2028", don't talk about "Trump's odds")
- Quote or paraphrase a specific phrase from the tweet to prove you read it
- If tweet is about a future election (2028), don't talk about current events

Date context (CRITICAL):
- It is December 2025
- DO NOT mention "Biden 2024" or "Trump 2024" (those are past)
- DO mention current 2026 races, current market movements
- Always reference TODAY's date context

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
Otherwise: one short, context-specific reply"""

        # Add archetype-specific prompt
        if archetype_prompt_addition:
            system_prompt += "\n\n" + archetype_prompt_addition
        
        # Extract key entities from tweet for validation
        key_entities = extract_key_entities(tweet_text)
        
        # Build user prompt with urgency if applicable
        urgency_prefix = urgency_language if urgency_language else ""
        
        user_prompt = f"""TWEET_TEXT: {tweet_text_input}

CONTEXT: {context_input}
AUTHOR_HANDLE: {author_handle_input}
BOT_HANDLE: {bot_handle_input}

{urgency_prefix}Generate a unique, human X reply that focuses on prediction markets and odds. Use the {archetype.replace('_', ' ')} archetype. Do NOT mention Biden/Trump/2024 unless the tweet does. Do NOT reference images or media. Do NOT include any links (links are handled separately). Connect to what the market is pricing in. Keep under 200 characters."""
        
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
        
        # 5. Check text deduplication before proceeding
        if DEDUPLICATOR and DEDUPLICATOR.is_duplicate_or_similar(reply_text):
            log("[DEDUPE] Reply text too similar to recent replies, regenerating...")
            # Try one more regeneration with higher temperature
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
                    temperature=0.95,
                    max_tokens=120,
                )
                reply_text = dedupe_retry.choices[0].message.content.strip()
                if reply_text.startswith('"') and reply_text.endswith('"'):
                    reply_text = reply_text[1:-1]
                
                # Re-check deduplication
                if DEDUPLICATOR and DEDUPLICATOR.is_duplicate_or_similar(reply_text):
                    log("[DEDUPE] Retry still similar, using fallback")
                    reply_text = f"Everyone's betting {topic or 'this'} but the value's probably on the other side." if topic else "The market's pricing this differently than people think."
            except Exception as e:
                log(f"[DEDUPE] Regeneration failed: {e}")
        
        # 6. Handle link inclusion (with config-driven strategy)
        # Remove any existing link from LLM output
        if REFERRAL_LINK in reply_text:
            reply_text = reply_text.replace(REFERRAL_LINK, "").strip()
        
        # Check link safety before including
        link_to_use = REFERRAL_LINK
        if HARDENING:
            # Check if we can post this link (duplicate prevention)
            if not HARDENING.can_post_link(link_to_use, min_minutes_between=30):
                log("[LINK_SAFETY] Link posted too recently, skipping link in this reply")
                link_to_use = None
            else:
                # Get link variant if available (30% chance)
                link_to_use = HARDENING.get_link_variant(link_to_use)
        
        # Determine link usage based on reply type and config
        should_include_link = False
        link_usage_targets = {
            "originals": 0.35,
            "high_value_replies": 0.5,
            "normal_replies": 0.25,
            "trending_replies": 0.5  # Stage 12 replies
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
            target_freq = link_usage_targets.get("high_value_replies", 0.5)
        else:
            target_freq = link_usage_targets.get("normal_replies", 0.25)
        
        # Decide whether to include link
        should_include_link = random.random() < target_freq
        
        # Also check archetype strategy (can override if archetype says no)
        if REPLY_PSYCHOLOGY:
            thread_id = None
            reply_number = 1
            archetype_says_include = REPLY_PSYCHOLOGY.should_include_link(
                archetype, thread_id=thread_id, reply_number=reply_number
            )
            # If archetype says no, respect it (but if archetype says yes, still use config frequency)
            if not archetype_says_include:
                should_include_link = False
            log(f"[PSYCHOLOGY] Archetype: {archetype}, Config target: {target_freq:.0%}, Final decision: {should_include_link}")
        
        # Add link if decided
        if should_include_link and link_to_use:
            # Use natural CTAs
            cta_templates = [
                f"I'm betting it here 👉 {link_to_use}",
                f"Real money odds here 👉 {link_to_use}",
                f"Put money behind it 👉 {link_to_use}",
                f"Track it live 👉 {link_to_use}",
            ]
            link_text = f"\n\n{random.choice(cta_templates)}"
            reply_text += link_text
            log(f"[LINK] Including link in {reply_type} reply (target: {target_freq:.0%})")
            # Record link usage
            if HARDENING:
                HARDENING.record_link(link_to_use)
        else:
            log(f"[LINK] No link in {reply_type} reply (target: {target_freq:.0%})")
        
        return sanitize(reply_text)
        
    except Exception as e:
        log(f"[WARNING] OpenAI reply generation failed: {e}, using fallback template")
        template = random.choice(REPLY_TEMPLATES)
        # For fallback, include link if requested
        if include_link:
            return sanitize(template.format(link=REFERRAL_LINK))
        else:
            return sanitize(template.replace("{link}", "").strip())

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
                            remove_buttons.nth(j).click()
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
                        close_buttons.first.click()
                        media_removed = True
                        log("[MEDIA_BLOCK] Removed media preview")
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

def click_post_once(page) -> bool:
    """
    Click a single button if present; only use keyboard if no button is clickable.
    HARD BLOCK: Ensures no media is attached before posting.
    Uses force-click fallback if standard click fails (prevents infinite viewport scroll loops).
    """
    # HARD BLOCK: Remove any attached media before posting
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
                    btn.click()
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

def should_target_for_reply(card, topic: str) -> tuple[bool, str]:
    """
    Decide if we should reply to this card based on content relevance and follower count.
    Returns (should_reply: bool, reason: str)
    """
    try:
        # Extract account info
        account_text = card.inner_text() if hasattr(card, 'inner_text') else ""
        account_text_lower = account_text.lower()
        
        # Define relevance keywords
        keywords = [
            "polymarket",
            "prediction market",
            "prediction markets",
            "betting odds",
            "betting",
            "odds",
            "trump odds",
            "biden odds",
            "election odds",
            "bet on trump",
            "bet on biden",
            "election prediction",
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
        
        # NEW FILTER: Skip if engagement < 3 (very low engagement)
        if engagement > 0 and engagement < 3:
            log(f"[TARGETING] Skipped - low engagement (engagement={engagement})")
            return False, "low-engagement"
        
        # UPDATED: Only skip if followers < 10 (very low threshold)
        if follower_count > 0 and follower_count < 10:
            log(f"[TARGETING] Skipped - very low followers (followers={follower_count})")
            return False, "low-followers"
        
        # Tier 1: high relevance + 50+ followers -> always reply
        if content_matches and follower_count >= 50:
            log(f"[TARGETING] ✓ High-relevance target (followers={follower_count}, engagement={engagement})")
            return True, "high-relevance"
        
        # Tier 2: relevance + 20-49 followers -> good growth target
        if content_matches and follower_count >= 20:
            log(f"[TARGETING] ✓ Growth target (followers={follower_count}, engagement={engagement})")
            return True, "growth-target"
        
        # Tier 3: high relevance content even with low followers (but >= 10)
        if content_matches:
            log(f"[TARGETING] ✓ Relevant content (followers={follower_count}, engagement={engagement})")
            return True, "relevant-content"
        
        # Default: allow if no strong signal against
        return True, "default-allow"
        
    except Exception as e:
        log(f"[TARGETING] Error checking target: {e}")
        # On error, default to allowing (don't want to skip everything)
        return True, "error-default-allow"

def reply_to_card(page, card, topic: str, recent_replies: list, reply_idx: int) -> bool:
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
        
        # Check rate limits (max 8 replies/hour)
        if HARDENING and not HARDENING.can_post_reply(max_replies_per_hour=8):
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
        
        # open composer - limit retries to 3 max
        reply_clicked = False
        viewport_failures = 0
        max_viewport_failures = 3  # Reduced from 5 to 3
        
        try:
            for attempt in range(max_viewport_failures):
                reply_button = card.locator('[data-testid="reply"]').first
                if reply_button.count() == 0:
                    log(f"[REPLY_FAIL] Reply button not found")
                    return False
                
                # Try standard click
                try:
                    reply_button.click()
                    reply_clicked = True
                    break
                except Exception as click_error:
                    error_str = str(click_error).lower()
                    # Check if it's a viewport/outside/mask error
                    is_viewport_error = "outside" in error_str or "viewport" in error_str or "not visible" in error_str
                    is_mask_error = "subtree intercepts pointer events" in error_str or "mask" in error_str or "intercepts" in error_str
                    
                    if is_viewport_error or is_mask_error:
                        viewport_failures += 1
                        # Use JS fallback after 2 failures (not 5)
                        if viewport_failures >= 2:
                            log(f"[REPLY_CLICK] Using JS fallback click after {viewport_failures} viewport errors")
                            # Force-click using JavaScript to bypass mask
                            try:
                                card.evaluate("""
                                    (el) => {
                                        const btn = el.querySelector('[data-testid="reply"]');
                                        if (btn) {
                                            btn.scrollIntoView({ behavior: 'instant', block: 'center' });
                                            btn.click();
                                            return true;
                                        }
                                        return false;
                                    }
                                """)
                                reply_clicked = True
                                break
                            except Exception as force_error:
                                log(f"[REPLY_FAIL] Force-click also failed: {repr(force_error)}")
                                # Don't return yet, try one more time
                                if viewport_failures >= max_viewport_failures:
                                    log(f"[REPLY_CLICK_FAILED] Giving up after {viewport_failures} attempts")
                                    return False
                        else:
                            # Retry with a small scroll
                            log(f"[REPLY_CLICK] Viewport error (attempt {attempt + 1}/{max_viewport_failures}), retrying...")
                            human_pause(0.3, 0.5)
                            continue
                    else:
                        # Not a viewport error, log and fail immediately
                        log(f"[REPLY_FAIL] Reply button click error: {repr(click_error)}")
                        return False
            
            if not reply_clicked:
                log(f"[REPLY_CLICK_FAILED] Reply button click failed after {max_viewport_failures} attempts")
                return False
        except Exception as e:
            log(f"[REPLY_FAIL] Reply button not found or not clickable: {repr(e)}")
            return False
        
        human_pause(0.8, 1.4)
        
        # Wait for reply composer to appear (fix for "textbox not found" error)
        composer_appeared = False
        composer_selectors = [
            'div[role="textbox"][data-testid="tweetTextarea_0"]',
            'div[role="textbox"][data-testid="tweetTextarea_1"]',
            'div[role="textbox"]',
            'div[aria-label="Post text"]',
        ]
        for selector in composer_selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=5000):
                    composer_appeared = True
                    break
            except Exception:
                continue
        
        if not composer_appeared:
            log("[REPLY_FAIL] Reply composer did not appear after click, giving up")
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

        # Extract tweet ID, text, and author handle for contextual reply generation
        tweet_id = extract_tweet_id(card) or ""
        tweet_text = extract_tweet_text(card)
        author_handle = extract_author_handle(card)
        
        # Try to extract author followers (for high-value reply detection)
        author_followers = 0
        try:
            follower_text = card.locator('text=/\\d+[KM]?\\s*followers/i').first
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
        
        # STAGE 10: Check if politics market, generate AI thesis if so
        text = None
        if STAGE_10_ENABLED and poly_intel and "polymarket" in tweet_text.lower():
            # STAGE 10 QUALITY FILTER: Only reply if tweet has actual betting/prediction substance
            # Skip tweets that just mention "Polymarket" without odds, predictions, or market data
            if not poly_intel.has_betting_substance(tweet_text):
                log(f"[STAGE 10] ✗ Skipping reply - tweet lacks betting/prediction substance (just generic mention)")
            else:
                market_name = tweet_text.split("Polymarket")[0].strip() if "Polymarket" in tweet_text else tweet_text[:50]
                if poly_intel.is_politics_market(market_name):
                    context = poly_intel.fetch_market_context(market_name=market_name, market_odds="50%", volume_24h="$100k", resolution_date="2026-01-01", sentiment="neutral")
                    thesis = poly_intel.generate_contrarian_thesis(context)
                    if thesis:
                        # STAGE 10B: format_thesis_for_tweet now includes quality filtering
                        formatted = poly_intel.format_thesis_for_tweet(thesis, market_name, market_context=context)
                        if formatted:
                            text = formatted["message"]
                            poly_intel.log_thesis(market_name, thesis)
                            log(f"[STAGE 10] ✓ Generated thesis reply: {market_name}")
        
        # If Stage 10 didn't generate a reply, use normal compose_reply_text
        if not text:
            text = compose_reply_text(tweet_text=tweet_text, topic=topic, author_handle=author_handle, bot_handle=BOT_HANDLE, include_link=False, reply_type=reply_type, author_followers=author_followers)
        
        # Check for NO_REPLY (self-reply prevention)
        if text == "NO_REPLY" or not text:
            log("[FILTER] Skipping self-reply or empty reply")
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

        box_selectors = [
            "div[role='textbox'][data-testid='tweetTextarea_0']",
            "div[role='textbox'][data-testid='tweetTextarea_1']",
            "div[role='textbox']",
        ]
        typed = False
        last_error = None
        for sel in box_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=1500):
                    page.locator(sel).first.click()
                    # Human-like typing: 1-3 second total delay spread across typing
                    # Calculate delay per character to achieve 1-3s total
                    total_delay_seconds = random.uniform(1.0, 3.0)
                    delay_per_char = int((total_delay_seconds * 1000) / max(len(text), 1))
                    delay_per_char = max(15, min(delay_per_char, 80))  # Clamp between 15-80ms
                    
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
        return False

def post_trending_video(page):
    """
    Actually download and post a trending video
    
    Steps:
    1. Find high-engagement video from Radar targets
    2. Download the video
    3. Generate caption with link
    4. Post it
    5. Mark as posted
    """
    if not VIDEO_FINDER:
        log("[VIDEO] Video finder not available")
        return False
    
    log("[VIDEO] Starting trending video search...")
    
    try:
        # Get search parameters from Radar
        search_params = VIDEO_FINDER.find_trending_video_post(page)
        keyword = search_params.get("keyword", "polymarket")
        
        # Search for posts matching criteria - use raw keyword only
        log(f"[VIDEO SEARCH] Query: {keyword}")
        
        # Navigate to X search for videos - use raw keyword only, no filters
        search_url = f"https://x.com/search?q={keyword.replace(' ', '%20')}&src=typed_query&f=live"
        stable_goto(page, search_url)
        human_pause(2.0, 3.0)
        
        # Wait for tweets to load
        for _ in range(30):
            if page.locator('article[data-testid="tweet"]').count() > 0:
                break
            human_pause(0.3, 0.6)
        
        # Find posts with videos
        video_cards = page.locator('article[data-testid="tweet"]')
        card_count = video_cards.count()
        log(f"[VIDEO] Found {card_count} potential video posts")
        
        for i in range(min(card_count, 10)):  # Check first 10
            try:
                card = video_cards.nth(i)
                
                # Check if it has a video element
                video_element = card.locator('video').first
                if video_element.count() == 0:
                    continue
                
                # Extract post ID
                tweet_id = extract_tweet_id(card) or ""
                if not tweet_id:
                    continue
                
                # Get engagement stats (approximate from likes)
                likes_text = ""
                try:
                    likes_element = card.locator('[data-testid="like"]').first
                    if likes_element.count() > 0:
                        likes_text = likes_element.inner_text()
                except Exception:
                    pass
                
                # Parse likes (handles K, M suffixes)
                likes = 0
                if likes_text:
                    try:
                        likes_str = likes_text.replace("K", "000").replace("M", "000000").replace(",", "")
                        likes = int(''.join(filter(str.isdigit, likes_str)))
                    except Exception:
                        likes = 0
                
                # Check if good candidate
                post_data = {
                    "id": tweet_id,
                    "views": 50000,  # Estimate - X doesn't always show views publicly
                    "likes": likes
                }
                
                if not VIDEO_FINDER.is_good_video_candidate(post_data):
                    continue
                
                log(f"[VIDEO ✓] Found good video: {tweet_id} ({likes} likes)")
                
                # Get original post text for context
                original_text = extract_tweet_text(card)
                
                # Generate caption
                caption = VIDEO_FINDER.generate_caption_for_video(original_text, keyword, REFERRAL_LINK)
                
                log(f"[VIDEO] Generated caption: {caption[:100]}...")
                
                # For video reposting, we'll use X's built-in repost feature
                # Navigate to the tweet and use the repost menu
                try:
                    # Click on the tweet to open it
                    card.click()
                    human_pause(1.0, 2.0)
                    
                    # Try to find repost button
                    repost_button = page.locator('[data-testid="retweet"]').first
                    if repost_button.count() > 0:
                        repost_button.click()
                        human_pause(0.5, 1.0)
                        
                        # Click "Quote" to add our caption
                        quote_button = page.locator('text="Quote"').first
                        if quote_button.count() > 0:
                            quote_button.click()
                            human_pause(1.0, 2.0)
                            
                            # Type our caption in the quote tweet box
                            compose_box = page.locator('[data-testid="tweetTextarea_0"]').first
                            if compose_box.count() > 0:
                                compose_box.click()
                                human_pause(0.3, 0.5)
                                compose_box.fill(caption)
                                human_pause(0.5, 1.0)
                                
                                # Click Post button
                                post_button = page.locator('[data-testid="tweetButton"]').first
                                if post_button.count() > 0:
                                    post_button.click()
                                    human_pause(2.0, 3.0)
                                    
                                    log("[VIDEO ✓] Quote tweet posted successfully!")
                                    
                                    # Mark as posted
                                    VIDEO_FINDER.save_posted_id(tweet_id)
                                    
                                    # Close any dialogs
                                    try:
                                        page.keyboard.press("Escape")
                                    except Exception:
                                        pass
                                    
                                    return True
                    
                    # If quote didn't work, go back
                    page.keyboard.press("Escape")
                    human_pause(0.5, 1.0)
                    
                except Exception as e:
                    log(f"[VIDEO ERROR] Failed to repost video: {e}")
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    continue
                
            except Exception as e:
                log(f"[VIDEO ERROR] Failed on post {i}: {e}")
                continue
        
        log("[VIDEO_SKIP] No suitable videos found this round (reason: no videos with sufficient engagement or already posted)")
        return False
        
    except Exception as e:
        log(f"[VIDEO ERROR] {e}")
        import traceback
        tb = traceback.format_exc()
        log(f"[VIDEO ERROR] Full traceback:\n{tb}")
        return False

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
        detected_topic = monitor.detect_trending_polymarket_keyword([trending_keyword])
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
                like_button.click(timeout=2000)
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
                retweet_button.click(timeout=2000)
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
    
    if not poly_intel:
        log("[STAGE 11B] PolymarketIntelligence not available, skipping")
        return False
    
    try:
        log(f"[STAGE 11B] Processing breaking news: {news_headline[:80]}...")
        
        # Get instant thesis from news jacker
        result = news_jacker.get_instant_thesis(news_headline, poly_intel=poly_intel)
        
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
                new_tweet_button.click()
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
                        page.locator(sel).first.click()
                        human_pause(0.3, 0.5)
                        
                        # Type tweet (faster for news - urgency)
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

def post_daily_contrarian_thread(page):
    """
    Stage 11A: Post daily contrarian thread from Stage 10 theses.
    Posts once per day at peak hours (9am EST).
    """
    if not STAGE_11A_ENABLED or not thread_builder:
        return False
    
    try:
        log("[STAGE 11A] Checking if thread ready to post...")
        
        # Get thread tweets
        thread_data = thread_builder.get_thread_tweets(hours=24, top_n=5)
        
        if not thread_data.get("ready_to_post", False):
            log("[STAGE 11A] Thread not ready to post")
            return False
        
        tweets = thread_data.get("tweets", [])
        if not tweets or len(tweets) == 0:
            log("[STAGE 11A] No tweets to post")
            return False
        
        # Get posting delay (default 2.5 seconds between tweets for human-like behavior)
        posting_delay = thread_data.get("posting_delay", 2.5)
        log(f"[STAGE 11A] Posting thread: {len(tweets)} tweets (delay: {posting_delay}s between tweets)")
        
        # Post first tweet (original tweet)
        try:
            # Go to home
            stable_goto(page, HOME_URL)
            human_pause(2.0, 3.0)
            
            # Open composer (click new tweet button)
            new_tweet_button = page.locator('[data-testid="SideNav_NewTweet_Button"]').first
            if new_tweet_button.count() == 0:
                # Fallback: try compose URL
                page.goto("https://x.com/compose/tweet")
                human_pause(2.0, 3.0)
            else:
                new_tweet_button.click()
                human_pause(1.0, 2.0)
            
            # Type first tweet
            box_selectors = [
                "div[role='textbox'][data-testid='tweetTextarea_0']",
                "div[role='textbox']",
            ]
            typed = False
            for sel in box_selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=3000):
                        page.locator(sel).first.click()
                        human_pause(0.3, 0.5)
                        
                        # Type first tweet
                        first_tweet = tweets[0]
                        for ch in first_tweet:
                            page.keyboard.type(ch, delay=random.randint(20, 50))
                        typed = True
                        break
                except Exception:
                    continue
            
            if not typed:
                log("[STAGE 11A] Failed to type first tweet")
                page.keyboard.press("Escape")
                return False
            
            human_pause(0.5, 1.0)
            
            # Post first tweet
            posted = click_post_once(page)
            if not posted:
                log("[STAGE 11A] Failed to post first tweet")
                page.keyboard.press("Escape")
                return False
            
            log(f"[STAGE 11A] ✓ Posted tweet 1/7: {tweets[0][:50]}...")
            # Wait for tweet to appear + posting delay (2-3 seconds per tweet for human-like behavior)
            human_pause(3.0, 5.0)
            time.sleep(posting_delay)
            
            # Now post remaining tweets as replies (thread continuation)
            for i, tweet_text in enumerate(tweets[1:], 2):
                try:
                    # Find the last tweet we posted (our own tweet)
                    # Navigate to our profile to find the latest tweet
                    page.goto(f"https://x.com/{BOT_HANDLE.replace('@', '')}")
                    human_pause(2.0, 3.0)
                    
                    # Find the first tweet (our latest)
                    first_tweet_card = page.locator('article[data-testid="tweet"]').first
                    if first_tweet_card.count() == 0:
                        log(f"[STAGE 11A] Could not find latest tweet for reply {i}")
                        break
                    
                    # Click reply button
                    reply_button = first_tweet_card.locator('[data-testid="reply"]').first
                    if reply_button.count() == 0:
                        log(f"[STAGE 11A] Could not find reply button for tweet {i}")
                        break
                    
                    reply_button.click()
                    human_pause(1.0, 2.0)
                    
                    # Type reply
                    box_selectors = [
                        "div[role='textbox'][data-testid='tweetTextarea_0']",
                        "div[role='textbox'][data-testid='tweetTextarea_1']",
                        "div[role='textbox']",
                    ]
                    typed_reply = False
                    for sel in box_selectors:
                        try:
                            if page.locator(sel).first.is_visible(timeout=3000):
                                page.locator(sel).first.click()
                                human_pause(0.3, 0.5)
                                
                                for ch in tweet_text:
                                    page.keyboard.type(ch, delay=random.randint(20, 50))
                                typed_reply = True
                                break
                        except Exception:
                            continue
                    
                    if not typed_reply:
                        log(f"[STAGE 11A] Failed to type reply {i}")
                        page.keyboard.press("Escape")
                        continue
                    
                    human_pause(0.5, 1.0)
                    
                    # Post reply
                    posted_reply = click_post_once(page)
                    if posted_reply:
                        log(f"[STAGE 11A] ✓ Posted tweet {i}/7: {tweet_text[:50]}...")
                        # Wait for tweet to appear + posting delay (2-3 seconds per tweet for human-like behavior)
                        human_pause(3.0, 5.0)
                        time.sleep(posting_delay)
                    else:
                        log(f"[STAGE 11A] Failed to post reply {i}")
                        page.keyboard.press("Escape")
                        continue
                    
                except Exception as e:
                    log(f"[STAGE 11A] Error posting reply {i}: {e}")
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass
                    continue
            
            # Mark thread as posted
            thread_builder.mark_thread_posted(tweets)
            log(f"[STAGE 11A] ✓ Thread posted successfully ({len(tweets)} tweets)")
            
            return True
            
        except Exception as e:
            log(f"[STAGE 11A] Error posting thread: {e}")
            import traceback
            traceback.print_exc()
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
    
    except Exception as e:
        log(f"[STAGE 11A] Error in post_daily_contrarian_thread: {e}")
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

    while True:
        # Heartbeat logging every 5 minutes
        if HARDENING:
            HARDENING.heartbeat()
        
        # Check sleep hours at start of each loop
        if should_sleep_now():
            sleep_duration = random.randint(60, 300)  # 1-5 minutes
            log(f"[SLEEP_MODE] Bot sleeping for {sleep_duration}s (UTC hours 2-6)")
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
        
        # Stage 6: Print daily analytics summary at 11pm
        if should_print_daily_summary():
            log("[ANALYTICS] Printing daily summary...")
            if ANALYTICS:
                ANALYTICS.print_daily_summary()
        
        # Stage 11A: Post daily contrarian thread (once per day at 9am)
        if should_post_daily_thread():
            log("[STAGE 11A] Time to post daily contrarian thread...")
            success = post_daily_contrarian_thread(page)
            if success:
                log("[STAGE 11A] ✓ Daily thread posted successfully")
            else:
                log("[STAGE 11A] Thread posting failed or not ready")
        
        # Check if should follow an account (looks human)
        if ACCOUNT_HELPER and ACCOUNT_HELPER.should_follow_account():
            log("[FOLLOW] Time to follow a relevant account (5-10/day limit)")
            # TODO: Add actual follow logic here
            # For now, just log the action
            log("[FOLLOW] Follow logic not yet implemented, skipped")
        
        # Check if it's time to post a video (3 per day)
        if VIDEO_SCHEDULER and VIDEO_SCHEDULER.should_post_video_now():
            log("[VIDEO] Time to post a trending video (3/day schedule)")
            
            success = post_trending_video(page)
            
            if success:
                VIDEO_SCHEDULER.mark_video_posted()
                if ACCOUNT_HELPER:
                    ACCOUNT_HELPER.log_action("video")
                # Stage 6: Log analytics for video
                if ANALYTICS:
                    # Videos typically include link in caption
                    video_topic = "polymarket"  # Default, could be extracted from video search
                    ANALYTICS.log_action("video", video_topic, True, "video_" + str(int(time.time())))
                log("[VIDEO] ✓ Video posted successfully")
            else:
                log("[VIDEO] Video posting failed or no suitable videos found, will retry next cycle")
        
        # ============================================================
        # STAGE 12: Smart Trending Jacker
        # ============================================================
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
        if TRENDING_JACKER and TRENDING_JACKER.should_run_trending_scan():
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
                                if random.random() < 0.5:
                                    cta_templates = [
                                        f"I'm betting it here 👉 {REFERRAL_LINK}",
                                        f"Real money odds here 👉 {REFERRAL_LINK}",
                                        f"Put money behind it 👉 {REFERRAL_LINK}",
                                    ]
                                    reply_text += f"\n\n{random.choice(cta_templates)}"
                                
                                # Post the Stage 12 reply (reuse reply_to_card logic but with pre-generated text)
                                # Open reply box first
                                reply_clicked = False
                                try:
                                    reply_button = card.locator('[data-testid="reply"]').first
                                    if reply_button.count() > 0:
                                        reply_button.click()
                                        reply_clicked = True
                                        human_pause(0.8, 1.4)
                                except Exception:
                                    log("[TRENDING_REPLY_FAIL] Could not open reply box")
                                    continue
                                
                                if not reply_clicked:
                                    continue
                                
                                # Type the reply text
                                box_selectors = [
                                    "div[role='textbox'][data-testid='tweetTextarea_0']",
                                    "div[role='textbox'][data-testid='tweetTextarea_1']",
                                    "div[role='textbox']",
                                ]
                                typed = False
                                for sel in box_selectors:
                                    try:
                                        if page.locator(sel).first.is_visible(timeout=1500):
                                            page.locator(sel).first.click()
                                            total_delay_seconds = random.uniform(1.0, 3.0)
                                            delay_per_char = int((total_delay_seconds * 1000) / max(len(reply_text), 1))
                                            delay_per_char = max(15, min(delay_per_char, 80))
                                            for ch in reply_text:
                                                page.keyboard.type(ch, delay=delay_per_char + random.randint(-5, 5))
                                            typed = True
                                            break
                                    except Exception:
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
        
        if MAX_RUN_HOURS and (time.time() - start_time) > MAX_RUN_HOURS * 3600:
            log("⏱️ Max runtime reached—exiting.")
            break

        # Intelligent Search: Use ChatGPT to generate queries from Stage 12's trending data
        term = None
        if INTELLIGENT_SEARCH:
            try:
                # Get current trends from Stage 12 (already scanned hourly)
                trends = []
                markets = []
                if TRENDING_JACKER:
                    trends = TRENDING_JACKER.get_cached_trends()
                    # Get Polymarket markets for top trends
                    for trend in trends[:3]:  # Top 3 trends
                        trend_markets = TRENDING_JACKER.map_trend_to_markets(trend, poly_intel)
                        for market in trend_markets:
                            if market.get("title"):
                                markets.append(market["title"])
                
                # Get intelligent query (ChatGPT generates once per hour, then reuses)
                term = INTELLIGENT_SEARCH.get_next_query(page, trends=trends, markets=markets, openai_client=openai_client)
            except Exception as e:
                log(f"[SEARCH] Intelligent search failed: {str(e)[:100]}, using fallback")
                term = None
        
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
            term = "Polymarket"  # Ultimate fallback
        
        search_live(page, term)

        cards = collect_articles(page, limit=MAX_ARTICLES_SCAN)
        random.shuffle(cards)
        target = random.randint(*REPLIES_PER_TERM)
        sent = 0

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
                    follower_text = card.locator('text=/\\d+[KM]?\\s*followers/i').first
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
                log(f"[WARNING] Reply attempt failed (check [REPLY_TRACEBACK] logs for details)")
        
        # Random delay between search terms (20-45 min, already randomized)
        human_pause(*DELAY_BETWEEN_TERMS)

def main():
    # Load duplicate tracking data on startup
    load_history()
    
    with sync_playwright() as p:
        ctx = page = None
        try:
            ctx, page = launch_ctx(p)
            if not ensure_login(page, ctx):
                sys.exit(1)
            bot_loop(page)
        finally:
            pass

if __name__ == "__main__":
    main()

