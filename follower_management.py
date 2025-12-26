import json
import os
import time
from datetime import datetime, timedelta
import re

class FollowerManager:
    def __init__(self, follow_log="follow_log.json"):
        self.follow_log = follow_log
        self.log = self.load_log()
    
    def load_log(self):
        if os.path.exists(self.follow_log):
            try:
                with open(self.follow_log, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "followed_accounts": {},  # {handle: {followed_at, follow_back_status}}
            "unfollowed_accounts": [],
            "last_audit": None
        }
    
    def save_log(self):
        try:
            with open(self.follow_log, 'w') as f:
                json.dump(self.log, f, indent=2)
        except Exception as e:
            print(f"[UNFOLLOW] Error saving log: {e}")
    
    def record_follow(self, handle):
        """Log when we follow someone"""
        if handle and handle not in self.log["followed_accounts"]:
            self.log["followed_accounts"][handle] = {
                "followed_at": datetime.now().isoformat(),
                "follow_back_status": "pending"
            }
            self.save_log()
    
    def should_unfollow(self, handle):
        """
        Determine if we should unfollow this account
        
        Unfollow if:
        1. We followed them 7+ days ago and they DIDN'T follow back
        2. They have 0 followers (spam account)
        3. They're a bot/spam account (all caps, numbers, no posts)
        """
        
        follow_data = self.log["followed_accounts"].get(handle)
        
        if not follow_data:
            return False, ["not_in_log"]
        
        # Calculate how long we've been following
        try:
            followed_at = datetime.fromisoformat(follow_data["followed_at"])
            follow_duration_days = (datetime.now() - followed_at).days
        except Exception:
            follow_duration_days = 0
        
        # Already unfollowed?
        if handle in self.log["unfollowed_accounts"]:
            return False, ["already_unfollowed"]
        
        reasons = []
        
        # RULE 1: Followed 7+ days, no follow back
        if follow_duration_days >= 7:
            follow_back_status = follow_data.get("follow_back_status")
            if follow_back_status == "pending" or follow_back_status == "no":
                reasons.append("no_follow_back_7days")
        
        if reasons:
            print(f"[UNFOLLOW] Should unfollow @{handle}. Reasons: {', '.join(reasons)}")
            return True, reasons
        
        return False, ["still_following"]
    
    def parse_follower_count(self, followers_text):
        """Parse follower count from text like '1.2K followers' or '500 followers'"""
        if not followers_text:
            return 0
        try:
            # Extract number
            match = re.search(r'([\d.]+)\s*(K|M)?', followers_text.replace(',', ''))
            if match:
                number = float(match.group(1))
                suffix = match.group(2)
                if suffix == 'K':
                    return int(number * 1000)
                elif suffix == 'M':
                    return int(number * 1000000)
                else:
                    return int(number)
        except Exception:
            pass
        return 0
    
    def unfollow_dead_accounts(self, page):
        """
        Go through followed accounts and unfollow the ones that don't follow back
        
        Strategy:
        1. Navigate to your following list
        2. Check each account for follower count + follow-back status
        3. Unfollow accounts that don't meet criteria
        4. Log unfollows
        """
        print("[UNFOLLOW] Starting follower audit...")
        unfollowed_count = 0
        
        try:
            # Get bot handle
            bot_handle = os.getenv("BOT_HANDLE", "k_shamil57907")
            
            # Go to following list
            page.goto(f"https://x.com/{bot_handle}/following")
            time.sleep(3)
            
            # Wait for list to load
            for _ in range(30):
                if page.locator('[data-testid="UserCell"]').count() > 0:
                    break
                time.sleep(0.3)
            
            seen_handles = set()
            # Scroll through following list
            for scroll_attempt in range(10):  # Audit ~50 accounts
                following_items = page.locator('[data-testid="UserCell"]').all()
                
                for item in following_items:
                    try:
                        # Get handle from user name element
                        handle = None
                        try:
                            name_elem = item.locator('[data-testid="User-Name"]').first
                            if name_elem.count() > 0:
                                name_text = name_elem.inner_text()
                                # Extract handle (usually after @ symbol or in link)
                                handle_match = re.search(r'@(\w+)', name_text)
                                if handle_match:
                                    handle = handle_match.group(1)
                                else:
                                    # Try to get from link
                                    link_elem = item.locator('a[href*="/"]').first
                                    if link_elem.count() > 0:
                                        href = link_elem.get_attribute("href")
                                        if href:
                                            handle = href.split('/')[-1].replace('@', '')
                        except Exception:
                            pass
                        
                        if not handle or handle in seen_handles:
                            continue
                        seen_handles.add(handle)
                        
                        # Get follower count
                        followers = 0
                        try:
                            # Look for follower count text
                            followers_elem = item.locator('text=/\\d+[KM]?\\s*followers/i, text=/followers/i').first
                            if followers_elem.count() > 0:
                                followers_text = followers_elem.inner_text()
                                followers = self.parse_follower_count(followers_text)
                        except Exception:
                            pass
                        
                        # Check if they follow you back
                        # Look for "Following" button - if it shows "Follow" instead, they don't follow back
                        is_following_back = False
                        try:
                            # Check for "Following" button (they follow you back) vs just "Following" (we follow them)
                            following_button = item.locator('[data-testid*="follow"], button:has-text("Following"), button:has-text("Follow")').first
                            if following_button.count() > 0:
                                button_text = following_button.inner_text()
                                # If button says "Following" and we're on the following page, they likely follow back
                                # This is approximate - X's UI is complex
                                is_following_back = "Following" in button_text
                        except Exception:
                            pass
                        
                        # Update follow back status in log
                        if handle not in self.log["followed_accounts"]:
                            self.log["followed_accounts"][handle] = {
                                "followed_at": datetime.now().isoformat(),
                                "follow_back_status": "yes" if is_following_back else "no"
                            }
                        else:
                            self.log["followed_accounts"][handle]["follow_back_status"] = "yes" if is_following_back else "no"
                        self.save_log()
                        
                        # Determine if should unfollow
                        should_unfollow, reasons = self.should_unfollow(handle)
                        
                        # Additional checks on live data
                        if followers == 0:
                            reasons.append("zero_followers_spam")
                            should_unfollow = True
                        
                        if is_following_back:
                            # They follow you back, keep them
                            continue
                        
                        if should_unfollow:
                            # Click unfollow button
                            try:
                                unfollow_button = item.locator('button:has-text("Following"), [aria-label*="Following"]').first
                                if unfollow_button.count() > 0:
                                    unfollow_button.click()
                                    time.sleep(1)
                                    
                                    # Confirm unfollow dialog
                                    confirm_unfollow = page.locator('[data-testid="confirmationSheetConfirm"], button:has-text("Unfollow")').first
                                    if confirm_unfollow.count() > 0:
                                        confirm_unfollow.click()
                                        time.sleep(1)
                                        
                                        print(f"[UNFOLLOW ✓] Unfollowed @{handle}. Reasons: {', '.join(reasons)}")
                                        if handle not in self.log["unfollowed_accounts"]:
                                            self.log["unfollowed_accounts"].append(handle)
                                        self.save_log()
                                        unfollowed_count += 1
                                        time.sleep(1)  # Small delay between unfollows
                            except Exception as e:
                                print(f"[UNFOLLOW ERROR] Failed to unfollow @{handle}: {e}")
                                continue
                    
                    except Exception as e:
                        print(f"[UNFOLLOW ERROR] Failed on account: {e}")
                        continue
                
                # Scroll for more accounts
                try:
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(2)
                except Exception:
                    break
            
            self.log["last_audit"] = datetime.now().isoformat()
            self.save_log()
            print(f"[UNFOLLOW] Unfollowed {unfollowed_count} dead accounts")
            return unfollowed_count
        
        except Exception as e:
            print(f"[UNFOLLOW ERROR] {e}")
            import traceback
            traceback.print_exc()
            return 0

FOLLOWER_MGR = FollowerManager()

