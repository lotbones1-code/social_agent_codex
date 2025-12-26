"""
Authority Targeting - Target high-follower accounts to maximize viral potential
Works with Playwright browser automation (not X API)
"""
import random
import time
import re
from datetime import datetime

class AuthorityTargeter:
    """Target high-follower accounts to maximize viral potential"""
    
    def __init__(self, page, bot_handle="k_shamil57907"):
        self.page = page
        self.bot_handle = bot_handle
        self.replied_to = set()  # Track who we've replied to recently
    
    def find_crypto_influencers(self, min_followers=1000, max_results=10):
        """
        Find crypto personalities posting about Polymarket using Playwright.
        
        Args:
            min_followers: Minimum follower count (extracted from page)
            max_results: Maximum number of influencers to return
        
        Returns:
            List of influencer dicts with username, followers, tweet_id, relevance_keyword
        """
        keywords = [
            "polymarket",
            "prediction markets",
            "betting markets",
            "crypto",
            "finance",
            "odds",
            "bitcoin prediction",
            "election odds",
            "crypto trading",
            "market analysis"
        ]
        
        influencers = []
        seen_usernames = set()
        total_cards_scanned = 0
        cards_meeting_threshold = 0
        
        for keyword in keywords[:3]:  # Limit to 3 keywords to avoid rate limits
            try:
                # Search for tweets (filter applied silently in backend, not in URL)
                search_url = f"https://x.com/search?q={keyword}&src=typed_query&f=live"
                try:
                    # Use domcontentloaded instead of networkidle for faster, more reliable loading
                    self.page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                    # Wait for tweet containers to appear (proves search page is usable)
                    self.page.wait_for_selector('article[data-testid="tweet"]', timeout=30000)
                except Exception as goto_error:
                    print(f"[AUTHORITY] Warning: Page navigation timeout for {keyword}: {goto_error}")
                    # Continue to next keyword instead of crashing
                    continue
                
                time.sleep(3)  # Wait for results
                
                # Scroll to load more results
                self.page.evaluate("window.scrollBy(0, 2000)")
                time.sleep(2)
                
                # Find tweet cards
                tweet_cards = self.page.locator('article[data-testid="tweet"]').all()
                
                for card in tweet_cards[:20]:  # Limit to first 20 tweets per keyword
                    try:
                        total_cards_scanned += 1
                        card_text = card.inner_text()
                        
                        # Backend filter: Skip retweets (filter applied silently, not in URL)
                        retweet_indicators = [
                            "retweeted by",
                            "reposted by"
                        ]
                        if any(indicator in card_text.lower() for indicator in retweet_indicators):
                            continue  # Skip retweets silently
                        
                        # Extract username
                        username_match = re.search(r'@(\w+)', card_text)
                        if not username_match:
                            continue
                        username = username_match.group(1)
                        
                        # Skip if already seen or is the bot itself
                        if username in seen_usernames or username.lower() == self.bot_handle.lower().replace('@', ''):
                            continue
                        
                        # Extract follower count
                        follower_count = 0
                        follower_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*followers?', card_text)
                        if follower_match:
                            count_str = follower_match.group(1).upper()
                            if 'K' in count_str:
                                follower_count = int(float(count_str.replace('K', '')) * 1000)
                            elif 'M' in count_str:
                                follower_count = int(float(count_str.replace('M', '')) * 1000000)
                            else:
                                follower_count = int(float(count_str))
                        
                        if follower_count >= min_followers:
                            cards_meeting_threshold += 1
                            # Extract tweet ID from link
                            tweet_link = card.locator('a[href*="/status/"]').first
                            tweet_id = None
                            if tweet_link.count() > 0:
                                href = tweet_link.get_attribute('href') or ''
                                match = re.search(r'/status/(\d+)', href)
                                if match:
                                    tweet_id = match.group(1)
                            
                            if tweet_id:
                                influencers.append({
                                    'username': username,
                                    'followers': follower_count,
                                    'tweet_id': tweet_id,
                                    'relevance_keyword': keyword
                                })
                                seen_usernames.add(username)
                                
                                if len(influencers) >= max_results:
                                    break
                    except Exception as e:
                        print(f"[AUTHORITY] Error extracting influencer: {e}")
                        continue
                
                if len(influencers) >= max_results:
                    break
                    
            except Exception as e:
                print(f"[AUTHORITY] Error searching for {keyword}: {e}")
                continue
        
        # Sort by follower count (descending)
        influencers.sort(key=lambda x: x['followers'], reverse=True)
        
        if len(influencers) == 0:
            print(f"[AUTHORITY] Found 0 influencers (min {min_followers} followers). Scanned {total_cards_scanned} cards, {cards_meeting_threshold} met follower threshold")
        else:
            print(f"[AUTHORITY] Found {len(influencers)} influencers (min {min_followers} followers)")
        return influencers
    
    def target_quality_reply(self, tweet_id, influencer_username):
        """
        Generate a high-quality reply for an influencer (not generic).
        Note: This returns the reply text - actual posting is handled by main loop.
        
        Args:
            tweet_id: Tweet ID to reply to
            influencer_username: Username of the influencer
        
        Returns:
            Reply text string (or None if we shouldn't reply)
        """
        # Check if we already replied to this influencer recently
        if influencer_username in self.replied_to:
            return None
        
        high_quality_replies = [
            "This is underselling the complexity. The real edge is in the tail risk. What's your volatility assumption?",
            "You're not wrong, but the market is repricing this faster than most realize. The recent data changed everything.",
            "Narrative is shifting faster than the odds reflect. Position-wise, I'm curious if you're seeing the same inflection?",
            "Good call, but there's a micro-edge here most people miss: the orderbook depth doesn't match the price action.",
            "Interesting take. The crowd is basically saying this via markets. Curious if you think that's rich or cheap.",
        ]
        
        reply = random.choice(high_quality_replies)
        
        # Store that we're replying to this influencer
        self.replied_to.add(influencer_username)
        
        print(f"[AUTHORITY] Generated quality reply for @{influencer_username}: {reply[:50]}...")
        return reply
    
    def find_reply_opportunities(self, max_opportunities=5):
        """
        Daily: Find 3-5 influencer tweets to reply to.
        
        Args:
            max_opportunities: Maximum number of influencers to target
        
        Returns:
            List of dicts with tweet_id, username, reply_text
        """
        opportunities = []
        
        # Find influencers (start with 200+ followers for broader reach)
        influencers = self.find_crypto_influencers(min_followers=200, max_results=max_opportunities * 2)
        
        for influencer in influencers[:max_opportunities]:
            reply_text = self.target_quality_reply(influencer['tweet_id'], influencer['username'])
            if reply_text:
                opportunities.append({
                    'tweet_id': influencer['tweet_id'],
                    'username': influencer['username'],
                    'followers': influencer['followers'],
                    'reply_text': reply_text,
                    'tweet_url': f"https://x.com/{influencer['username']}/status/{influencer['tweet_id']}"
                })
        
        print(f"[AUTHORITY] Found {len(opportunities)} reply opportunities")
        return opportunities
    
    def reset_replied_tracking(self):
        """Reset the replied tracking (call daily to allow new replies)"""
        self.replied_to = set()
        print("[AUTHORITY] Reset replied tracking")

