"""
Stage 12: Smart Trending Jacker

Scans X trending topics, maps them to Polymarket markets, and hijacks high-value tweets
with early replies for first-mover advantage.
"""

import time
import random
import re
from datetime import datetime
from typing import List, Dict, Optional, Tuple

class TrendingJacker:
    def __init__(self, config=None):
        self.config = config or {}
        self.update_config(config)
        
        self.last_trend_scan = 0
        self.cached_trends = []
        self.trend_cache_time = 0
        self.replies_this_hour = []
        self.hour_start_time = time.time()
    
    def update_config(self, config=None):
        """Update config (called from bot loop with phase controller config)"""
        if config:
            self.config = config
        self.stage12_enabled = self.config.get("stage12_enabled", True)
        self.hourly_max_replies = self.config.get("stage12_hourly_max_replies", 5)
        self.trend_refresh_minutes = self.config.get("stage12_trend_refresh_minutes", 60)
        
    def should_run_trending_scan(self) -> bool:
        """Check if it's time to scan trends (hourly)"""
        if not self.stage12_enabled:
            return False
        
        elapsed = time.time() - self.last_trend_scan
        return elapsed >= (self.trend_refresh_minutes * 60)
    
    def can_post_stage12_reply(self) -> bool:
        """Check if we can post another Stage 12 reply this hour"""
        # Reset hourly counter if needed
        if time.time() - self.hour_start_time >= 3600:
            self.replies_this_hour = []
            self.hour_start_time = time.time()
        
        return len(self.replies_this_hour) < self.hourly_max_replies
    
    def scan_trending_topics(self, page) -> List[str]:
        """
        Scan X trending section and extract top trends.
        Returns list of trend names (strings).
        """
        try:
            # Navigate to X trending (or explore page) - short timeout to avoid blocking
            trending_url = "https://x.com/explore"
            page.goto(trending_url, wait_until="domcontentloaded", timeout=8000)  # 8 second timeout, don't wait for networkidle
            time.sleep(1)  # Reduced wait time
            
            trends = []
            
            # Try to find trending topics (X UI may vary)
            # Look for common selectors
            trend_selectors = [
                '[data-testid="trend"]',
                'a[href*="/hashtag/"]',
                'span[dir="ltr"]',  # Generic text spans
            ]
            
            for selector in trend_selectors:
                try:
                    elements = page.locator(selector).all()
                    for elem in elements[:10]:  # Top 10
                        text = elem.inner_text().strip()
                        if text and len(text) > 2 and len(text) < 50:
                            # Filter out non-trend text
                            if not text.startswith(('@', 'http')):
                                trends.append(text)
                except Exception:
                    continue
            
            # Deduplicate and clean
            trends = list(dict.fromkeys(trends))[:10]  # Keep first 10 unique
            
            if trends:
                print(f"[TRENDING_SCAN] Found {len(trends)} trends: {', '.join(trends[:5])}")
                self.last_trend_scan = time.time()
                self.cached_trends = trends
                self.trend_cache_time = time.time()
                return trends
            else:
                print("[TRENDING_SKIPPED] No trends found, UI may have changed")
                return []
                
        except Exception as e:
            # Graceful failure - don't block the main loop
            error_msg = str(e)[:100]
            if "timeout" in error_msg.lower() or "exceeded" in error_msg.lower():
                print(f"[TRENDING_SKIPPED] Timeout scanning trends, using cached or skipping this cycle")
            else:
                print(f"[TRENDING_SKIPPED] Failed to scan trends: {error_msg}")
            return []  # Return empty list, don't raise exception
    
    def get_cached_trends(self) -> List[str]:
        """Get cached trends if still fresh (< 2 hours old)"""
        if time.time() - self.trend_cache_time < (2 * 3600):
            return self.cached_trends
        return []
    
    def map_trend_to_markets(self, trend: str, poly_intel=None) -> List[Dict]:
        """
        Map a trend to Polymarket markets.
        Returns list of market dicts with: id, title, description
        """
        markets = []
        
        # Simple keyword-based mapping (can be enhanced with actual Polymarket API)
        trend_lower = trend.lower()
        
        # Priority: Elections, Politics, Major Events
        if any(kw in trend_lower for kw in ["trump", "biden", "election", "senate", "congress", "president"]):
            # Political markets
            markets.append({
                "id": f"trend_{trend[:20]}",
                "title": f"{trend} Market",
                "description": f"Polymarket market related to {trend}"
            })
        elif any(kw in trend_lower for kw in ["war", "ukraine", "russia", "geopolitics"]):
            # Geopolitical markets
            markets.append({
                "id": f"trend_{trend[:20]}",
                "title": f"{trend} Market",
                "description": f"Polymarket market related to {trend}"
            })
        elif any(kw in trend_lower for kw in ["crypto", "bitcoin", "ethereum", "market"]):
            # Crypto/finance markets
            markets.append({
                "id": f"trend_{trend[:20]}",
                "title": f"{trend} Market",
                "description": f"Polymarket market related to {trend}"
            })
        
        # If poly_intel exists, try to use it for better market matching
        if poly_intel and markets:
            # Could enhance with actual market search here
            pass
        
        return markets[:3]  # Return up to 3 markets
    
    def find_trending_tweets(self, page, trend: str, max_tweets: int = 5) -> List:
        """
        Find recent tweets about a trend.
        Returns list of tweet cards (Playwright locators).
        """
        try:
            # Search for the trend
            search_query = trend.replace(" ", "%20")
            search_url = f"https://x.com/search?q={search_query}&src=typed_query&f=live"
            page.goto(search_url, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            
            # Wait for tweets to load
            for _ in range(10):
                if page.locator('article[data-testid="tweet"]').count() > 0:
                    break
                time.sleep(0.5)
            
            # Collect tweet cards
            cards = page.locator('article[data-testid="tweet"]')
            count = min(cards.count(), max_tweets)
            
            return [cards.nth(i) for i in range(count)]
            
        except Exception as e:
            print(f"[TRENDING_ERROR] Failed to find tweets for trend '{trend}': {str(e)[:100]}")
            return []
    
    def is_good_hijack_target(self, card, trend: str) -> Tuple[bool, str]:
        """
        Check if a tweet is a good target for hijacking.
        Returns (is_good: bool, reason: str)
        """
        try:
            tweet_text = card.inner_text().lower()
            
            # Check for betting/odds language
            has_intent = any(kw in tweet_text for kw in ["bet", "wager", "odds", "prediction", "betting", "poll"])
            
            # Try to get engagement (likes)
            likes = 0
            try:
                likes_elem = card.locator('[data-testid="like"]').first
                if likes_elem.count() > 0:
                    likes_text = likes_elem.inner_text()
                    likes_str = likes_text.replace("K", "000").replace("M", "000000").replace(",", "").strip()
                    likes = int(''.join(filter(str.isdigit, likes_str))) if likes_str else 0
            except Exception:
                pass
            
            # Prefer tweets with some engagement
            if likes >= 10 or has_intent:
                return True, "high_engagement_or_intent"
            
            return False, "low_engagement"
            
        except Exception as e:
            return False, f"error_{str(e)[:20]}"
    
    def generate_stage12_reply(self, trend: str, market: Dict, tweet_text: str, openai_client=None) -> Optional[str]:
        """
        Generate a Stage 12 reply for trending hijack.
        Returns reply text or None.
        """
        if not openai_client:
            # Fallback template
            return f"Everyone's screaming {trend} but Polymarket has this way tighter than people think. Value's probably on the other side."
        
        try:
            prompt = f"""You are a Polymarket trader hijacking a trending topic.

TREND: {trend}
MARKET: {market.get('title', 'Polymarket market')}
TWEET: {tweet_text[:300]}

Write a SHORT, OPINIONATED reply (1-2 sentences, 120-220 chars). Sound like a real trader. Be specific and contrarian. No templates, no "Notice how" patterns. Do NOT include any links."""
            
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a trader. Write short, direct, opinionated replies. No templates."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                max_tokens=120,
            )
            
            reply = response.choices[0].message.content.strip()
            if reply.startswith('"') and reply.endswith('"'):
                reply = reply[1:-1]
            
            return reply
            
        except Exception as e:
            print(f"[TRENDING_REPLY_FAIL] Generation error: {str(e)[:100]}")
            return None
    
    def record_reply(self, tweet_id: str):
        """Record that we posted a Stage 12 reply"""
        self.replies_this_hour.append({
            "tweet_id": tweet_id,
            "time": time.time()
        })

# Global instance
TRENDING_JACKER = TrendingJacker()

