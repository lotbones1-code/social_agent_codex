import json
import os
from difflib import SequenceMatcher

class ReplyDeduplicator:
    def __init__(self, history_file="reply_history.json"):
        self.history_file = history_file
        self.history = self.load_history()
    
    def load_history(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return {"replies": [], "target_ids": []}
        return {"replies": [], "target_ids": []}
    
    def save_history(self):
        """Save history, keeping only last 500 replies"""
        # Keep last 500 replies only
        self.history["replies"] = self.history["replies"][-500:]
        self.history["target_ids"] = self.history["target_ids"][-500:]
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history, f)
        except Exception as e:
            print(f"[DEDUPE] Error saving history: {e}")
    
    def similarity(self, text1, text2):
        """Calculate similarity between two texts"""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def is_duplicate_or_similar(self, new_text, threshold=0.75):
        """Check if reply text is duplicate or >75% similar to recent replies"""
        for old_text in self.history["replies"]:
            if self.similarity(new_text, old_text) > threshold:
                return True
        return False
    
    def already_replied_to(self, target_id):
        """Check if we already replied to this tweet"""
        return target_id in self.history["target_ids"]
    
    def add_reply(self, text, target_id):
        """Record successful reply"""
        self.history["replies"].append(text)
        if target_id:
            self.history["target_ids"].append(target_id)
        self.save_history()
    
    def can_post_reply(self, text, target_id):
        """Master check: both duplicate text and target ID"""
        if target_id and self.already_replied_to(target_id):
            print(f"[DEDUPE] Already replied to {target_id}, skipping")
            return False
        if self.is_duplicate_or_similar(text):
            print(f"[DEDUPE] Reply text too similar to recent replies, regenerating")
            return False
        return True

DEDUPLICATOR = ReplyDeduplicator()

