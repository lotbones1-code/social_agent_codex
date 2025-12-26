"""
Stage 12: Trending Quote-Tweet Stage

Scans for high-engagement tweets (especially with videos) in our niche keywords,
then quote-tweets them with a short, human-style reaction + Polymarket angle + CTA.

Frequency: 2-4 times per day max
Safety: Respects global hourly action cap, no media downloading/re-uploading
"""

import json
import os
import time
import random
from datetime import datetime, timezone


def get_today_str():
    """Return today's date in YYYY-MM-DD format (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class TrendingQuoteTweet:
    """Manages trending quote-tweet stage (Stage 12)."""
    
    def __init__(self, log_file="stage_12_quote_log.json", max_per_day=8):
        self.log_file = log_file
        self.max_per_day = max_per_day  # Increased to 6-8/day for high volume on high quality
        self.log = self.load_log()
        
        # Elite curation thresholds
        self.VIDEO_ENGAGEMENT_THRESHOLD = 15000  # Only top-tier viral videos
        self.TEXT_ENGAGEMENT_THRESHOLD = 25000  # Only massive text tweets
    
    def load_log(self):
        """Load quote-tweet history."""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    # Reset daily counter if new day
                    today = get_today_str()
                    if data.get("last_date") != today:
                        data["quotes_today"] = 0
                        data["last_date"] = today
                    return data
            except Exception:
                pass
        return {
            "last_date": get_today_str(),
            "quotes_today": 0,
            "quoted_tweet_ids": []
        }
    
    def save_log(self):
        """Save quote-tweet history."""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.log, f, indent=2)
        except Exception as e:
            print(f"[STAGE 12] Error saving log: {e}")
    
    def can_quote_tweet(self):
        """Check if we can post a quote-tweet (rate limit: 2-4/day)."""
        today = get_today_str()
        if self.log.get("last_date") != today:
            self.log["quotes_today"] = 0
            self.log["last_date"] = today
            self.save_log()
        
        if self.log.get("quotes_today", 0) >= self.max_per_day:
            print(f"[STAGE 12] Daily quote-tweet limit reached ({self.max_per_day}/day)")
            return False
        
        return True
    
    def mark_quoted(self, tweet_id):
        """Mark a tweet as quoted."""
        self.log["quotes_today"] = self.log.get("quotes_today", 0) + 1
        self.log["quoted_tweet_ids"] = self.log.get("quoted_tweet_ids", [])
        self.log["quoted_tweet_ids"].append(tweet_id)
        # Keep last 500 tweet IDs
        self.log["quoted_tweet_ids"] = self.log["quoted_tweet_ids"][-500:]
        self.save_log()
    
    def already_quoted(self, tweet_id):
        """Check if we already quoted this tweet."""
        return tweet_id in self.log.get("quoted_tweet_ids", [])
    
    def extract_engagement(self, card):
        """Extract engagement metrics (likes, retweets, views) from tweet card."""
        try:
            likes = 0
            retweets = 0
            views = 0
            
            # Try to extract likes
            try:
                likes_elem = card.locator('[data-testid="like"]').first
                if likes_elem.count() > 0:
                    likes_text = likes_elem.inner_text() or ""
                    likes = self._parse_count(likes_text)
            except Exception:
                pass
            
            # Try to extract retweets
            try:
                retweet_elem = card.locator('[data-testid="retweet"]').first
                if retweet_elem.count() > 0:
                    retweet_text = retweet_elem.inner_text() or ""
                    retweets = self._parse_count(retweet_text)
            except Exception:
                pass
            
            # Try to extract views (if visible)
            try:
                views_text = card.locator('text=/\\d+[KM]?\\s*Views/i').first.inner_text() if card.locator('text=/\\d+[KM]?\\s*Views/i').first.count() > 0 else ""
                if views_text:
                    views = self._parse_count(views_text)
            except Exception:
                pass
            
            return {"likes": likes, "retweets": retweets, "views": views, "total": likes + retweets + views}
        except Exception:
            return {"likes": 0, "retweets": 0, "views": 0, "total": 0}
    
    def _parse_count(self, count_str):
        """Parse count string like '1.2K' or '5M' to integer."""
        try:
            count_str = count_str.upper().strip()
            if 'K' in count_str:
                return int(float(count_str.replace('K', '').replace(',', '')) * 1000)
            elif 'M' in count_str:
                return int(float(count_str.replace('M', '').replace(',', '')) * 1000000)
            else:
                # Remove non-numeric chars
                return int(''.join(filter(str.isdigit, count_str)) or 0)
        except Exception:
            return 0
    
    def has_video(self, card):
        """Check if tweet has a video."""
        try:
            video_selectors = [
                '[data-testid="video"]',
                'video',
                '[aria-label*="video"]',
                '[aria-label*="Video"]',
            ]
            for selector in video_selectors:
                if card.locator(selector).first.count() > 0:
                    return True
            return False
        except Exception:
            return False
    
    def is_high_engagement(self, card, min_likes=None, min_total=None):
        """Check if tweet has high engagement (ELITE thresholds only).
        
        Videos: 15,000+ total engagement (top-tier viral content)
        Text: 25,000+ total engagement (only massive tweets)
        """
        engagement = self.extract_engagement(card)
        
        # Use elite thresholds
        if min_likes is None:
            min_likes = self.TEXT_ENGAGEMENT_THRESHOLD
        if min_total is None:
            min_total = self.TEXT_ENGAGEMENT_THRESHOLD
        
        # Prioritize videos with elite threshold
        if self.has_video(card):
            # Elite threshold for videos: 15K+ total engagement
            return engagement["total"] >= self.VIDEO_ENGAGEMENT_THRESHOLD
        
        # For text tweets, require elite engagement: 25K+ total
        return engagement["total"] >= self.TEXT_ENGAGEMENT_THRESHOLD
    
    def generate_quote_text(self, tweet_text, openai_client, referral_link):
        """Generate a short, human-style reaction quote text with Polymarket angle."""
        if not openai_client:
            # Fallback quote text
            fallback_quotes = [
                "This is exactly what prediction markets are pricing. Wild.",
                "The odds on this are moving fast. Worth watching.",
                "Polymarket traders are already on this. Markets don't lie.",
            ]
            return random.choice(fallback_quotes) + f" {referral_link}"
        
        try:
            system_prompt = """You are a smart Polymarket trader reacting to trending tweets.

Your goal: Write a SHORT (under 200 chars), human-style reaction that:
- Adds a prediction market/Polymarket angle to the original tweet
- Sounds like a real person reacting (not a bot)
- Is spicy, opinionated, or insightful
- Ends with a CTA linking to Polymarket

Rules:
- Keep it under 200 characters total
- Sound natural and conversational
- Reference odds, markets, or trading when relevant
- Use 1-2 emojis max if it fits
- NO hashtags

Output ONLY the quote text, nothing else."""

            user_prompt = f"""Original tweet:
{tweet_text[:300]}

Write a short, spicy reaction that connects this to prediction markets/Polymarket. 
Make it human and opinionated. Keep under 200 chars. Include the URL at the end: {referral_link}"""

            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.8,
                max_tokens=150,
            )
            
            quote_text = response.choices[0].message.content.strip()
            
            # Clean up quotes
            if quote_text.startswith('"') and quote_text.endswith('"'):
                quote_text = quote_text[1:-1]
            
            # Ensure link is included
            if referral_link not in quote_text:
                quote_text = f"{quote_text} {referral_link}"
            
            # Ensure it fits in quote tweet limit (280 chars for quote text)
            if len(quote_text) > 280:
                quote_text = quote_text[:270] + "… " + referral_link
            
            return quote_text
            
        except Exception as e:
            print(f"[STAGE 12] Error generating quote text: {e}")
            # Fallback
            fallback_quotes = [
                "This is exactly what prediction markets are pricing. Wild.",
                "The odds on this are moving fast. Worth watching.",
                "Polymarket traders are already on this. Markets don't lie.",
            ]
            return random.choice(fallback_quotes) + f" {referral_link}"


# Global instance
trending_quote_tweet = TrendingQuoteTweet()

