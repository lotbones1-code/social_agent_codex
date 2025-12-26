import random
import time
from datetime import datetime

class EngagementMixer:
    """
    Makes the bot look like a real human by mixing engagement types:
    - Most activity is still replies (what we're good at)
    - But also likes, retweets, and quotes to break up the pattern
    
    Engagement mix ratio:
    - 75% replies (keep main focus)
    - 15% likes on good posts
    - 7% retweets
    - 3% quote tweets with added value
    """
    
    def __init__(self):
        self.last_engagement_type = None
        self.engagement_log = []
    
    def get_next_engagement_type(self):
        """
        Decide what type of engagement to do next
        Don't repeat same type twice in a row
        """
        rand = random.random()
        
        if rand < 0.75:
            engagement_type = "reply"
        elif rand < 0.90:
            engagement_type = "like"
        elif rand < 0.97:
            engagement_type = "retweet"
        else:
            engagement_type = "quote_tweet"
        
        # Don't repeat the same type (looks too mechanical)
        if engagement_type == self.last_engagement_type:
            # Pick a different one
            alternatives = ["reply", "like", "retweet", "quote_tweet"]
            alternatives.remove(engagement_type)
            engagement_type = random.choice(alternatives)
        
        self.last_engagement_type = engagement_type
        return engagement_type
    
    def should_like_this_post(self, post_data):
        """
        Determine if we should like a post
        
        Like if:
        1. Post has 100+ likes (proven quality)
        2. Post is about Polymarket/prediction markets/politics
        3. Post is NOT already liked by us
        4. Posted in last 48 hours (fresh)
        """
        likes = post_data.get("likes", 0)
        text = post_data.get("text", "").lower()
        is_liked = post_data.get("is_liked", False)
        
        good_keywords = [
            "polymarket",
            "prediction market",
            "betting odds",
            "2026",
            "midterm",
            "senate",
            "election betting"
        ]
        
        has_good_topic = any(keyword in text for keyword in good_keywords)
        
        if likes >= 100 and has_good_topic and not is_liked:
            print(f"[ENGAGEMENT] ✓ Will like this post ({likes} likes)")
            return True
        
        return False
    
    def should_retweet_this_post(self, post_data):
        """
        Determine if we should retweet
        
        Retweet if:
        1. Post has 500+ likes (very high quality)
        2. About prediction markets or politics
        3. NOT from a bot/spam account
        """
        likes = post_data.get("likes", 0)
        text = post_data.get("text", "").lower()
        author_followers = post_data.get("author_followers", 0)
        is_retweeted = post_data.get("is_retweeted", False)
        
        good_keywords = [
            "polymarket",
            "prediction market",
            "betting",
            "2026",
            "midterm"
        ]
        
        has_good_topic = any(keyword in text for keyword in good_keywords)
        
        # Only retweet high-quality posts from real accounts
        if likes >= 500 and has_good_topic and author_followers >= 100 and not is_retweeted:
            print(f"[ENGAGEMENT] ✓ Will retweet this post ({likes} likes, {author_followers} followers)")
            return True
        
        return False
    
    def generate_quote_tweet(self, original_text):
        """
        Generate a quote tweet that adds value
        
        Quote tweet templates:
        - Add context or analysis
        - Build on the original point
        - Never just repeat the original (adds value)
        """
        
        templates = [
            "This is huge. {insight}",
            "Exactly. And here's what people miss: {insight}",
            "Perfect take. The market is already pricing in {insight}",
            "Spot on. Watch how this moves the odds on {insight}",
        ]
        
        insights = [
            "the odds shift will be immediate",
            "volatility is coming",
            "this changes everything",
            "the timing matters more than most think",
            "consensus is already moving",
        ]
        
        template = random.choice(templates)
        insight = random.choice(insights)
        
        quote_text = template.format(insight=insight)
        
        return quote_text
    
    def like_post(self, page, post):
        """Actually click the like button"""
        try:
            like_button = post.locator('[data-testid="like"]').first
            if like_button.count() > 0:
                like_button.click()
                time.sleep(1)
                print("[ENGAGEMENT ✓] Liked post")
                return True
        except Exception as e:
            print(f"[ENGAGEMENT ERROR] Failed to like: {e}")
        return False
    
    def retweet_post(self, page, post):
        """Actually click the retweet button"""
        try:
            retweet_button = post.locator('[data-testid="retweet"]').first
            if retweet_button.count() > 0:
                retweet_button.click()
                time.sleep(1)
                
                # Click "Retweet" in the menu
                retweet_confirm = page.locator('text="Retweet"').first
                if retweet_confirm.count() > 0:
                    retweet_confirm.click()
                    time.sleep(1)
                    print("[ENGAGEMENT ✓] Retweeted post")
                    return True
        except Exception as e:
            print(f"[ENGAGEMENT ERROR] Failed to retweet: {e}")
        return False
    
    def quote_tweet_post(self, page, post, quote_text):
        """Quote tweet a post"""
        try:
            retweet_button = post.locator('[data-testid="retweet"]').first
            if retweet_button.count() > 0:
                retweet_button.click()
                time.sleep(1)
                
                # Click "Quote Tweet" option
                quote_option = page.locator('text="Quote Tweet"').first
                if quote_option.count() > 0:
                    quote_option.click()
                    time.sleep(2)
                    
                    # Type the quote
                    compose_box = page.locator('[data-testid="tweetTextarea_0"]').first
                    if compose_box.count() > 0:
                        compose_box.click()
                        time.sleep(0.5)
                        compose_box.fill(quote_text)
                        time.sleep(1)
                        
                        # Post
                        post_button = page.locator('[data-testid="tweetButton"]').first
                        if post_button.count() > 0:
                            post_button.click()
                            time.sleep(2)
                            
                            print(f"[ENGAGEMENT ✓] Quote tweeted with: {quote_text[:50]}")
                            return True
        except Exception as e:
            print(f"[ENGAGEMENT ERROR] Failed to quote tweet: {e}")
        return False
    
    def log_engagement(self, engagement_type, post_id, success):
        """Track engagement for analytics"""
        self.engagement_log.append({
            "type": engagement_type,
            "post_id": post_id,
            "success": success,
            "timestamp": datetime.now().isoformat()
        })

ENGAGEMENT_MIXER = EngagementMixer()

