"""
Stage 11C: Engagement Amplifier

Automatically likes and retweets own posts to trigger X's algorithmic amplification.
Early engagement signals importance to X's algorithm.
"""

import json
import os
import random
from datetime import datetime

class EngagementAmplifier:
    """
    Amplifies own posts by liking and retweeting them within 30 minutes of posting.
    Triggers X's algorithmic amplification for 3-5x more impressions.
    """
    
    def __init__(self, analytics_log="performance_log.json"):
        self.analytics_log = analytics_log
        self.max_amplifications_per_day = 1
    
    def should_amplify(self):
        """
        Check if we've hit daily rate limit.
        Returns True if we can amplify (haven't hit limit), False otherwise.
        """
        if not os.path.exists(self.analytics_log):
            return True  # No log file, assume we can amplify
        
        try:
            with open(self.analytics_log, 'r') as f:
                data = json.load(f)
        except Exception:
            return True  # Error reading, allow amplification
        
        # Get all stage11c entries from today
        posts = data.get("posts", [])
        today = datetime.now().strftime("%Y-%m-%d")
        
        amplifications_today = 0
        for post in posts:
            if post.get("type") == "stage11c_amplification":
                post_timestamp = post.get("timestamp", "")
                if post_timestamp:
                    try:
                        post_date = datetime.fromisoformat(post_timestamp).strftime("%Y-%m-%d")
                        if post_date == today:
                            amplifications_today += 1
                    except Exception:
                        continue
        
        can_amplify = amplifications_today < self.max_amplifications_per_day
        print(f"[STAGE 11C] Rate limit check: {amplifications_today}/{self.max_amplifications_per_day} amplifications used today")
        
        return can_amplify
    
    def get_amplification_delay(self):
        """
        Return random delay between 3-8 seconds.
        Simulates human pause between liking and retweeting.
        """
        return random.uniform(3.0, 8.0)
    
    def log_amplification(self, tweet_url, post_type="own_post"):
        """
        Write amplification event to performance_log.json.
        
        Args:
            tweet_url: URL of the amplified tweet
            post_type: Type of post (default: "own_post")
        """
        try:
            if os.path.exists(self.analytics_log):
                with open(self.analytics_log, 'r') as f:
                    data = json.load(f)
            else:
                data = {"posts": []}
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "stage11c_amplification",
                "tweet_url": tweet_url,
                "post_type": post_type
            }
            
            if "posts" not in data:
                data["posts"] = []
            data["posts"].append(entry)
            
            with open(self.analytics_log, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[STAGE 11C] ✓ Logged amplification: {tweet_url}")
        except Exception as e:
            print(f"[STAGE 11C] Log error: {str(e)[:80]}")

# Global instance
amplifier = EngagementAmplifier()

