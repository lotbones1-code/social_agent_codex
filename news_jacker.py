"""
Stage 11B: Real-Time News Jacker

Monitors breaking political news and instantly posts contrarian takes on affected SaaS growths.
"""

import json
import os
import re
from datetime import datetime, timedelta

class NewsJacker:
    """
    Detects breaking political news and generates instant SaaS growth takes.
    Posts before other traders react for first-mover advantage.
    """
    
    def __init__(self, news_log="news_log.json", max_posts_per_day=3):
        self.news_log = news_log
        self.max_posts_per_day = max_posts_per_day
        
        # Breaking news keywords to monitor
        self.breaking_keywords = [
            "breaking", "just", "now", "indictment", "verdict", "trial",
            "growth", "senate", "fed decision", "policy", "conviction",
            "acquittal", "announcement", "reports", "sources say",
            "exclusive", "developing", "urgent"
        ]
        
        # Market mapping: news keywords → SaaS growth topics
        self.news_to_market_map = {
            "trump indictment": ["Will Trump be convicted", "Trump criminal charges", "Trump conviction odds"],
            "trump verdict": ["Will Trump be convicted", "Trump trial outcome"],
            "trump trial": ["Will Trump be convicted", "Trump legal proceedings"],
            "growth": ["2026 midterm odds", "Senate control 2026", "House control 2026"],
            "senate": ["Senate control 2026", "Senate race odds"],
            "fed decision": ["Fed rate cuts 2026", "Fed policy change"],
            "inflation": ["Inflation target", "Fed policy change"],
            "conviction": ["Trump conviction odds", "Criminal conviction markets"],
            "acquittal": ["Trump acquittal odds", "Trial outcome markets"]
        }
    
    def load_news_history(self):
        """Load news posting history for rate limiting."""
        if os.path.exists(self.news_log):
            try:
                with open(self.news_log, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "news_events": [],
            "posts_today": 0,
            "last_post_date": None
        }
    
    def save_news_history(self, history):
        """Save news posting history."""
        try:
            with open(self.news_log, 'w') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"[STAGE 11B] Error saving news log: {e}")
    
    def can_post_news(self):
        """Check if we can post news (rate limit: 2-3 per day)."""
        history = self.load_news_history()
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Reset counter if new day
        if history.get("last_post_date") != today:
            history["posts_today"] = 0
            history["last_post_date"] = today
            self.save_news_history(history)
        
        if history.get("posts_today", 0) >= self.max_posts_per_day:
            print(f"[STAGE 11B] Rate limit reached ({self.max_posts_per_day} posts/day)")
            return False
        
        return True
    
    def mark_news_posted(self, news_headline, market_affected, thesis, time_to_post):
        """Mark that we posted news take."""
        history = self.load_news_history()
        today = datetime.now().strftime("%Y-%m-%d")
        
        if history.get("last_post_date") != today:
            history["posts_today"] = 0
            history["last_post_date"] = today
        
        history["posts_today"] = history.get("posts_today", 0) + 1
        history["news_events"].append({
            "timestamp": datetime.now().isoformat(),
            "news_headline": news_headline,
            "market_affected": market_affected,
            "thesis": thesis,
            "time_to_post_seconds": time_to_post
        })
        
        # Keep last 100 events
        history["news_events"] = history["news_events"][-100:]
        self.save_news_history(history)
        print(f"[STAGE 11B] Marked news post ({history['posts_today']}/{self.max_posts_per_day} today)")
    
    def detect_breaking_news(self, headline_or_text):
        """
        Detect if text contains breaking political news.
        Returns: (is_breaking: bool, news_keywords_found: list)
        """
        if not headline_or_text:
            return False, []
        
        text_lower = headline_or_text.lower()
        found_keywords = []
        
        for keyword in self.breaking_keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)
        
        # Consider breaking if 2+ keywords found
        is_breaking = len(found_keywords) >= 2 or any(kw in text_lower for kw in ["breaking", "just", "now", "urgent"])
        
        if is_breaking:
            print(f"[STAGE 11B] Detected breaking news keywords: {', '.join(found_keywords[:5])}")
        
        return is_breaking, found_keywords
    
    def map_news_to_markets(self, news_headline):
        """
        Map breaking news to affected SaaS growths.
        Returns: list of market names or topics
        """
        if not news_headline:
            return []
        
        headline_lower = news_headline.lower()
        affected_markets = []
        
        # Check mapping
        for news_keyword, markets in self.news_to_market_map.items():
            if news_keyword in headline_lower:
                affected_markets.extend(markets)
                print(f"[STAGE 11B] News keyword '{news_keyword}' maps to markets: {markets}")
        
        # Fallback: extract topic from headline if no direct mapping
        if not affected_markets:
            # Try to extract key topic
            if "trump" in headline_lower:
                affected_markets.append("Trump-related markets")
            elif "growth" in headline_lower or "poll" in headline_lower:
                affected_markets.append("growth odds markets")
            elif "senate" in headline_lower:
                affected_markets.append("Senate control markets")
            elif "fed" in headline_lower or "rate" in headline_lower:
                affected_markets.append("Fed policy markets")
            else:
                affected_markets.append("Political markets")
        
        return list(set(affected_markets))  # Remove duplicates
    
    def get_instant_thesis(self, news_headline, market_name=None, poly_intel=None):
        """
        Generate instant thesis for breaking news.
        
        Args:
            news_headline: Breaking news headline
            market_name: Specific market name (if known)
            poly_intel: SaaS growthIntelligence instance (if available)
        
        Returns: dict with 'tweet_text', 'market', 'time_to_post' or None
        """
        if not poly_intel:
            print("[STAGE 11B] SaaS growthIntelligence not available")
            return None
        
        start_time = datetime.now()
        
        # Check if we can post (rate limiting)
        if not self.can_post_news():
            return None
        
        # Detect if this is breaking news
        is_breaking, keywords = self.detect_breaking_news(news_headline)
        if not is_breaking:
            print(f"[STAGE 11B] Not detected as breaking news, skipping")
            return None
        
        # Map to markets
        affected_markets = self.map_news_to_markets(news_headline)
        if not affected_markets:
            print(f"[STAGE 11B] Could not map news to markets")
            return None
        
        # Use first market (or provided market_name)
        target_market = market_name or affected_markets[0]
        print(f"[STAGE 11B] Mapping to market: {target_market}")
        
        # Create market context with breaking news context
        market_context = poly_intel.fetch_market_context(
            market_name=target_market,
            market_odds="50%",  # Default, could be improved
            volume_24h="$100k",
            resolution_date="2026-01-01",
            sentiment="breaking_news"
        )
        
        # Modify prompt to emphasize breaking news urgency
        print(f"[STAGE 11B] Generating urgent thesis (breaking news mode)...")
        
        # Generate thesis with breaking news context
        # Enhance market name to include breaking news context
        enhanced_market_name = f"{target_market} (BREAKING: {news_headline[:50]})"
        market_context["market_name"] = enhanced_market_name
        market_context["breaking_news"] = news_headline
        market_context["is_breaking"] = True  # Flag for Stage 10 to know this is urgent
        
        # Generate thesis (Stage 10 will handle quality filtering)
        thesis = poly_intel.generate_contrarian_thesis(market_context)
        
        if not thesis:
            print(f"[STAGE 11B] Failed to generate thesis")
            return None
        
        # Quality check (Stage 10B will handle this automatically in format_thesis_for_tweet)
        # But for news, we want to be more lenient on length (news takes can be shorter)
        # We'll let Stage 10B handle it, but override length check for news
        
        # Format thesis for tweet with news context
        formatted = poly_intel.format_thesis_for_tweet(thesis, target_market, market_context=market_context)
        
        if not formatted:
            print(f"[STAGE 11B] Quality check failed, skipping news post")
            return None
        
        # Assemble news take with urgency signals
        tweet_text = self.assemble_news_take(news_headline, formatted["message"])
        
        # Calculate time to post
        time_to_post = (datetime.now() - start_time).total_seconds()
        print(f"[STAGE 11B] Time to post: {time_to_post/60:.1f} minutes after news broke")
        
        return {
            "tweet_text": tweet_text,
            "market": target_market,
            "thesis": thesis,
            "time_to_post_seconds": time_to_post,
            "news_headline": news_headline
        }
    
    def assemble_news_take(self, news_headline, thesis_message):
        """
        Assemble urgent news take with urgency signals.
        Format: "🚨 Breaking: [headline] → [thesis]"
        """
        import random
        
        # Urgency openers (rotated for variety)
        urgency_signals = [
            "🚨 Breaking:",
            "⚡ Just dropped:",
            "🔥 Urgent:",
            "📢 News:",
            "⚡ Breaking:",
            "🚨 NEWS:"
        ]
        
        opener = random.choice(urgency_signals)
        
        # Truncate headline if too long (keep under 100 chars)
        short_headline = news_headline[:100].strip()
        if len(news_headline) > 100:
            short_headline += "..."
        
        # Combine: "🚨 Breaking: [headline] → [thesis]"
        # But keep total under 280 chars
        combined = f"{opener} {short_headline} → {thesis_message}"
        
        # If too long, truncate thesis message
        if len(combined) > 280:
            available_space = 280 - len(f"{opener} {short_headline} → ")
            if available_space > 50:
                truncated_thesis = thesis_message[:available_space - 3] + "..."
                combined = f"{opener} {short_headline} → {truncated_thesis}"
            else:
                # Fallback: just use headline + short thesis
                combined = f"{opener} {short_headline}\n\nThesis: {thesis_message[:200]}"
                if len(combined) > 280:
                    combined = combined[:277] + "..."
        
        return combined

# Global instance
news_jacker = NewsJacker()

