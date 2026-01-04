"""
Thread Optimizer - Conversation hijacking and timing optimization

Identifies high-potential threads and optimizes reply timing for maximum visibility.
"""

import re
from datetime import datetime

class ThreadOptimizer:
    """
    Optimizes thread targeting and timing:
    - Identifies high-potential threads (hot conversations)
    - Targets top replies for better visibility
    - Detects time-sensitive content for urgent replies
    """
    
    def __init__(self):
        self.time_sensitive_keywords = [
            "breaking", "just", "now", "live", "happening",
            "growth", "metrics", "results", "conversion", "tracking",
            "odds", "market", "spike", "crash", "move",
            "announcement", "news", "update", "reports"
        ]
    
    def is_high_potential_thread(self, card, page=None):
        """
        Identify high-potential threads:
        - Thread has 10+ replies (conversation is hot)
        - Top replies have 50+ likes (quality discussion)
        - Still under 100 replies (not yet saturated)
        """
        try:
            # Try to extract reply count
            reply_count = 0
            try:
                reply_elem = card.locator('[data-testid="reply"]').first
                if reply_elem.count() > 0:
                    reply_text = reply_elem.get_attribute("aria-label") or ""
                    # Parse "X replies" or "X replies" from aria-label
                    reply_match = re.search(r'(\d+)\s*replies?', reply_text, re.IGNORECASE)
                    if reply_match:
                        reply_count = int(reply_match.group(1))
            except Exception:
                pass
            
            # Check if thread is in sweet spot (10-100 replies)
            if reply_count < 10:
                return False, "too_few_replies"  # Not hot yet
            if reply_count > 100:
                return False, "too_many_replies"  # Saturated
            
            # Try to check top reply engagement (approximate via likes on original)
            # This is a proxy - we assume if original has high engagement, thread does too
            try:
                likes_elem = card.locator('[data-testid="like"]').first
                if likes_elem.count() > 0:
                    likes_text = likes_elem.get_attribute("aria-label") or ""
                    likes_match = re.search(r'(\d+\.?\d*[KkMm]?)\s*likes?', likes_text, re.IGNORECASE)
                    if likes_match:
                        likes_str = likes_match.group(1)
                        likes_count = self._parse_count(likes_str)
                        if likes_count >= 50:
                            return True, "high_potential"
            except Exception:
                pass
            
            # If we can't determine, default to allowing if reply count is good
            if 10 <= reply_count <= 100:
                return True, "potential_thread"
            
            return False, "unknown"
            
        except Exception as e:
            return False, f"error: {str(e)}"
    
    def _parse_count(self, count_str):
        """Parse count string like '1.5K' or '2M' to integer"""
        try:
            count_str = count_str.upper().replace(",", "")
            if 'K' in count_str:
                return int(float(count_str.replace('K', '')) * 1000)
            elif 'M' in count_str:
                return int(float(count_str.replace('M', '')) * 1000000)
            else:
                return int(count_str)
        except Exception:
            return 0
    
    def is_time_sensitive(self, tweet_text):
        """Detect if post is time-sensitive (needs fast reply)"""
        if not tweet_text:
            return False
        
        text_lower = tweet_text.lower()
        
        # Check for time-sensitive keywords
        keyword_matches = sum(1 for kw in self.time_sensitive_keywords if kw in text_lower)
        
        # If 2+ time-sensitive keywords, it's urgent
        if keyword_matches >= 2:
            return True, "urgent"
        
        # Check for specific patterns
        urgent_patterns = [
            r'\b(metrics|conversion|results?)\s+(just|now|live|out)',
            r'\b(odds|market)\s+(spike|crash|move|breaking)',
            r'\b(breaking|just|happening\s+now)',
            r'\b(announcement|news)\s+(just|now|breaking)'
        ]
        
        for pattern in urgent_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True, "urgent_pattern"
        
        return False, "normal"
    
    def get_reply_delay(self, is_urgent=False):
        """Get optimal reply delay based on urgency"""
        if is_urgent:
            # Urgent: Reply within 5 minutes (algorithm + human recency)
            return (5, 10)  # 5-10 minutes
        else:
            # Normal: Reply 15-30 minutes (less bot-like)
            return (15, 30)
    
    def get_urgency_language(self, is_urgent=False):
        """Get language to add urgency when appropriate"""
        if is_urgent:
            urgency_phrases = [
                "This is moving fast",
                "Real-time odds",
                "Happening now",
                "Watch this closely",
                "This just hit"
            ]
            import random
            return random.choice(urgency_phrases) + ": "
        return ""
    
    def should_target_top_replies(self, is_high_potential=False):
        """Decide if we should target top 3 replies instead of OP"""
        # Only for high-potential threads
        if is_high_potential:
            # 70% chance to target top replies (better visibility)
            import random
            return random.random() < 0.70
        return False

# Global instance
THREAD_OPTIMIZER = ThreadOptimizer()

