"""
Reply Optimizer - ChatGPT prompt optimization for human-like variety

Adds style rotation, shorter replies, question endings, and better variation.
"""

import random

class ReplyOptimizer:
    """
    Manages ChatGPT reply optimization:
    - Style rotation (3 personas: analytical, casual, urgent)
    - Shorter replies (30% reduction)
    - Question endings (30% of replies)
    - Temperature optimization (0.8 for variety)
    """
    
    def __init__(self):
        self.styles = ["analytical", "casual", "urgent"]
        self.current_style_index = 0
        self.question_endings = [
            " What do you think?",
            " Thoughts?",
            " Agree?",
            " How are you sizing this?",
            " Where do you see this going?",
            " Overpriced or fair?",
            " This a buy or fade?",
            " What's your take?"
        ]
    
    def get_next_style(self):
        """Rotate through reply styles"""
        style = self.styles[self.current_style_index]
        self.current_style_index = (self.current_style_index + 1) % len(self.styles)
        return style
    
    def get_style_prompt_addition(self, style):
        """Get prompt addition based on style"""
        additions = {
            "analytical": """
**Style: Analytical**
- Use data-driven language (percentages, odds, probabilities)
- Compare multiple scenarios or markets
- Use phrases like "the data suggests", "markets imply", "probability-wise"
- Stay objective and measured
""",
            "casual": """
**Style: Casual**
- Write like you're texting a friend
- Use shorter sentences, contractions
- More conversational tone ("yeah", "nah", "tbh")
- Less formal, more relatable
""",
            "urgent": """
**Style: Urgent**
- Create FOMO or time-sensitive feel
- Use action words ("breaking", "just", "now", "watch")
- Highlight immediate opportunity or risk
- More energetic, less measured
"""
        }
        return additions.get(style, "")
    
    def should_add_question(self, probability=0.3):
        """Decide if reply should end with question (30% probability)"""
        return random.random() < probability
    
    def add_question_ending(self, reply_text):
        """Add a question ending to reply if it doesn't already have one"""
        if reply_text.endswith("?") or reply_text.endswith("!"):
            return reply_text
        
        question = random.choice(self.question_endings)
        # Make sure total length stays under limit
        max_length = 240
        if len(reply_text + question) <= max_length:
            return reply_text + question
        else:
            # Trim reply to fit question
            trimmed = reply_text[:max_length - len(question) - 3].rstrip() + "..."
            return trimmed + question
    
    def optimize_reply_length(self, reply_text, target_reduction=0.3):
        """Make reply ~30% shorter (humans are terse, bots are long)"""
        original_length = len(reply_text)
        target_length = int(original_length * (1 - target_reduction))
        
        if original_length <= target_length:
            return reply_text  # Already short enough
        
        # Simple approach: trim to target length at word boundaries
        words = reply_text.split()
        trimmed_words = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 <= target_length:
                trimmed_words.append(word)
                current_length += len(word) + 1
            else:
                break
        
        if trimmed_words:
            result = " ".join(trimmed_words)
            # Add ellipsis if we cut it short
            if len(result) < original_length * 0.8:
                result = result.rstrip(".,!?") + "..."
            return result
        
        return reply_text[:target_length] + "..."
    
    def get_temperature(self):
        """Get optimized temperature for variety (0.8 recommended)"""
        return 0.8
    
    def get_sentence_openings(self, style):
        """Get varied sentence openings for style"""
        openings = {
            "analytical": [
                "The data shows",
                "Markets imply",
                "Looking at the odds",
                "Probability-wise",
                "The numbers suggest",
                "Statistically",
                "Based on current pricing",
                "The implied probability is"
            ],
            "casual": [
                "Yeah",
                "Nah",
                "Tbh",
                "Here's the thing",
                "Real talk",
                "Look",
                "So",
                "Tbh this is",
                "Honestly",
                "I mean"
            ],
            "urgent": [
                "Breaking",
                "Just saw",
                "Watch this",
                "This just",
                "Now this",
                "Here's what's happening",
                "This is wild",
                "Now we're talking",
                "This could"
            ]
        }
        return openings.get(style, ["Here's the thing"])

# Global instance
REPLY_OPTIMIZER = ReplyOptimizer()

