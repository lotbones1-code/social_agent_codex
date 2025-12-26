import random
import time
from datetime import datetime, timedelta

class AccountHelper:
    def __init__(self):
        self.follows_today = 0
        self.follow_limit_per_day = 10
        self.last_follow_date = datetime.now().strftime("%Y-%m-%d")
        self.warning_count = 0
        self.last_warning_reset = datetime.now()
        self.metrics = {
            "posts_today": 0,
            "replies_today": 0,
            "videos_today": 0,
            "links_included": 0,
            "dedupe_skips": 0,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
    
    def should_follow_account(self):
        """Follow 5-10 relevant accounts per day to look human"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.last_follow_date:
            self.follows_today = 0
            self.last_follow_date = today
        
        if self.follows_today < self.follow_limit_per_day:
            self.follows_today += 1
            return True
        return False
    
    def log_warning(self, warning_type):
        """Track if X is flagging us"""
        self.warning_count += 1
        
        if datetime.now() - self.last_warning_reset > timedelta(hours=1):
            self.warning_count = 0
            self.last_warning_reset = datetime.now()
        
        if self.warning_count >= 3:
            print("[EMERGENCY] 3+ warnings in 1 hour. Pausing bot for 24 hours.")
            time.sleep(86400)
            self.warning_count = 0
    
    def log_action(self, action_type):
        """Track daily metrics"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self.metrics["date"]:
            self.print_daily_summary()
            self.metrics = {k: 0 for k in self.metrics if k != "date"}
            self.metrics["date"] = today
        
        if action_type == "post":
            self.metrics["posts_today"] += 1
        elif action_type == "reply":
            self.metrics["replies_today"] += 1
        elif action_type == "video":
            self.metrics["videos_today"] += 1
        elif action_type == "link":
            self.metrics["links_included"] += 1
        elif action_type == "dedupe_skip":
            self.metrics["dedupe_skips"] += 1
    
    def print_daily_summary(self):
        print(f"""
[DAILY SUMMARY]
Posts: {self.metrics['posts_today']}
Replies: {self.metrics['replies_today']}
Videos: {self.metrics['videos_today']}
Links: {self.metrics['links_included']}
Dedupe Skips: {self.metrics['dedupe_skips']}
        """)

ACCOUNT_HELPER = AccountHelper()

