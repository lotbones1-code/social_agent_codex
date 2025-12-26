import json
import os
import random
from datetime import datetime

class RadarTargeting:
    """
    Uses your Radar-identified hot topics and accounts
    to prioritize which threads to reply in
    
    Strategy:
    - Load radar_config.json (you update manually 2-3x/day)
    - Prioritize replies/likes/retweets on those topics
    - For video reposting, prioritize videos from those accounts
    """
    
    def __init__(self, config_file="radar_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.last_config_update = None
    
    def load_config(self):
        """Load Radar hot topics from config"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return self.default_config()
        return self.default_config()
    
    def default_config(self):
        """Fallback if no Radar config exists"""
        return {
            "hot_accounts": [
                "@Polymarket",
                "@PredictIt",
                "@NateSilver538"
            ],
            "hot_keywords": [
                "Polymarket"
            ],
            "hot_topics": [
                "2026 midterms",
                "senate control",
                "election betting"
            ],
            "last_updated": datetime.now().isoformat()
        }
    
    def refresh_config(self):
        """Reload config if file was updated"""
        if os.path.exists(self.config_file):
            self.config = self.load_config()
            self.last_config_update = datetime.now().isoformat()
            print(f"[RADAR] Updated targeting config from Radar")
    
    def is_radar_target(self, post_text, post_author=None):
        """
        Check if a post matches our Radar hot topics
        
        Return priority score:
        - 1.0 = exact match with hot keyword
        - 0.7 = topic match
        - 0.0 = not relevant
        """
        text_lower = post_text.lower()
        
        # Check for hot keywords (highest priority)
        for keyword in self.config.get("hot_keywords", []):
            if keyword.lower() in text_lower:
                print(f"[RADAR] ✓ Matched hot keyword: {keyword}")
                return 1.0
        
        # Check for hot topics
        for topic in self.config.get("hot_topics", []):
            if topic.lower() in text_lower:
                print(f"[RADAR] ✓ Matched hot topic: {topic}")
                return 0.7
        
        # Check if from hot account
        if post_author:
            for account in self.config.get("hot_accounts", []):
                if account.lower() in post_author.lower():
                    print(f"[RADAR] ✓ Post from hot account: {account}")
                    return 0.8
        
        return 0.0
    
    def get_search_priority(self):
        """
        Get the highest-priority Radar keyword to search right now
        
        Strategy: rotate through hot keywords, prioritizing current ones
        """
        keywords = self.config.get("hot_keywords", [])
        if keywords:
            keyword = random.choice(keywords)  # Pick random from hot keywords
            print(f"[RADAR] Prioritizing search: {keyword}")
            return keyword
        return "polymarket"
    
    def get_video_priority_accounts(self):
        """
        For video reposting, prioritize these accounts
        Their content is more likely to trend
        """
        return self.config.get("hot_accounts", [])

RADAR_TARGETING = RadarTargeting()

