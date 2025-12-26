"""
Stage 11D: Response Optimizer

Monitors replies to your posts and automatically generates thoughtful counter-replies
to keep conversations alive. More back-and-forth = higher engagement.
"""

import json
import os
import re
from datetime import datetime, timedelta
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

class ResponseOptimizer:
    """
    Generates smart replies to comments on your posts to boost engagement.
    """
    
    def __init__(self, analytics_log="performance_log.json", min_comment_length=10, max_replies_per_hour=3):
        self.analytics_log = analytics_log
        self.min_comment_length = min_comment_length
        self.max_replies_per_hour = max_replies_per_hour
        
        # Spam keywords to filter out
        self.spam_keywords = [
            "follow", "dm for", "link in bio", "scam", "click here",
            "make money", "earn cash", "free crypto", "sign up",
            "promo code", "discount", "limited time"
        ]
    
    def is_spam_comment(self, comment_text):
        """
        Return True if comment is spam.
        Checks for spam keywords, too short, excessive emojis, or multiple URLs.
        """
        if not comment_text:
            return True
        
        comment_lower = comment_text.lower()
        
        # Check for spam keywords
        for keyword in self.spam_keywords:
            if keyword in comment_lower:
                return True
        
        # Check length
        if len(comment_text) < self.min_comment_length:
            return True
        
        # Check for excessive emojis (>5)
        emoji_count = len(re.findall(r'[😀-🙏🌀-🗿]', comment_text))
        if emoji_count > 5:
            return True
        
        # Check for multiple URLs
        url_count = len(re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', comment_text))
        if url_count > 1:
            return True
        
        return False
    
    def should_reply_to_comment(self):
        """
        Check rate limit (max 3 replies per hour).
        Returns True if we can reply, False if rate limit hit.
        """
        if not os.path.exists(self.analytics_log):
            return True  # No log, assume we can reply
        
        try:
            with open(self.analytics_log, 'r') as f:
                data = json.load(f)
        except Exception:
            return True  # Error reading, allow reply
        
        # Get all stage11d entries from last hour
        posts = data.get("posts", [])
        one_hour_ago = datetime.now() - timedelta(hours=1)
        
        replies_last_hour = 0
        for post in posts:
            if post.get("type") == "stage11d_reply":
                post_timestamp = post.get("timestamp", "")
                if post_timestamp:
                    try:
                        post_time = datetime.fromisoformat(post_timestamp)
                        if post_time >= one_hour_ago:
                            replies_last_hour += 1
                    except Exception:
                        continue
        
        can_reply = replies_last_hour < self.max_replies_per_hour
        print(f"[STAGE 11D] Rate limit check: {replies_last_hour}/{self.max_replies_per_hour} replies used this hour")
        
        return can_reply
    
    def generate_smart_reply(self, original_post, user_comment):
        """
        Generate a smart reply using GPT-4.
        Returns dict with: reply, tone, asks_question
        """
        if not client:
            print("[STAGE 11D] OpenAI client not available")
            return None
        
        prompt = f"""You are a Polymarket trader replying to a comment on your post.

YOUR ORIGINAL POST:
{original_post[:300]}

USER'S COMMENT:
{user_comment[:300]}

Generate a thoughtful reply (150-200 chars) that:
1. Acknowledges the commenter's point
2. Adds new information or insight
3. Ends with a follow-up question when appropriate

Tone options: engaging, educational, or humorous (choose what fits best).

Output ONLY this JSON (no markdown):
{{"reply": "YOUR REPLY TEXT", "tone": "engaging|educational|humorous", "asks_question": true}}"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Output ONLY valid JSON. No markdown. No explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=200
            )
            
            response_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            data = json.loads(response_text)
            
            # Validate required fields
            if "reply" not in data or "tone" not in data:
                return None
            
            # Ensure asks_question is boolean
            if "asks_question" not in data:
                data["asks_question"] = "?" in data.get("reply", "")
            
            return data
        
        except Exception as e:
            print(f"[STAGE 11D] Error generating reply: {str(e)[:100]}")
            return None
    
    def log_reply(self, original_post_id, user_handle, reply_text, reply_quality):
        """
        Write reply event to performance_log.json.
        
        Args:
            original_post_id: ID of the original post
            user_handle: Handle of the user who commented
            reply_text: The generated reply text
            reply_quality: Quality metric (dict with tone, asks_question, etc.)
        """
        try:
            if os.path.exists(self.analytics_log):
                with open(self.analytics_log, 'r') as f:
                    data = json.load(f)
            else:
                data = {"posts": []}
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "stage11d_reply",
                "original_post_id": original_post_id,
                "user_handle": user_handle,
                "reply_text": reply_text,
                "tone": reply_quality.get("tone", "engaging"),
                "asks_question": reply_quality.get("asks_question", False)
            }
            
            if "posts" not in data:
                data["posts"] = []
            data["posts"].append(entry)
            
            with open(self.analytics_log, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[STAGE 11D] ✓ Logged reply to @{user_handle}")
        except Exception as e:
            print(f"[STAGE 11D] Log error: {str(e)[:80]}")

# Global instance
optimizer = ResponseOptimizer()

