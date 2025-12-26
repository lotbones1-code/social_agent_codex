"""
Stage 11F: Competitor Tracker

Monitors what other Polymarket traders post and generates better counter-takes
to dominate conversations. When competitors' posts get 100+ engagement,
reply with a sharper edge and steal their audience.
"""

import json
import os
import re
from datetime import datetime, timedelta
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

class CompetitorTracker:
    """
    Tracks competitor posts and generates counter-takes to steal engagement.
    """
    
    def __init__(self, analytics_log="performance_log.json", min_engagement_threshold=100, max_replies_per_hour=2):
        self.analytics_log = analytics_log
        self.competitor_handles = []  # List of competitor handles to monitor
        self.min_engagement_threshold = min_engagement_threshold
        self.max_replies_per_hour = max_replies_per_hour
    
    def add_competitor(self, handle):
        """Add a competitor handle to the monitoring list."""
        if handle and handle not in self.competitor_handles:
            self.competitor_handles.append(handle)
            print(f"[STAGE 11F] Added competitor: {handle}")
    
    def should_reply_to_competitor(self):
        """
        Check rate limit (max 2 replies per hour).
        Returns True if we can reply, False if rate limit hit.
        """
        if not os.path.exists(self.analytics_log):
            return True  # No log, assume we can reply
        
        try:
            with open(self.analytics_log, 'r') as f:
                data = json.load(f)
        except Exception:
            return True  # Error reading, allow reply
        
        # Get all stage11f entries from last hour
        posts = data.get("posts", [])
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        replies_last_hour = 0
        for post in posts:
            if post.get("type") == "stage11f_competitor_reply":
                post_timestamp = post.get("timestamp", "")
                if post_timestamp:
                    try:
                        post_time = datetime.fromisoformat(post_timestamp)
                        if post_time >= one_hour_ago:
                            replies_last_hour += 1
                    except Exception:
                        continue
        
        can_reply = replies_last_hour < self.max_replies_per_hour
        print(f"[STAGE 11F] Rate limit check: {replies_last_hour}/{self.max_replies_per_hour} replies used this hour")
        
        return can_reply
    
    def is_high_engagement(self, engagement_count):
        """
        Return True if engagement meets threshold.
        """
        return engagement_count >= self.min_engagement_threshold
    
    def generate_counter_take(self, competitor_thesis):
        """
        Generate a counter-take using GPT-4.
        Finds what competitor is MISSING (not wrong), offers better edge.
        Returns dict with: counter_take, angle, conviction
        """
        if not client:
            print("[STAGE 11F] OpenAI client not available")
            return None
        
        prompt = f"""You are a Polymarket trader analyzing a competitor's take.

COMPETITOR'S THESIS:
{competitor_thesis[:400]}

Your task:
1. Find what the competitor is MISSING (not wrong, just incomplete)
2. Offer a better edge with specific data/insight
3. Keep it collaborative, not confrontational
4. 150-200 characters

Angles to consider:
- missing_data: They're missing key data point
- wrong_probability: Their probability estimate is off
- ignoring_catalyst: They're not accounting for upcoming catalyst
- better_edge: You have a better angle entirely

Output ONLY this JSON (no markdown):
{{"counter_take": "YOUR REPLY", "angle": "missing_data|wrong_probability|ignoring_catalyst|better_edge", "conviction": 85}}"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Output ONLY valid JSON. No markdown. No explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=250
            )
            
            response_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            data = json.loads(response_text)
            
            # Validate required fields
            if "counter_take" not in data or "angle" not in data:
                return None
            
            # Ensure conviction is int (0-100)
            if "conviction" not in data:
                data["conviction"] = 75
            else:
                data["conviction"] = int(data["conviction"])
            
            return data
        
        except Exception as e:
            print(f"[STAGE 11F] Error generating counter-take: {str(e)[:100]}")
            return None
    
    def log_counter_reply(self, competitor_handle, counter_take, angle, conviction):
        """
        Write counter-reply event to performance_log.json.
        
        Args:
            competitor_handle: Handle of the competitor
            counter_take: The generated counter-take text
            angle: The angle used (missing_data, wrong_probability, etc.)
            conviction: Conviction level (0-100)
        """
        try:
            if os.path.exists(self.analytics_log):
                with open(self.analytics_log, 'r') as f:
                    data = json.load(f)
            else:
                data = {"posts": []}
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "stage11f_competitor_reply",
                "competitor_handle": competitor_handle,
                "counter_take": counter_take,
                "angle": angle,
                "conviction": conviction
            }
            
            if "posts" not in data:
                data["posts"] = []
            data["posts"].append(entry)
            
            with open(self.analytics_log, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[STAGE 11F] ✓ Logged counter-reply to @{competitor_handle}")
        except Exception as e:
            print(f"[STAGE 11F] Log error: {str(e)[:80]}")

# Global instance
tracker = CompetitorTracker()

