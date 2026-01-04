import json
import os
import time
from datetime import datetime, timedelta

class PostCleanup:
    def __init__(self, cleanup_log="cleanup_log.json"):
        self.cleanup_log = cleanup_log
        self.log = self.load_log()
    
    def load_log(self):
        if os.path.exists(self.cleanup_log):
            try:
                with open(self.cleanup_log, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "deleted_posts": [],
            "reasons": {},
            "last_cleanup": None
        }
    
    def save_log(self):
        try:
            with open(self.cleanup_log, 'w') as f:
                json.dump(self.log, f, indent=2)
        except Exception as e:
            print(f"[CLEANUP] Error saving log: {e}")
    
    def is_shitty_post(self, post_data):
        """
        Determine if a post should be deleted.
        
        Delete if ANY of these are true:
        1. Has image attachments (the dumb AI images we had)
        2. Zero views after 48+ hours
        3. Mentions outdated content (2024 references)
        4. Posted more than 7 days ago with under 5 views
        5. Under 1 view after 72+ hours (definitely dead)
        """
        
        post_id = post_data.get("id")
        text = post_data.get("text", "").lower()
        views = post_data.get("views", 0)
        likes = post_data.get("likes", 0)
        replies = post_data.get("replies", 0)
        has_image = post_data.get("has_image", False)
        has_video = post_data.get("has_video", False)
        posted_at = post_data.get("created_at")  # ISO format or datetime string
        
        # Calculate age
        if posted_at:
            try:
                # Try parsing ISO format
                if 'T' in str(posted_at):
                    post_time = datetime.fromisoformat(str(posted_at).replace('Z', '+00:00'))
                else:
                    # Try parsing other formats
                    post_time = datetime.strptime(str(posted_at), "%Y-%m-%d %H:%M:%S")
                age_hours = (datetime.now(post_time.tzinfo if post_time.tzinfo else None) - post_time.replace(tzinfo=None)).total_seconds() / 3600
            except Exception:
                age_hours = 0
        else:
            age_hours = 0
        
        reasons = []
        
        # RULE 1: Has shitty AI-generated images (not videos)
        if has_image and not has_video:
            reasons.append("had_dumb_image")
        
        # RULE 2: Zero views after 48+ hours
        if age_hours >= 48 and views == 0:
            reasons.append("zero_views_48h")
        
        # RULE 3: Outdated content
        outdated_keywords = [
            "biden 2024",
            "trump 2024",
            "2024",  # Block stale year references
            "biden vs trump",
            "2024 race"
        ]
        for keyword in outdated_keywords:
            if keyword in text:
                reasons.append("outdated_content")
                break
        
        # RULE 4: Old post (7+ days) with minimal engagement
        if age_hours >= 168 and views < 5:  # 168 hours = 7 days
            reasons.append("old_low_engagement")
        
        # RULE 5: Dead post (72+ hours, under 1 view)
        if age_hours >= 72 and views < 1:
            reasons.append("completely_dead")
        
        if reasons:
            print(f"[CLEANUP] Deleting post {post_id}. Reasons: {', '.join(reasons)}")
            if post_id:
                self.log["deleted_posts"].append(post_id)
                self.log["reasons"][post_id] = reasons
                self.save_log()
            return True
        
        return False
    
    def delete_shitty_posts(self, page):
        """
        Go through recent posts and delete the shitty ones
        
        Strategy:
        1. Navigate to your profile
        2. Load last 20-30 posts
        3. Check each for "shitty" criteria
        4. Delete the ones that qualify
        5. Log deleted posts
        """
        print("[CLEANUP] Starting post cleanup sweep...")
        deleted_count = 0
        
        try:
            # Get bot handle from environment or use default
            bot_handle = os.getenv("BOT_HANDLE", "k_shamil57907")
            
            # Go to your profile
            page.goto(f"https://x.com/{bot_handle}")
            time.sleep(3)
            
            # Scroll and collect posts
            seen_post_ids = set()
            for scroll_attempt in range(5):  # Collect ~20 posts
                posts = page.locator('article[data-testid="tweet"]').all()
                
                for post in posts:
                    try:
                        # Extract post ID using the same method as extract_tweet_id
                        post_id = None
                        try:
                            post_id = post.get_attribute("data-tweet-id")
                        except Exception:
                            pass
                        
                        if not post_id or post_id in seen_post_ids or post_id in self.log["deleted_posts"]:
                            continue
                        
                        seen_post_ids.add(post_id)
                        
                        # Get text
                        try:
                            text_elem = post.locator('[data-testid="tweetText"]').first
                            text = text_elem.inner_text() if text_elem.count() > 0 else ""
                        except Exception:
                            text = ""
                        
                        # Get engagement (use likes as proxy for views)
                        views = 0
                        likes = 0
                        try:
                            # Try to get likes count
                            likes_elem = post.locator('[data-testid="like"]').first
                            if likes_elem.count() > 0:
                                likes_text = likes_elem.inner_text()
                                # Parse likes (handles K, M suffixes)
                                try:
                                    likes_str = likes_text.replace("K", "000").replace("M", "000000").replace(",", "").strip()
                                    likes = int(''.join(filter(str.isdigit, likes_str))) if likes_str else 0
                                except Exception:
                                    likes = 0
                            # Use likes as proxy for views (X doesn't always show views publicly)
                            views = likes * 10  # Rough estimate: 10 views per like
                        except Exception:
                            pass
                        
                        # Check for image/video
                        has_image = False
                        has_video = False
                        try:
                            has_image = post.locator('img[alt*="Image"], img[alt*="image"]').count() > 0
                            has_video = post.locator('video').count() > 0
                        except Exception:
                            pass
                        
                        # Get timestamp
                        created_at = None
                        try:
                            time_elem = post.locator('time').first
                            if time_elem.count() > 0:
                                created_at = time_elem.get_attribute("datetime")
                        except Exception:
                            pass
                        
                        post_data = {
                            "id": post_id,
                            "text": text,
                            "views": views,
                            "likes": likes,
                            "replies": 0,
                            "has_image": has_image,
                            "has_video": has_video,
                            "created_at": created_at
                        }
                        
                        # Check if shitty
                        if self.is_shitty_post(post_data):
                            # Click the "..." menu
                            try:
                                more_button = post.locator('[aria-label="More"], [aria-label="More options"]').first
                                if more_button.count() > 0:
                                    more_button.click()
                                    time.sleep(1)
                                    
                                    # Click "Delete"
                                    delete_option = page.locator('text="Delete"').first
                                    if delete_option.count() > 0:
                                        delete_option.click()
                                        time.sleep(1)
                                        
                                        # Confirm delete
                                        confirm_button = page.locator('[data-testid="confirmationSheetConfirm"]').first
                                        if confirm_button.count() > 0:
                                            confirm_button.click()
                                            time.sleep(2)
                                            
                                            print(f"[CLEANUP ✓] Deleted post {post_id}")
                                            deleted_count += 1
                                            # Small delay between deletions
                                            time.sleep(1)
                                    else:
                                        # Cancel menu if delete option not found
                                        page.keyboard.press("Escape")
                            except Exception as e:
                                print(f"[CLEANUP ERROR] Failed to delete post {post_id}: {e}")
                                # Cancel menu on error
                                try:
                                    page.keyboard.press("Escape")
                                except Exception:
                                    pass
                    
                    except Exception as e:
                        print(f"[CLEANUP ERROR] Failed to process post: {e}")
                        continue
                
                # Scroll for more posts
                try:
                    page.evaluate("window.scrollBy(0, 1000)")
                    time.sleep(2)
                except Exception:
                    break
            
            self.log["last_cleanup"] = datetime.now().isoformat()
            self.save_log()
            print(f"[CLEANUP] Deleted {deleted_count} shitty posts")
            return deleted_count
        
        except Exception as e:
            print(f"[CLEANUP ERROR] {e}")
            import traceback
            traceback.print_exc()
            return 0

CLEANUP = PostCleanup()

