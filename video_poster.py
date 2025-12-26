import json
import os
import time
from datetime import datetime

class VideoScheduler:
    def __init__(self, config_file="video_schedule.json"):
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
            "videos_per_day": 3,
            "videos_posted_today": 0,
            "last_video_date": "",
            "next_video_time": 0
        }
    
    def save_config(self):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"[VIDEO] Error saving config: {e}")
    
    def reset_daily_counter_if_needed(self):
        """Reset counter at midnight"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.config["last_video_date"] != today:
            self.config["videos_posted_today"] = 0
            self.config["last_video_date"] = today
            self.save_config()
    
    def should_post_video_now(self):
        """Check if it's time to post a video"""
        self.reset_daily_counter_if_needed()
        
        # Already hit daily limit?
        if self.config["videos_posted_today"] >= self.config["videos_per_day"]:
            return False
        
        # Time-based: spread 3 videos across 24h = every 8 hours
        current_time = time.time()
        if current_time < self.config["next_video_time"]:
            return False
        
        return True
    
    def mark_video_posted(self):
        """Record that we posted a video"""
        self.config["videos_posted_today"] += 1
        # Schedule next video in 8 hours (24h / 3 videos)
        self.config["next_video_time"] = time.time() + (8 * 3600)
        self.save_config()
        print(f"[VIDEO] Posted {self.config['videos_posted_today']}/3 today")

VIDEO_SCHEDULER = VideoScheduler()


import random

class TrendingVideoFinder:
    def __init__(self, radar_config="radar_config.json"):
        self.radar_config = radar_config
        self.posted_video_ids = self.load_posted_ids()
    
    def load_posted_ids(self):
        """Track which videos we already posted"""
        if os.path.exists("posted_videos.json"):
            try:
                with open("posted_videos.json", 'r') as f:
                    return json.load(f).get("video_ids", [])
            except Exception:
                return []
        return []
    
    def save_posted_id(self, video_id):
        """Mark video as posted"""
        self.posted_video_ids.append(video_id)
        # Keep last 500 only
        self.posted_video_ids = self.posted_video_ids[-500:]
        try:
            with open("posted_videos.json", 'w') as f:
                json.dump({"video_ids": self.posted_video_ids}, f)
        except Exception as e:
            print(f"[VIDEO] Error saving posted IDs: {e}")
    
    def load_radar_targets(self):
        """Load hot topics from Radar config"""
        if os.path.exists(self.radar_config):
            try:
                with open(self.radar_config, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "hot_accounts": ["@Polymarket"],
            "hot_keywords": ["polymarket", "prediction market"]
        }
    
    def find_trending_video_post(self, page):
        """
        Find a high-engagement video post from hot targets
        
        Strategy:
        1. Search for hot keywords OR check hot accounts
        2. Find posts with videos that have 10K+ views
        3. Posted in last 24-48 hours (fresh but proven)
        4. Not already reposted by us
        """
        radar = self.load_radar_targets()
        
        # Strategy: Search hot keywords first
        # Filter out generic/bad keywords that create poor searches
        bad_keywords = ["prediction market", "prediction markets", "betting markets"]
        good_keywords = [kw for kw in radar["hot_keywords"] if kw.lower() not in [b.lower() for b in bad_keywords]]
        
        # Fallback to safe keywords if filtered list is empty
        if not good_keywords:
            good_keywords = ["Polymarket", "election", "2026", "senate odds", "election betting"]
        
        keyword = random.choice(good_keywords)
        print(f"[VIDEO SEARCH] Looking for trending videos about: {keyword}")
        
        # Use your existing search function
        # Search for posts with videos
        # Hardcoded clean search to avoid bad keywords
        search_query = "Polymarket filter:videos min_faves:100"
        
        # Return the search parameters
        return {
            "search_query": search_query,
            "keyword": keyword,
            "target_accounts": radar["hot_accounts"],
            "min_views": 10000,
            "max_age_hours": 48
        }
    
    def is_good_video_candidate(self, post_data):
        """
        Check if video is worth reposting
        
        Criteria:
        - Has actual video (not just image)
        - 10K+ views OR 100+ likes
        - Posted in last 48 hours
        - About relevant topic
        - We haven't posted it before
        """
        video_id = post_data.get("id")
        
        # Already posted?
        if video_id in self.posted_video_ids:
            print(f"[VIDEO SKIP] Already posted {video_id}")
            return False
        
        # Has engagement?
        views = post_data.get("views", 0)
        likes = post_data.get("likes", 0)
        
        if views < 10000 and likes < 100:
            print(f"[VIDEO SKIP] Low engagement (views: {views}, likes: {likes})")
            return False
        
        print(f"[VIDEO ✓] Good candidate: {views} views, {likes} likes")
        return True
    
    def generate_caption_for_video(self, original_post_text, keyword, referral_link):
        """
        Create engaging caption for reposted video
        
        Style:
        - Short and punchy
        - References the market/odds angle
        - Adds your link naturally
        - Trending hashtags
        """
        
        # Caption templates
        templates = [
            "This is wild. {insight}\n\nTrack the odds: {link}",
            "{hook} 📈\n\nLive market data: {link}",
            "The market's reacting to this.\n\n{insight}\n\n{link}",
            "Watch how fast this moved the odds.\n\n{link}",
            "{hook}\n\nReal-time betting: {link}"
        ]
        
        # Insights based on keyword
        insights = {
            "polymarket": "Polymarket traders moving fast on this",
            "prediction market": "Prediction markets are pricing this in",
            "betting odds": "Odds just shifted hard",
            "2026 midterm": "2026 market is heating up",
            "senate odds": "Senate control odds changing",
            "election betting": "Bettors are all over this"
        }
        
        # Hooks
        hooks = [
            "This just happened 👀",
            "Market is going crazy on this",
            "Everyone's betting on this now",
            "This moved the market",
            "Odds are wild right now"
        ]
        
        caption_template = random.choice(templates)
        insight = insights.get(keyword, "Markets are reacting to this")
        hook = random.choice(hooks)
        
        caption = caption_template.format(
            insight=insight,
            hook=hook,
            link=referral_link
        )
        
        # Add trending hashtags (2 max)
        hashtags = self.get_trending_hashtags(keyword)
        if hashtags:
            caption += f"\n\n{hashtags}"
        
        return caption
    
    def get_trending_hashtags(self, keyword):
        """Pick 1-2 relevant trending hashtags"""
        hashtag_map = {
            "polymarket": "#Polymarket #PredictionMarkets",
            "prediction market": "#PredictionMarkets #Crypto",
            "betting odds": "#BettingMarkets #Politics",
            "2026 midterm": "#Midterms2026 #Politics",
            "senate odds": "#Senate #Politics",
            "election betting": "#ElectionBetting #Politics"
        }
        return hashtag_map.get(keyword, "#Polymarket")

VIDEO_FINDER = TrendingVideoFinder()
