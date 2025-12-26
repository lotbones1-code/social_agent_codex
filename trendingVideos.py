#!/usr/bin/env python3
"""
Trending Video Reposting Module
Finds, downloads, and reposts trending political/prediction market videos from X
"""

import time
import random
import re
import json
import requests
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

# Import from main module (will be imported at runtime to avoid circular imports)
# Functions will receive these as parameters or import lazily

# Track used video URLs to avoid duplicates
USED_VIDEOS_PATH = Path("storage/used_videos.json")

def load_used_videos() -> set:
    """Load set of video tweet URLs we've already used"""
    try:
        if USED_VIDEOS_PATH.exists():
            data = json.loads(USED_VIDEOS_PATH.read_text())
            # Clean old entries (keep only from today)
            today = datetime.now().strftime("%Y-%m-%d")
            if isinstance(data, dict) and data.get("date") == today:
                return set(data.get("urls", []))
        return set()
    except Exception:
        return set()

def save_used_video(url: str):
    """Mark a video URL as used"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        data = {"date": today, "urls": list(load_used_videos())}
        data["urls"].append(url)
        USED_VIDEOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        USED_VIDEOS_PATH.write_text(json.dumps(data, indent=2))
    except Exception as e:
        # Import log here to avoid circular imports
        from social_agent import log
        log(f"[ERROR] Failed to save used video: {e}")

def findTrendingPoliticalVideos(page, limit: int = 10) -> List[Dict]:
    """
    Find trending political/prediction videos from large, relevant accounts
    Filters for: verified or followers ≥ 50,000, likes ≥ 200 or views ≥ 50,000, last 24 hours
    Returns list of candidate tweet objects with video URLs
    """
    # Import here to avoid circular imports
    from social_agent import SEARCH_URL, stable_goto, human_pause, log, extract_account_stats
    
    candidates = []
    used_urls = load_used_videos()
    
    # Helper to parse number with K/M/B suffix
    def parse_number(val_str):
        if not val_str:
            return 0
        multiplier = 1
        val_upper = str(val_str).upper()
        if 'K' in val_upper:
            multiplier = 1000
            val_str = val_upper.replace('K', '').strip()
        elif 'M' in val_upper:
            multiplier = 1000000
            val_str = val_upper.replace('M', '').strip()
        elif 'B' in val_upper:
            multiplier = 1000000000
            val_str = val_upper.replace('B', '').strip()
        try:
            return int(float(val_str) * multiplier)
        except:
            return 0
    
    # Search terms for trending content
    search_terms = [
        "politics video",
        "election news video",
        "prediction market video",
        "political news",
        "breaking news video",
        "finance news video",
    ]
    
    for term in search_terms[:3]:  # Limit searches to avoid rate limits
        try:
            url = SEARCH_URL.format(q=term.replace(" ", "%20"))
            stable_goto(page, url)
            human_pause(2.0, 4.0)
            
            # Find tweet cards with videos
            cards = page.locator('article[data-testid="tweet"]')
            card_count = min(cards.count(), 20)
            
            for i in range(card_count):
                try:
                    card = cards.nth(i)
                    
                    # Check if tweet has video
                    video_elem = card.locator('video, [data-testid="videoComponent"]').first
                    if video_elem.count() == 0:
                        continue
                    
                    # Extract account stats (followers, verified, engagement)
                    stats = extract_account_stats(card)
                    followers = stats.get("followers", 0)
                    verified = stats.get("verified", False)
                    likes = stats.get("likes", 0)
                    views = stats.get("views", 0)
                    
                    # Filter: Must be verified OR followers ≥ 50,000
                    if not verified and followers < 50000:
                        continue
                    
                    # Filter: Must have likes ≥ 200 OR views ≥ 50,000
                    if likes < 200 and views < 50000:
                        continue
                    
                    # Extract tweet ID and URL
                    tweet_link = card.locator('a[href*="/status/"]').first
                    if tweet_link.count() == 0:
                        continue
                    
                    href = tweet_link.get_attribute("href")
                    if not href:
                        continue
                    
                    # Full URL
                    if href.startswith("/"):
                        tweet_url = f"https://x.com{href}"
                    else:
                        tweet_url = href
                    
                    # Skip if already used
                    if tweet_url in used_urls:
                        continue
                    
                    # Extract tweet ID for timestamp checking (if possible)
                    tweet_id_match = re.search(r"/status/(\d+)", href)
                    tweet_id = tweet_id_match.group(1) if tweet_id_match else None
                    
                    # Note: We can't easily check if tweet is from last 24 hours without API access
                    # We'll rely on the search being sorted by recent and the engagement filters
                    # which naturally favor recent content
                    
                    # Extract tweet text for context
                    try:
                        tweet_text = card.locator('[data-testid="tweetText"]').first.inner_text()
                    except Exception:
                        tweet_text = ""
                    
                    candidates.append({
                        "url": tweet_url,
                        "tweet_id": tweet_id,
                        "text": tweet_text[:200] if tweet_text else "",
                        "followers": followers,
                        "verified": verified,
                        "likes": likes,
                        "views": views,
                        "card": card,  # Keep reference for later use
                    })
                    
                    if len(candidates) >= limit:
                        break
                        
                except Exception as e:
                    log(f"[DEBUG] Error extracting candidate video: {e}")
                    continue
            
            if len(candidates) >= limit:
                break
                
        except Exception as e:
            log(f"[ERROR] Error searching for trending videos: {e}")
            continue
    
    log(f"[INFO] Found {len(candidates)} candidate trending videos (filtered for quality)")
    return candidates

def downloadVideoFromTweet(page, tweet_url: str) -> Dict:
    """
    Download video from a tweet URL using the authenticated browser session
    Returns dict with {success: bool, reason?: str, path?: Path}
    """
    # Import here to avoid circular imports
    from social_agent import stable_goto, human_pause, log, VIDEOS_DIR
    
    try:
        # Navigate to tweet using authenticated session
        stable_goto(page, tweet_url)
        human_pause(2.0, 4.0)
        
        # Find video element
        video_elem = page.locator('video').first
        if video_elem.count() == 0:
            log(f"[WARNING] No video found in tweet: {tweet_url}")
            return {"success": False, "reason": "no_video_found"}
        
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        video_path = VIDEOS_DIR / f"repost_{int(time.time())}_{random.randint(1000, 9999)}.mp4"
        
        try:
            # Method 1: Try to intercept network requests to get video URL
            # This is the most reliable method for X videos which often use authenticated CDN URLs
            video_url = None
            try:
                # Wait for video to start loading
                page.wait_for_selector('video', timeout=5000)
                
                # Try to get video source from network requests
                # Check if video element has a src attribute
                video_src = video_elem.get_attribute("src")
                if video_src and video_src.startswith("http"):
                    video_url = video_src
                    log(f"[DEBUG] Found video src attribute: {video_url[:50]}...")
                
                # If no src, try to extract from video's currentSrc via JavaScript
                if not video_url:
                    video_url = page.evaluate("""
                        () => {
                            const video = document.querySelector('video');
                            if (!video) return null;
                            // Try currentSrc first (actual loaded source)
                            if (video.currentSrc) return video.currentSrc;
                            // Fallback to src
                            return video.src || null;
                        }
                    """)
                    if video_url:
                        log(f"[DEBUG] Extracted video URL via JavaScript: {video_url[:50]}...")
                
            except Exception as e:
                log(f"[DEBUG] Could not extract video URL: {e}")
            
            # If we have a direct HTTP URL, download it using the authenticated session's cookies
            if video_url and video_url.startswith("http"):
                try:
                    # Use requests with cookies from the authenticated Playwright session
                    cookies = page.context.cookies()
                    cookie_dict = {cookie["name"]: cookie["value"] for cookie in cookies}
                    
                    response = requests.get(
                        video_url,
                        stream=True,
                        timeout=30,
                        cookies=cookie_dict,
                        headers={
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Referer": tweet_url,
                        }
                    )
                    
                    if response.status_code == 200:
                        with open(video_path, "wb") as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                        
                        if video_path.exists() and video_path.stat().st_size > 1000:  # At least 1KB
                            log(f"[INFO] Downloaded video to: {video_path.name} ({video_path.stat().st_size} bytes)")
                            return {"success": True, "path": video_path}
                    else:
                        log(f"[DEBUG] Video URL returned status {response.status_code}")
                        
                except Exception as e:
                    log(f"[DEBUG] Direct download failed: {e}")
            
            # Method 2: Try using Playwright's download API (works if video has download attribute)
            # This is less reliable but sometimes works for public videos
            try:
                # Check if video can be right-clicked and downloaded
                # For now, we'll skip this as X videos rarely support this
                pass
            except Exception as e:
                log(f"[DEBUG] Playwright download method failed: {e}")
            
            # If we still don't have the file, return failure
            if not video_path.exists() or video_path.stat().st_size == 0:
                log(f"[WARNING] Could not download video from {tweet_url} - video may be protected or require different auth")
                if video_path.exists():
                    video_path.unlink()
                return {"success": False, "reason": "protected_or_no_access"}
                
        except Exception as e:
            log(f"[WARNING] Error during video download: {e}")
            if video_path.exists():
                video_path.unlink()
            return {"success": False, "reason": "download_error"}
            
        # Should not reach here, but if we do and have a valid file, return success
        if video_path.exists() and video_path.stat().st_size > 0:
            return {"success": True, "path": video_path}
        else:
            return {"success": False, "reason": "unknown"}
            
    except Exception as e:
        log(f"[WARNING] Error accessing tweet {tweet_url}: {e}")
        return {"success": False, "reason": "access_error"}

def createRepostCaption(video_meta: Dict, state: Dict) -> str:
    """
    Create caption for reposted video using Market Nerd voice
    One sentence describing clip, one short line about odds/markets, optional CTA
    Max 200 characters
    """
    # Import here to avoid circular imports
    from social_agent import (
        canUseLinkInPost, sanitize, openai_client, REFERRAL_LINK, log,
        safetyCheckDraft, spiceCheckDraft, fix_banned_opening
    )
    
    system_prompt = """You are "The Market Nerd Analyst" – a data-driven, slightly contrarian observer obsessed with odds and market moves.

You write short, punchy captions for reposted videos:
- One sentence describing the clip
- One short line about odds or markets
- Max 200 characters total
- Avoid generic openings: "Absolutely," "Indeed," "It's fascinating," "I'm curious," "Betting," "The future."
- Data-first: Include specific odds, percentages, or market stats when relevant."""

    # Check if we can include link
    can_include_link = canUseLinkInPost(state)
    
    video_context = video_meta.get("text", "")[:300] if video_meta.get("text") else "Political/prediction market video"
    
    user_prompt = f"""Write a caption for a reposted political/prediction market video.

Video context: {video_context}

Format:
- One sentence describing what the clip shows
- One short line about odds or markets (include specific numbers if relevant)

canUseLinkInPost = {can_include_link}

If canUseLinkInPost is true, append exactly this at the end: "Live odds: {REFERRAL_LINK}"
If canUseLinkInPost is false, do not include any link.

Max 200 characters total.
Use at most 3 relevant hashtags.
Never say you are a bot or automated.

Output only the final caption text, nothing else."""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.85,
            max_tokens=200,
        )
        caption = response.choices[0].message.content.strip()
        # Remove quotes if wrapped
        if caption.startswith('"') and caption.endswith('"'):
            caption = caption[1:-1]
        
        draft_caption = sanitize(caption)
        
        # Ensure link is appended if canUseLinkInPost and not already present
        if can_include_link and REFERRAL_LINK not in draft_caption:
            draft_caption = f"{draft_caption} Live odds: {REFERRAL_LINK}".strip()
        elif not can_include_link:
            # Remove link if present but we can't use it
            draft_caption = draft_caption.replace(REFERRAL_LINK, "").strip()
        
        # Enforce 200 character limit
        if len(draft_caption) > 200:
            # Trim before the link if link is present
            if REFERRAL_LINK in draft_caption:
                link_part = f"Live odds: {REFERRAL_LINK}"
                remaining_chars = 200 - len(link_part) - 1  # -1 for space
                main_text = draft_caption.replace(link_part, "").strip()[:remaining_chars]
                draft_caption = f"{main_text} {link_part}".strip()
            else:
                draft_caption = draft_caption[:197].rstrip() + "..."
        
        # Safety check
        status, safe_caption = safetyCheckDraft(draft_caption, state)
        
        # Spice check to make it sharper (preserve link)
        link_present = REFERRAL_LINK in safe_caption
        link_line = None
        if link_present:
            # Extract link line
            if f"Live odds: {REFERRAL_LINK}" in safe_caption:
                link_line = f"Live odds: {REFERRAL_LINK}"
                safe_caption_minus_link = safe_caption.replace(link_line, "").strip()
            else:
                link_line = REFERRAL_LINK
                safe_caption_minus_link = safe_caption.replace(REFERRAL_LINK, "").strip()
        else:
            safe_caption_minus_link = safe_caption
        
        final_caption = spiceCheckDraft(safe_caption_minus_link, max_chars=200)
        
        # If spice check returns SKIP, use the safe caption (without link)
        if final_caption == "SKIP":
            log("[SPICE] Caption rejected by spice check, using safe version")
            final_caption = safe_caption_minus_link
        
        # Restore link if it was present
        if link_present and link_line and REFERRAL_LINK not in final_caption:
            final_caption = f"{final_caption} {link_line}".strip()
        
        # Check for banned openings after spice check
        final_lower = final_caption.strip().lower()
        banned_openers = ["Absolutely", "Indeed", "Betting", "The", "It's", "I'm"]
        starts_with_banned = any(final_lower.startswith(opener.lower()) for opener in banned_openers)
        
        if starts_with_banned:
            log(f"[BANNED_OPENER] Detected banned opening in caption, fixing...")
            # Preserve link before fixing
            link_preserved = REFERRAL_LINK in final_caption
            link_to_restore = None
            if link_preserved:
                if f"Live odds: {REFERRAL_LINK}" in final_caption:
                    link_to_restore = f"Live odds: {REFERRAL_LINK}"
                    final_caption = final_caption.replace(link_to_restore, "").strip()
                else:
                    link_to_restore = REFERRAL_LINK
                    final_caption = final_caption.replace(REFERRAL_LINK, "").strip()
            
            final_caption = fix_banned_opening(final_caption)
            
            # Restore link
            if link_to_restore:
                final_caption = f"{final_caption} {link_to_restore}".strip()
        
        # Re-apply character limit after all processing
        if len(final_caption) > 200:
            if REFERRAL_LINK in final_caption:
                link_part = f"Live odds: {REFERRAL_LINK}" if f"Live odds: {REFERRAL_LINK}" in final_caption else REFERRAL_LINK
                remaining_chars = 200 - len(link_part) - 1
                main_text = final_caption.replace(link_part, "").strip()[:remaining_chars]
                final_caption = f"{main_text} {link_part}".strip()
            else:
                final_caption = final_caption[:197].rstrip() + "..."
        
        return final_caption
    except Exception as e:
        log(f"[ERROR] Failed to create repost caption: {e}")
        # Fallback caption
        fallback = "Interesting take on the markets. What do you think?"
        if can_include_link:
            fallback = f"{fallback} Live odds: {REFERRAL_LINK}"
        return fallback[:200]  # Enforce limit even on fallback

def selectVideoForRepost(candidates: List[Dict], state: Dict) -> Optional[Dict]:
    """
    Select a video from candidates based on engagement and freshness
    """
    if not candidates:
        return None
    
    # Filter out already used
    used_urls = load_used_videos()
    available = [c for c in candidates if c.get("url") not in used_urls]
    
    if not available:
        return None
    
    # For now, random selection (could be enhanced with engagement metrics)
    return random.choice(available)

def maybePostRepostedVideo(page, state: Dict) -> Optional[Dict]:
    """
    Main orchestrator for reposting trending videos
    Returns dict with post data if ready to post, None/False otherwise
    Falls back to original text post if video download fails
    """
    # Import here to avoid circular imports
    from social_agent import (
        getPostingState, check_can_repost_video, resetDailyCountersIfNewDay,
        REFERRAL_LINK, log, generate_tweet_with_ai
    )
    
    try:
        # Reset daily counters if needed
        resetDailyCountersIfNewDay(state)
        state = getPostingState()
        
        # Limit video reposts to max 3 per day
        max_video_reposts_per_day = 3
        reposted_videos_today = state.get("repostedVideosToday", 0)
        if reposted_videos_today >= max_video_reposts_per_day:
            log(f"[INFO] Daily video repost limit reached ({reposted_videos_today}/{max_video_reposts_per_day})")
            return None
        
        # Check if we can repost video (must be ≤50% of original posts)
        if not check_can_repost_video(state):
            log("[INFO] Repost video limit reached (50% of original posts)")
            return None
        
        # Check if last post was a video (don't post videos back-to-back)
        last_post_type = state.get("lastOriginalPostType")
        if last_post_type == "video":
            log("[INFO] Last post was a video, skipping to avoid back-to-back videos")
            return None
        
        # Find trending videos
        candidates = findTrendingPoliticalVideos(page, limit=5)
        if not candidates:
            log("[INFO] No trending video candidates found")
            return None
        
        # Select video
        selected = selectVideoForRepost(candidates, state)
        if not selected:
            log("[INFO] No suitable video selected for repost")
            return None
        
        tweet_url = selected.get("url")
        log(f"[INFO] Selected video for repost: {tweet_url}")
        
        # Download video (now returns structured result)
        download_result = downloadVideoFromTweet(page, tweet_url)
        
        if not download_result.get("success"):
            reason = download_result.get("reason", "unknown")
            log(f"[WARNING] Skipping video repost – not downloadable / protected (reason: {reason})")
            
            # Fall back to posting an original text tweet about the same topic
            video_text = selected.get("text", "")[:200]
            if video_text:
                log(f"[INFO] Falling back to original text post about: {video_text[:50]}...")
                # The caller will handle generating and posting original content
                # We return None here so the normal posting flow takes over
            return None
        
        video_path = download_result.get("path")
        if not video_path or not video_path.exists():
            log(f"[WARNING] Video path invalid after download")
            return None
        
        # Create caption (already includes safety and spice checks internally)
        caption = createRepostCaption(selected, state)
        
        if not caption or len(caption.strip()) == 0:
            log("[ERROR] Caption generation failed")
            return None
        
        # Mark video as used (before posting to avoid duplicate attempts)
        save_used_video(tweet_url)
        
        log(f"[INFO] Ready to post reposted video with caption: {caption[:60]}...")
        
        # Return dict with post data for caller to use
        return {
            "type": "repost_video",
            "video_path": video_path,
            "caption": caption,
            "has_link": REFERRAL_LINK in caption,
        }
        
    except Exception as e:
        log(f"[ERROR] Error in maybePostRepostedVideo: {e}")
        return None

def postRepostedVideo(page, video_path: Path, caption: str) -> bool:
    """
    Post a reposted video with caption using existing posting infrastructure
    This is called from the main posting flow
    """
    try:
        from social_agent import (
            get_inline_composer, find_file_input, click_post_once,
            human_pause, HOME_URL, stable_goto
        )
        
        # Go to home
        stable_goto(page, HOME_URL)
        human_pause(2.0, 4.0)
        
        # Get composer
        composer = get_inline_composer(page)
        if not composer:
            log("[ERROR] Could not find tweet composer")
            return False
        
        # Click composer
        composer.click(timeout=5000)
        human_pause(0.5, 1.0)
        
        # Type caption
        for ch in caption:
            page.keyboard.type(ch, delay=random.randint(30, 80))
            if random.random() < 0.05:
                human_pause(0.3, 0.8)
        
        human_pause(1.0, 2.0)
        
        # Attach video
        file_input = find_file_input(page)
        if file_input and video_path.exists():
            file_input.set_input_files(str(video_path))
            log(f"📹 Attached reposted video: {video_path.name}")
            human_pause(2.0, 4.0)  # Wait for upload
        else:
            log("[ERROR] Could not attach video")
            return False
        
        # Post
        posted = click_post_once(page)
        if posted:
            human_pause(3.0, 5.0)
            log(f"✅ Reposted video posted successfully!")
            return True
        else:
            log("[ERROR] Failed to post reposted video")
            return False
            
    except Exception as e:
        log(f"[ERROR] Error posting reposted video: {e}")
        return False

