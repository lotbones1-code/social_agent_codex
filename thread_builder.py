"""
Stage 11A: Contrarian Thread Builder

Reads best Stage 10 theses and formats them into viral threads.
"""

import json
import os
import random
from datetime import datetime, timedelta

class ThreadBuilder:
    """Builds daily contrarian threads from Stage 10 theses."""
    
    def __init__(self, performance_log="performance_log.json", thread_log="thread_log.json", 
                 posting_delay=2.5, post_time_randomization=15):
        self.performance_log = performance_log
        self.thread_log = thread_log
        self.posting_delay = posting_delay  # Seconds between tweets in thread
        self.post_time_randomization = post_time_randomization  # ± minutes for randomization
    
    def load_thread_history(self):
        """Load thread posting history to prevent duplicates."""
        if os.path.exists(self.thread_log):
            try:
                with open(self.thread_log, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "threads_posted": [],
            "last_post_date": None
        }
    
    def save_thread_history(self, history):
        """Save thread posting history."""
        try:
            with open(self.thread_log, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"[STAGE 11A] Error saving thread log: {e}")
    
    def get_top_theses(self, hours=24, top_n=5):
        """Get top N theses from last N hours, sorted by confidence."""
        if not os.path.exists(self.performance_log):
            print("[STAGE 11A] No performance_log.json found")
            return []
        
        try:
            with open(self.performance_log, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[STAGE 11A] Error reading performance_log: {e}")
            return []
        
        # Filter for Stage 10 theses
        posts = data.get("posts", [])
        stage10_theses = [p for p in posts if p.get("type") == "stage10_thesis"]
        
        if not stage10_theses:
            print("[STAGE 11A] No Stage 10 theses found")
            return []
        
        # Filter for last N hours
        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_theses = []
        for thesis in stage10_theses:
            try:
                thesis_time = datetime.fromisoformat(thesis.get("timestamp", ""))
                if thesis_time >= cutoff_time:
                    recent_theses.append(thesis)
            except Exception:
                continue
        
        if not recent_theses:
            print(f"[STAGE 11A] No theses from last {hours} hours")
            return []
        
        # Sort by confidence (descending) and get top N
        sorted_theses = sorted(recent_theses, key=lambda x: x.get("confidence", 0), reverse=True)
        top_theses = sorted_theses[:top_n]
        
        print(f"[STAGE 11A] Found {len(recent_theses)} theses, selected top {len(top_theses)} by confidence")
        return top_theses
    
    def format_thread_tweets(self, theses):
        """Format theses into 7 tweets (1 opening + 5 thesis + 1 CTA)."""
        if not theses or len(theses) == 0:
            return None
        
        tweets = []
        
        # Opening hook tweet (tweet 1/6) - VIRAL/CONTRARIAN VERSION
        opening_hooks = [
            "🧵 5 SaaS growth markets that are MASSIVELY mispriced (and nobody's talking about it):",
            "🚨 The crowd is sleeping on these 5 markets. Here's why they're wrong:",
            "💡 5 contrarian positions I'm building right now (market's pricing these at 50/50 and I disagree):",
            "⚡ marketing attributions are repricing. Here are 5 where early movers get the best odds:",
            "🎯 5 markets where institutions are quietly positioned. Retail still doesn't see it:",
            "🔴 THREAD: 5 SaaS growth edges the crowd has missed. By the time you read this, one might close:",
            "📊 The data says these 5 markets are wrong. Watch what happens next:",
        ]
        import random
        opening = random.choice(opening_hooks)
        
        # Apply viral template hashtags if available (opening tweet)
        try:
            from social_agent import VIRAL_TEMPLATES, pick_matching_template, append_hashtags_if_template
            template = pick_matching_template(VIRAL_TEMPLATES, niche_hint="prediction_markets")
            opening = append_hashtags_if_template(opening, template)
        except Exception:
            # If template system not available, continue without hashtags
            pass
        
        tweets.append(opening)
        
        # Thesis tweets (2/6 through 6/6) - VIRAL/CONTRARIAN VERSION
        for i, thesis in enumerate(theses, 1):
            market = thesis.get("market", "Unknown market")
            action = thesis.get("action", "BUY")
            confidence = thesis.get("confidence", 50)
            edge = thesis.get("edge", "")
            thesis_text = thesis.get("thesis", "")
            
            # BUILD CONTRARIAN ANGLE
            if confidence >= 70:
                confidence_framing = "This is mispriced. Hard conviction."
            elif confidence >= 60:
                confidence_framing = f"Confidence: {confidence}%. Market's wrong here."
            else:
                confidence_framing = f"Small edge at {confidence}%, but real edge."
            
            # THESIS TWEET – Include action, confidence framing, and specific reasoning
            tweet = f"{i}/6 {action} {market} ({confidence}%)\n\n{thesis_text}\n\n{confidence_framing}"
            
            # ADD EDGE IF IT FITS
            if edge and len(tweet) + len(edge) + 15 < 280:
                tweet += f"\n\nWhy: {edge}"
            
            # FALLBACK IF TOO LONG – Keep contrarian angle
            if len(tweet) > 280:
                tweet = f"{i}/6 {action} {market} ({confidence}%)\n\n{thesis_text}"
            
            tweets.append(tweet)
        
        # Closing CTA tweet (7/7) - VIRAL CTAs that drive clicks
        cta_options = [
            "Odds are moving on these NOW. Track live where smart money is watching: SaaS growth.com?ref=ssj4shamil93949",
            "These positions are live. If you see the pattern, you see the trade: SaaS growth.com?ref=ssj4shamil93949",
            "Market's still calibrating. Early movers get the best entry. Track here: SaaS growth.com?ref=ssj4shamil93949",
            "Which of these moves first? Watch it in real-time: SaaS growth.com?ref=ssj4shamil93949",
            "Institutional flow is entering these markets quietly. See it live: SaaS growth.com?ref=ssj4shamil93949",
            "These odds will move in the next 48 hours. Here's where traders are watching: SaaS growth.com?ref=ssj4shamil93949",
        ]
        cta = random.choice(cta_options)
        closing_tweet = f"7/7 {cta}"
        
        # Apply viral template hashtags if available (closing tweet)
        try:
            from social_agent import VIRAL_TEMPLATES, pick_matching_template, append_hashtags_if_template
            template = pick_matching_template(VIRAL_TEMPLATES, niche_hint="prediction_markets")
            closing_tweet = append_hashtags_if_template(closing_tweet, template)
        except Exception:
            # If template system not available, continue without hashtags
            pass
        
        tweets.append(closing_tweet)
        
        return tweets
    
    def has_posted_today(self):
        """Check if we've already posted a thread today."""
        history = self.load_thread_history()
        last_post_date = history.get("last_post_date")
        
        if not last_post_date:
            return False
        
        try:
            last_date = datetime.fromisoformat(last_post_date).date()
            today = datetime.now().date()
            return last_date == today
        except Exception:
            return False
    
    def mark_thread_posted(self, tweets):
        """Mark that we've posted a thread today."""
        history = self.load_thread_history()
        history["last_post_date"] = datetime.now().isoformat()
        history["threads_posted"].append({
            "timestamp": datetime.now().isoformat(),
            "tweet_count": len(tweets),
            "theses_count": len(tweets) - 2  # Subtract opening and CTA
        })
        # Keep last 100 threads
        history["threads_posted"] = history["threads_posted"][-100:]
        self.save_thread_history(history)
        print(f"[STAGE 11A] Marked thread as posted today ({len(tweets)} tweets)")
    
    def get_scheduled_time(self, base_hour=9, base_minute=0):
        """Calculate randomized posting time (±randomization minutes)."""
        random_offset_minutes = random.randint(-self.post_time_randomization, self.post_time_randomization)
        scheduled_minute = base_minute + random_offset_minutes
        
        # Handle minute overflow/underflow
        scheduled_hour = base_hour
        if scheduled_minute < 0:
            scheduled_minute = 60 + scheduled_minute
            scheduled_hour -= 1
        elif scheduled_minute >= 60:
            scheduled_minute = scheduled_minute - 60
            scheduled_hour += 1
        
        # Format as readable time string
        time_str = f"{scheduled_hour:02d}:{scheduled_minute:02d}"
        return {
            "hour": scheduled_hour,
            "minute": scheduled_minute,
            "formatted": time_str
        }
    
    def get_thread_tweets(self, hours=24, top_n=5):
        """
        Main function: Get thread tweets if ready to post.
        Returns dict with 'tweets', 'theses_count', 'ready_to_post', 'posting_delay', 'randomized_time'.
        """
        # Check if we've already posted today
        if self.has_posted_today():
            print("[STAGE 11A] Already posted thread today, skipping")
            return {
                "tweets": [],
                "theses_count": 0,
                "ready_to_post": False,
                "posting_delay": self.posting_delay,
                "randomized_time": None
            }
        
        # Get top theses
        theses = self.get_top_theses(hours=hours, top_n=top_n)
        
        if not theses or len(theses) == 0:
            print("[STAGE 11A] Not enough theses to build thread")
            return {
                "tweets": [],
                "theses_count": 0,
                "ready_to_post": False,
                "posting_delay": self.posting_delay,
                "randomized_time": None
            }
        
        # Format into tweets
        tweets = self.format_thread_tweets(theses)
        
        if not tweets:
            print("[STAGE 11A] Failed to format tweets")
            return {
                "tweets": [],
                "theses_count": 0,
                "ready_to_post": False,
                "posting_delay": self.posting_delay,
                "randomized_time": None
            }
        
        # Calculate randomized posting time
        scheduled_time = self.get_scheduled_time(base_hour=9, base_minute=0)
        print(f"[STAGE 11A] Thread scheduled for {scheduled_time['formatted']} (randomized ±{self.post_time_randomization} min)")
        print(f"[STAGE 11A] ✓ Thread ready: {len(tweets)} tweets from {len(theses)} theses")
        
        return {
            "tweets": tweets,
            "theses_count": len(theses),
            "ready_to_post": True,
            "posting_delay": self.posting_delay,
            "randomized_time": scheduled_time['formatted'],
            "scheduled_hour": scheduled_time['hour'],
            "scheduled_minute": scheduled_time['minute']
        }

# Global instance
thread_builder = ThreadBuilder()

