"""
Engagement Multiplier - Convert post engagers → followers through strategic interaction
Works with Playwright browser automation (not X API)
"""
import json
import time
import re
from datetime import datetime
from pathlib import Path

class EngagementMultiplier:
    """Convert post engagers → followers through strategic interaction"""
    
    def __init__(self, page, bot_handle="k_shamil57907"):
        self.page = page
        self.bot_handle = bot_handle
        self.engagement_history_file = Path("engagement_history.json")
        self.follow_history_file = Path("follow_history.json")
        self.engagement_history = self._load_history()
        self.follow_history = self._load_follow_history()
    
    def _load_history(self):
        """Load engagement history from file"""
        try:
            if self.engagement_history_file.exists():
                with open(self.engagement_history_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def _save_history(self):
        """Save engagement history to file"""
        try:
            with open(self.engagement_history_file, 'w') as f:
                json.dump(self.engagement_history, f, indent=2)
        except Exception as e:
            print(f"[ENGAGEMENT] Failed to save history: {e}")
    
    def _load_follow_history(self):
        """Load follow history from file"""
        try:
            if self.follow_history_file.exists():
                with open(self.follow_history_file, 'r') as f:
                    return json.load(f)
        except Exception:
            pass
        return {"followed_users": [], "follow_timestamps": []}
    
    def _save_follow_history(self):
        """Save follow history to file"""
        try:
            with open(self.follow_history_file, 'w') as f:
                json.dump(self.follow_history, f, indent=2)
        except Exception as e:
            print(f"[ENGAGEMENT] Failed to save follow history: {e}")
    
    def get_post_engagers(self, tweet_url, min_followers=20, max_engagers=50):
        """
        Get everyone who liked/replied to your post using Playwright.
        
        Args:
            tweet_url: Full URL to the tweet (e.g., "https://x.com/k_shamil57907/status/123456")
            min_followers: Minimum follower count to include
            max_engagers: Maximum number of engagers to return
        
        Returns:
            List of engager dicts with user_id, username, followers, action, timestamp
        """
        engagers = []
        try:
            # Navigate to tweet
            self.page.goto(tweet_url, wait_until="networkidle")
            time.sleep(3)  # Wait for page to load
            
            # Get likers: Click "Liked by" or similar link
            try:
                # Look for "Liked by X and others" link
                likers_link = self.page.locator('a[href*="/likes"]').first
                if likers_link.count() > 0:
                    likers_link.click()
                    time.sleep(2)
                    
                    # Extract usernames and follower counts from likes modal
                    user_cards = self.page.locator('article[data-testid="tweet"]').all()
                    for card in user_cards[:max_engagers]:
                        try:
                            card_text = card.inner_text()
                            # Extract username (usually @username format)
                            username_match = re.search(r'@(\w+)', card_text)
                            if not username_match:
                                continue
                            username = username_match.group(1)
                            
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
                                engagers.append({
                                    'username': username,
                                    'followers': follower_count,
                                    'action': 'like',
                                    'timestamp': datetime.now().isoformat()
                                })
                        except Exception as e:
                            print(f"[ENGAGEMENT] Error extracting liker: {e}")
                            continue
                    
                    # Close modal
                    self.page.keyboard.press("Escape")
                    time.sleep(1)
            except Exception as e:
                print(f"[ENGAGEMENT] Could not get likers: {e}")
            
            # Get repliers: Search for replies to this tweet
            try:
                # Navigate back to tweet
                self.page.goto(tweet_url, wait_until="networkidle")
                time.sleep(2)
                
                # Scroll to see replies
                self.page.evaluate("window.scrollBy(0, 1000)")
                time.sleep(2)
                
                # Find reply cards
                reply_cards = self.page.locator('article[data-testid="tweet"]').all()
                for card in reply_cards[1:]:  # Skip first (original tweet)
                    try:
                        card_text = card.inner_text()
                        # Check if this is a reply (contains "Replying to" or similar)
                        if "Replying to" not in card_text and "@" + self.bot_handle not in card_text:
                            continue
                        
                        # Extract username
                        username_match = re.search(r'@(\w+)', card_text)
                        if not username_match:
                            continue
                        username = username_match.group(1)
                        
                        # Skip if it's the bot itself
                        if username.lower() == self.bot_handle.lower().replace('@', ''):
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
                            engagers.append({
                                'username': username,
                                'followers': follower_count,
                                'action': 'reply',
                                'timestamp': datetime.now().isoformat()
                            })
                    except Exception as e:
                        print(f"[ENGAGEMENT] Error extracting replier: {e}")
                        continue
            except Exception as e:
                print(f"[ENGAGEMENT] Could not get repliers: {e}")
            
            # Dedupe by username
            seen = set()
            unique_engagers = []
            for engager in engagers:
                if engager['username'] not in seen:
                    seen.add(engager['username'])
                    unique_engagers.append(engager)
            
            print(f"[ENGAGEMENT] Found {len(unique_engagers)} engagers for tweet")
            return unique_engagers[:max_engagers]
            
        except Exception as e:
            print(f"[ENGAGEMENT] Failed to fetch engagers: {e}")
            return []
    
    def auto_reply_to_quality_engagers(self, engagers, market="prediction markets", price="current odds"):
        """
        Reply to people who engaged (shows reciprocal engagement).
        Note: This should be called from the main bot loop which handles reply posting.
        
        Args:
            engagers: List of engager dicts
            market: Market name for context
            price: Price/odds for context
        
        Returns:
            List of usernames we replied to
        """
        replied_to = []
        for engager in engagers:
            if engager['followers'] < 20:
                continue  # Skip low-follower accounts
            
            # Check if we already replied to this user recently
            username = engager['username']
            if username in self.engagement_history:
                last_engaged = datetime.fromisoformat(self.engagement_history[username].get('last_engaged', ''))
                hours_since = (datetime.now() - last_engaged).total_seconds() / 3600
                if hours_since < 24:
                    continue  # Don't reply if we engaged in last 24h
            
            # Store for reply (will be handled by main loop)
            self.engagement_history[username] = {
                'last_engaged': datetime.now().isoformat(),
                'followers': engager['followers'],
                'action': engager['action'],
                'market': market,
                'price': price
            }
            replied_to.append(username)
            print(f"[ENGAGEMENT] Queued reply to @{username} ({engager['followers']} followers, {engager['action']})")
        
        self._save_history()
        return replied_to
    
    def smart_follow_back(self, engagers, max_follows_per_hour=5):
        """
        Follow back high-quality engagers (creates follower loop).
        Note: This should be called carefully to avoid rate limits.
        
        Args:
            engagers: List of engager dicts
            max_follows_per_hour: Maximum follows per hour (Twitter rate limit)
        
        Returns:
            Number of users followed
        """
        followed_count = 0
        current_time = time.time()
        
        # Clean old follow timestamps (older than 1 hour)
        hour_ago = current_time - 3600
        self.follow_history['follow_timestamps'] = [
            ts for ts in self.follow_history['follow_timestamps'] if ts > hour_ago
        ]
        
        # Check if we're at rate limit
        if len(self.follow_history['follow_timestamps']) >= max_follows_per_hour:
            print(f"[FOLLOW] Rate limit: Already followed {len(self.follow_history['follow_timestamps'])} users in last hour")
            return 0
        
        for engager in engagers:
            # Only follow if:
            # 1. They have 50+ followers (real account)
            # 2. We're not already following them
            # 3. We haven't followed them in last 24h
            if engager['followers'] < 50:
                continue
            
            username = engager['username']
            
            # Check if already following
            if username in self.follow_history['followed_users']:
                continue
            
            try:
                # Navigate to user profile
                profile_url = f"https://x.com/{username}"
                self.page.goto(profile_url, wait_until="networkidle")
                time.sleep(2)
                
                # Click follow button
                follow_button = self.page.locator('div[data-testid*="follow"]').first
                if follow_button.count() > 0:
                    button_text = follow_button.inner_text()
                    if "Follow" in button_text and "Following" not in button_text:
                        follow_button.click()
                        time.sleep(1)
                        
                        # Record follow
                        self.follow_history['followed_users'].append(username)
                        self.follow_history['follow_timestamps'].append(current_time)
                        followed_count += 1
                        
                        print(f"[FOLLOW] Followed @{username} ({engager['followers']} followers)")
                        
                        # Check rate limit
                        if len(self.follow_history['follow_timestamps']) >= max_follows_per_hour:
                            print(f"[FOLLOW] Rate limit reached ({max_follows_per_hour} follows/hour)")
                            break
                        
                        # Wait between follows (12 minutes = 5 follows/hour)
                        if followed_count < max_follows_per_hour:
                            time.sleep(720)  # 12 minutes
            except Exception as e:
                print(f"[FOLLOW] Failed to follow @{username}: {e}")
                continue
        
        self._save_follow_history()
        return followed_count
    
    def generate_engagement_report(self):
        """Daily: show which engagers might become followers"""
        total_engagers = len(self.engagement_history)
        high_quality = sum(1 for e in self.engagement_history.values() if e.get('followers', 0) >= 100)
        print(f"\n[ENGAGEMENT REPORT]")
        print(f"  Total engagers (all time): {total_engagers}")
        print(f"  High-quality (100+ followers): {high_quality}")
        print(f"  Estimated new followers: {high_quality * 0.3:.1f}")  # 30% conversion rate
        print(f"  Users followed: {len(self.follow_history.get('followed_users', []))}")

