#!/usr/bin/env python3
"""
🔥 VIRAL VIDEO ENGINE (Rebuilt for social_agent_codex)
Finds, scores, and reposts high-velocity viral videos.
"""

import time
import random
import re
import json
import requests
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# --- CONFIGURATION ---
VIRAL_THRESHOLDS = {
    "min_views": 10000,
    "min_likes": 200,
    "min_viral_score": 45.0,  # 0-100 scale
    "max_video_duration": 140 # seconds
}

USED_VIDEOS_PATH = Path("storage/used_viral_videos.json")
VIDEOS_DIR = Path("media/viral_videos")

def log(msg):
    print(f"[VIRAL_ENGINE] {msg}")

def load_used_videos() -> set:
    try:
        if USED_VIDEOS_PATH.exists():
            data = json.loads(USED_VIDEOS_PATH.read_text())
            return set(data.get("urls", []))
    except:
        return set()
    return set()

def save_used_video(url: str):
    try:
        data = {"urls": list(load_used_videos())}
        data["urls"].append(url)
        USED_VIDEOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USED_VIDEOS_PATH.write_text(json.dumps(data, indent=2))
    except Exception as e:
        log(f"Failed to save history: {e}")

def calculate_viral_score(stats: Dict) -> float:
    """
    Calculates Viral Potential Score (0-100)
    Based on Engagement Rate + View Velocity
    """
    views = stats.get("views", 0)
    likes = stats.get("likes", 0)
    replies = stats.get("replies", 0)
    reposts = stats.get("reposts", 0)
    
    if views < 1000: return 0.0
    
    # 1. Engagement Rate (Likes + Reposts + Replies) / Views
    # Benchmark: 5% is viral
    engagement = likes + (reposts * 2) + (replies * 1.5)
    eng_rate = engagement / views
    
    # Score 0-50 based on engagement
    eng_score = min(eng_rate / 0.05, 1.0) * 50
    
    # 2. Raw Impact (0-30 points)
    # Cap at 500k views
    impact_score = min(views / 500000, 1.0) * 30
    
    # 3. Ratio Bonus (0-20 points)
    # High like-to-view ratio means quality
    ratio_score = min((likes / views) / 0.04, 1.0) * 20
    
    total = eng_score + impact_score + ratio_score
    return round(total, 1)

def find_viral_candidates(page, limit: int = 5) -> List[Dict]:
    """Finds videos and scores them."""
    from social_agent import SEARCH_URL, stable_goto, human_pause, extract_account_stats
    
    candidates = []
    used = load_used_videos()
    
    # High-intent search terms
    queries = [
        "breaking news video filter:videos min_faves:500",
        "crypto news video filter:videos",
        "election video filter:videos min_retweets:100",
        "market crash video filter:videos"
    ]
    
    query = random.choice(queries)
    log(f"Searching for: {query}")
    
    try:
        stable_goto(page, SEARCH_URL.format(q=query.replace(" ", "%20")))
        human_pause(3, 5)
        
        cards = page.locator('article[data-testid="tweet"]')
        count = min(cards.count(), 15)
        
        for i in range(count):
            try:
                card = cards.nth(i)
                
                # Must have video
                if card.locator('video').count() == 0: continue
                
                # Get Link
                link_el = card.locator('a[href*="/status/"]').first
                if link_el.count() == 0: continue
                href = link_el.get_attribute("href")
                url = f"https://x.com{href}" if href.startswith("/") else href
                
                if url in used: continue
                
                # Get Stats & Score
                stats = extract_account_stats(card)
                score = calculate_viral_score(stats)
                
                text = card.locator('[data-testid="tweetText"]').inner_text()
                
                if score >= VIRAL_THRESHOLDS["min_viral_score"]:
                    log(f"🔥 FOUND VIRAL CANDIDATE: {score}/100 | {url}")
                    candidates.append({
                        "url": url,
                        "score": score,
                        "text": text,
                        "stats": stats
                    })
            except Exception:
                continue
                
    except Exception as e:
        log(f"Search error: {e}")
        
    # Sort by highest viral score
    return sorted(candidates, key=lambda x: x['score'], reverse=True)[:limit]

def download_viral_video(page, url: str) -> Optional[Path]:
    """Downloads video using browser session cookies."""
    from social_agent import stable_goto, human_pause
    
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"viral_{int(time.time())}.mp4"
    path = VIDEOS_DIR / filename
    
    try:
        stable_goto(page, url)
        human_pause(2, 4)
        
        # 1. Try to extract MP4 URL from network or DOM
        video_src = page.evaluate("""() => {
            const v = document.querySelector('video');
            return v ? v.src : null;
        }""")
        
        if not video_src or "blob:" in video_src:
            log("❌ Could not extract direct video URL (blob detected)")
            return None
            
        # 2. Download using Requests + Cookies
        cookies = {c['name']: c['value'] for c in page.context.cookies()}
        headers = {"User-Agent": page.evaluate("navigator.userAgent"), "Referer": url}
        
        with requests.get(video_src, stream=True, cookies=cookies, headers=headers) as r:
            r.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        if path.exists() and path.stat().st_size > 5000:
            log(f"✅ Downloaded: {filename}")
            return path
            
    except Exception as e:
        log(f"Download failed: {e}")
        
    return None

def run_viral_cycle(page, state):
    """
    MAIN ENTRY POINT: Call this from social_agent.py
    Returns True if video posted, False otherwise.
    """
    log("Starting Viral Video Cycle...")
    
    # 1. Find
    candidates = find_viral_candidates(page)
    if not candidates:
        log("No viral candidates found.")
        return False
        
    # 2. Select Best
    best_video = candidates[0]
    log(f"Selected Best Video: {best_video['score']}/100")
    
    # 3. Download
    video_path = download_viral_video(page, best_video['url'])
    if not video_path:
        save_used_video(best_video['url']) # Skip broken one next time
        return False
        
    # 4. Generate Caption (Simple & Punchy)
    caption = f"This is trending hard right now 📈\n\n{best_video['text'][:100]}...\n\n👇 Watch"
    
    # 5. Post (Uses safe isolated logic)
    try:
        from social_agent import click_post_once, find_file_input, HOME_URL, stable_goto
        
        stable_goto(page, HOME_URL)
        human_pause(2, 3)
        
        page.keyboard.type("n") # Shortcut for new tweet
        human_pause(1, 2)
        
        page.keyboard.type(caption)
        human_pause(1, 2)
        
        file_input = find_file_input(page)
        file_input.set_input_files(str(video_path))
        human_pause(5, 8) # Wait for upload
        
        if click_post_once(page):
            log("🚀 VIRAL VIDEO POSTED SUCCESSFULLY")
            save_used_video(best_video['url'])
            return True
            
    except Exception as e:
        log(f"Posting error: {e}")
        
    return False
