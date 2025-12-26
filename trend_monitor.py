"""
Stage 11E: Trend Monitor

Detects trending political topics on X and instantly posts contrarian Polymarket takes
while the trend is hot. Trending topics = massive audience = capture all that traffic.
"""

import json
import os
from datetime import datetime, timedelta

class TrendMonitor:
    """
    Monitors trending topics and generates Polymarket takes for hot political trends.
    """
    
    def __init__(self, analytics_log="performance_log.json", min_minutes_between_trend_posts=120):
        self.analytics_log = analytics_log
        self.min_minutes_between_trend_posts = min_minutes_between_trend_posts
        
        # Trend keywords to monitor (politics/Polymarket-relevant)
        self.trend_keywords = [
            "election", "trump", "senate", "fed", "conviction",
            "trial", "indictment", "policy", "congress", "president",
            "midterm", "poll", "odds", "betting", "market"
        ]
        
        # Mapping: trend keyword → Polymarket name
        self.trend_to_market_map = {
            "election": "2026 US Election",
            "trump": "Trump conviction odds",
            "senate": "Senate control 2026",
            "fed": "Fed rate cuts 2026",
            "conviction": "Trump conviction odds",
            "trial": "Trump trial outcome",
            "indictment": "Trump criminal charges",
            "policy": "Federal policy changes",
            "congress": "Congress control 2026",
            "president": "2028 Presidential Election",
            "midterm": "2026 Midterm Elections",
            "poll": "Election polling markets",
            "odds": "Political odds markets",
            "betting": "Political betting markets",
            "market": "Polymarket markets"
        }
    
    def can_post_trend_take(self):
        """
        Check rate limit (max 1 trend post per 2 hours).
        Returns True if we can post, False if rate limit hit.
        """
        if not os.path.exists(self.analytics_log):
            return True  # No log, assume we can post
        
        try:
            with open(self.analytics_log, 'r') as f:
                data = json.load(f)
        except Exception:
            return True  # Error reading, allow post
        
        # Get most recent stage11e entry
        posts = data.get("posts", [])
        stage11e_posts = [p for p in posts if p.get("type") == "stage11e_trend_post"]
        
        if not stage11e_posts:
            return True  # No previous posts, we can post
        
        # Get most recent post timestamp
        most_recent = max(stage11e_posts, key=lambda x: x.get("timestamp", ""))
        most_recent_time_str = most_recent.get("timestamp")
        
        if not most_recent_time_str:
            return True  # No timestamp, allow post
        
        try:
            most_recent_time = datetime.fromisoformat(most_recent_time_str)
            time_since_last = datetime.now() - most_recent_time
            minutes_since = time_since_last.total_seconds() / 60
            
            can_post = minutes_since >= self.min_minutes_between_trend_posts
            print(f"[STAGE 11E] Rate limit check: {minutes_since:.1f}/{self.min_minutes_between_trend_posts} minutes since last trend post")
            
            return can_post
        except Exception:
            return True  # Error parsing, allow post
    
    def detect_trending_polymarket_keyword(self, trending_topics_list):
        """
        Check if any trending topics contain Polymarket-relevant keywords.
        Returns the matching topic or None.
        """
        if not trending_topics_list:
            return None
        
        for topic in trending_topics_list:
            topic_lower = topic.lower()
            for keyword in self.trend_keywords:
                if keyword in topic_lower:
                    print(f"[STAGE 11E] ✓ Detected trending keyword: {keyword} (from topic: {topic})")
                    return topic
        
        return None
    
    def map_trend_to_market(self, trend_keyword):
        """
        Map trend keyword to Polymarket name.
        Returns market name string.
        """
        trend_lower = trend_keyword.lower()
        
        # Check direct mapping
        for keyword, market in self.trend_to_market_map.items():
            if keyword in trend_lower:
                print(f"[STAGE 11E] Mapped to market: {market}")
                return market
        
        # Fallback: try to extract key term
        if "trump" in trend_lower:
            return "Trump conviction odds"
        elif "election" in trend_lower:
            return "2026 US Election"
        elif "senate" in trend_lower:
            return "Senate control 2026"
        elif "fed" in trend_lower or "rate" in trend_lower:
            return "Fed rate cuts 2026"
        else:
            return "Political markets"
    
    def log_trend_post(self, trend_keyword, market, thesis):
        """
        Write trend post event to performance_log.json.
        
        Args:
            trend_keyword: The trending keyword detected
            market: Polymarket name
            thesis: Thesis text that was posted
        """
        try:
            if os.path.exists(self.analytics_log):
                with open(self.analytics_log, 'r') as f:
                    data = json.load(f)
            else:
                data = {"posts": []}
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "stage11e_trend_post",
                "trend_keyword": trend_keyword,
                "market": market,
                "thesis": thesis
            }
            
            if "posts" not in data:
                data["posts"] = []
            data["posts"].append(entry)
            
            with open(self.analytics_log, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[STAGE 11E] ✓ Logged trend post: {trend_keyword} → {market}")
        except Exception as e:
            print(f"[STAGE 11E] Log error: {str(e)[:80]}")

# Global instance
monitor = TrendMonitor()

