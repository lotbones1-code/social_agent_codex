"""
Bot Hardening Module - Anti-detection and human-like behavior

This module adds layers of randomization, rate limiting, and human-like patterns
to prevent bot detection while maximizing engagement safely.
"""

import json
import os
import time
import random
from datetime import datetime, timedelta
from collections import deque

class BotHardening:
    """
    Manages anti-detection features:
    - Rate limiting (replies/hour, posts/day)
    - Human-like engagement (likes/retweets)
    - Link safety (duplicate checks, variants)
    - Error recovery (failure tracking, pauses)
    - Heartbeat logging
    """
    
    def __init__(self, metrics_file="hardening_metrics.json"):
        self.metrics_file = metrics_file
        self.metrics = self.load_metrics()
        
        # Rate limiting tracking
        self.replies_this_hour = deque(maxlen=100)
        self.posts_today = deque(maxlen=50)
        self.last_hour_reset = time.time()
        self.actions_this_hour = deque(maxlen=100)  # Global action tracking
        
        # Error recovery
        self.consecutive_failures = 0
        self.last_failure_time = None
        self.pause_until = None
        
        # Link safety
        self.link_history = deque(maxlen=100)  # Track links posted in last 30 minutes
        self.link_variants = []  # Can be populated with alternate link variants
        self.thread_credibility = {}  # Track credibility building in threads
        
        # Engagement mix tracking
        self.actions_since_engagement = 0
        self.last_engagement_time = None
        
        # Heartbeat
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 300  # 5 minutes
    
    def load_metrics(self):
        """Load metrics from file"""
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    # Reset daily counters if new day
                    if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
                        data["posts_today"] = 0
                        data["date"] = datetime.now().strftime("%Y-%m-%d")
                    return data
            except Exception:
                pass
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "posts_today": 0,
            "replies_today": 0,
            "failures_today": 0,
            "links_posted": []
        }
    
    def save_metrics(self):
        """Save metrics to file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(self.metrics, f, indent=2)
        except Exception:
            pass
    
    # ==================== RATE LIMITING ====================
    
    # Global hourly action cap (prevents accidental spam spirals)
    MAX_ACTIONS_PER_HOUR = 30  # Total actions (replies + posts + threads + quote-tweets)
    
    def reset_hourly_counters(self):
        """Reset hourly counters if new hour"""
        current_time = time.time()
        if current_time - self.last_hour_reset > 3600:
            self.replies_this_hour.clear()
            self.actions_this_hour.clear()
            self.last_hour_reset = current_time
    
    def can_perform_action(self):
        """Check if we can perform any action (global hourly cap: 30/hour)"""
        self.reset_hourly_counters()
        
        if len(self.actions_this_hour) >= self.MAX_ACTIONS_PER_HOUR:
            wait_time = 3600 - (time.time() - self.last_hour_reset)
            print(f"[RATE_LIMIT] Max actions/hour ({self.MAX_ACTIONS_PER_HOUR}) reached. Wait {int(wait_time/60)} min")
            return False
        
        return True
    
    def record_action_generic(self):
        """Record any action (post, reply, thread, quote-tweet) for hourly cap tracking"""
        self.reset_hourly_counters()
        self.actions_this_hour.append(time.time())
    
    def can_post_reply(self, max_replies_per_hour=15):  # [PROBLEM #4 FIX] Increased from 8 to 15/hour (3x more aggressive)
        """Check if we can post a reply (rate limit: 15/hour)"""
        self.reset_hourly_counters()
        
        # Check global action cap first
        if not self.can_perform_action():
            return False
        
        if len(self.replies_this_hour) >= max_replies_per_hour:
            wait_time = 3600 - (time.time() - self.last_hour_reset)
            print(f"[RATE_LIMIT] Max replies/hour ({max_replies_per_hour}) reached. Wait {int(wait_time/60)} min")
            return False
        
        return True
    
    def record_reply(self):
        """Record that we posted a reply"""
        self.reset_hourly_counters()
        self.replies_this_hour.append(time.time())
        self.record_action_generic()  # Track for global hourly cap
        self.metrics["replies_today"] = self.metrics.get("replies_today", 0) + 1
        self.save_metrics()
    
    def can_post_original(self, max_posts_per_day=12):
        """Check if we can post an original post (rate limit: 12/day)"""
        # Check global action cap first
        if not self.can_perform_action():
            return False
        
        today = datetime.now().strftime("%Y-%m-%d")
        if self.metrics.get("date") != today:
            self.metrics["posts_today"] = 0
            self.metrics["date"] = today
        
        if self.metrics.get("posts_today", 0) >= max_posts_per_day:
            print(f"[RATE_LIMIT] Max posts/day ({max_posts_per_day}) reached")
            return False
        
        return True
    
    def record_post(self):
        """Record that we posted an original"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.metrics.get("date") != today:
            self.metrics["posts_today"] = 0
            self.metrics["date"] = today
        
        self.record_action_generic()  # Track for global hourly cap
        self.metrics["posts_today"] = self.metrics.get("posts_today", 0) + 1
        self.save_metrics()
    
    def should_take_break(self, actions_since_break=5, break_minutes_min=30, break_minutes_max=60):
        """Check if we should take a break after N consecutive actions"""
        if self.actions_since_engagement >= actions_since_break:
            break_duration = random.randint(break_minutes_min * 60, break_minutes_max * 60)
            print(f"[BREAK] Taking {break_duration//60} min break after {actions_since_break} actions")
            self.actions_since_engagement = 0
            return True, break_duration
        return False, 0
    
    def record_action(self):
        """Record that we performed an action (for break tracking)"""
        self.actions_since_engagement += 1
    
    # ==================== LINK SAFETY ====================
    
    def can_post_link(self, link, min_minutes_between=30):
        """Check if we can post this link (avoid duplicate links within 30 min)"""
        current_time = time.time()
        
        # Clean old entries (older than min_minutes_between)
        cutoff_time = current_time - (min_minutes_between * 60)
        while self.link_history and self.link_history[0][1] < cutoff_time:
            self.link_history.popleft()
        
        # Check if link was posted recently
        for prev_link, prev_time in self.link_history:
            if prev_link == link:
                wait_time = (prev_time + (min_minutes_between * 60)) - current_time
                print(f"[LINK_SAFETY] Link posted {int((current_time - prev_time)/60)} min ago. Wait {int(wait_time/60)} more min")
                return False
        
        return True
    
    def record_link(self, link):
        """Record that we posted a link"""
        self.link_history.append((link, time.time()))
        self.metrics.setdefault("links_posted", []).append({
            "link": link,
            "time": datetime.now().isoformat()
        })
        # Keep last 100 entries
        self.metrics["links_posted"] = self.metrics["links_posted"][-100:]
        self.save_metrics()
    
    def get_link_variant(self, base_link):
        """Get a link variant (if available) or return base link"""
        if self.link_variants and random.random() < 0.3:  # 30% chance to use variant
            return random.choice(self.link_variants)
        return base_link
    
    def should_build_credibility_first(self, thread_id, min_replies_before_link=2):
        """Check if we should build credibility in thread before posting link"""
        credibility = self.thread_credibility.get(thread_id, 0)
        
        if credibility < min_replies_before_link:
            self.thread_credibility[thread_id] = credibility + 1
            print(f"[CREDIBILITY] Building credibility in thread (reply {credibility + 1}/{min_replies_before_link})")
            return True  # Should build credibility first (don't post link yet)
        
        return False  # Can post link now
    
    # ==================== HUMAN-LIKE ENGAGEMENT ====================
    
    def should_do_engagement_action(self, actions_between_engagement=10):
        """Check if we should do a like/retweet instead of reply (every N actions)"""
        if self.actions_since_engagement >= actions_between_engagement:
            self.actions_since_engagement = 0
            self.last_engagement_time = time.time()
            return True
        return False
    
    # ==================== ERROR RECOVERY ====================
    
    def record_failure(self):
        """Record a failure and check if we should pause"""
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        self.metrics["failures_today"] = self.metrics.get("failures_today", 0) + 1
        self.save_metrics()
        
        if self.consecutive_failures >= 3:
            pause_duration = 3600  # 1 hour
            self.pause_until = time.time() + pause_duration
            print(f"[ERROR_RECOVERY] 3 consecutive failures. Pausing for {pause_duration//60} minutes")
            return True, pause_duration
        
        return False, 0
    
    def record_success(self):
        """Record a success (reset failure counter)"""
        self.consecutive_failures = 0
        self.pause_until = None
    
    def is_paused(self):
        """Check if we're currently paused due to errors"""
        if self.pause_until and time.time() < self.pause_until:
            remaining = int((self.pause_until - time.time()) / 60)
            print(f"[PAUSED] Error recovery pause active. {remaining} minutes remaining")
            return True
        elif self.pause_until:
            # Pause expired
            self.pause_until = None
        return False
    
    def should_wait_before_retry(self, min_wait_minutes=5, max_wait_minutes=10):
        """Check if we should wait before retrying after a failure"""
        if self.last_failure_time:
            wait_time = random.randint(min_wait_minutes * 60, max_wait_minutes * 60)
            elapsed = time.time() - self.last_failure_time
            if elapsed < wait_time:
                remaining = int((wait_time - elapsed) / 60)
                return True, remaining
        return False, 0
    
    # ==================== HEARTBEAT ====================
    
    def heartbeat(self):
        """Log heartbeat if enough time has passed"""
        current_time = time.time()
        if current_time - self.last_heartbeat >= self.heartbeat_interval:
            self.last_heartbeat = current_time
            replies_hour = len(self.replies_this_hour)
            posts_today = self.metrics.get("posts_today", 0)
            failures_today = self.metrics.get("failures_today", 0)
            print(f"[HEARTBEAT] Bot active. Replies this hour: {replies_hour}/8, Posts today: {posts_today}/12, Failures: {failures_today}")
            return True
        return False

# Global instance
HARDENING = BotHardening()

