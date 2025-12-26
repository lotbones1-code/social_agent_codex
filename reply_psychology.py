"""
Reply Psychology Module - Psychology-driven reply archetypes for better conversion

Three archetypes optimized for different engagement and conversion outcomes.
"""

import random

class ReplyPsychology:
    """
    Manages three reply archetypes:
    - Curious Skeptic (30%): High curiosity, builds conversation
    - Pattern Finder (40%): Smart insights, builds credibility  
    - Helper/Authority (30%): Trust-building, high conversion
    """
    
    def __init__(self):
        self.archetype_weights = {
            "curious_skeptic": 0.30,
            "pattern_finder": 0.40,
            "helper_authority": 0.30
        }
        self.archetype_link_strategies = {
            "curious_skeptic": "build_thread",  # No link in first reply, build thread, link in reply 2-3
            "pattern_finder": "natural",  # Link as tracking/research tool
            "helper_authority": "resource"  # Link as resource/proof
        }
        self.thread_credibility = {}  # Track thread participation for archetype A
    
    def select_archetype(self):
        """Select an archetype based on weights"""
        rand = random.random()
        cumulative = 0
        
        for archetype, weight in self.archetype_weights.items():
            cumulative += weight
            if rand <= cumulative:
                return archetype
        
        # Fallback to pattern_finder
        return "pattern_finder"
    
    def get_archetype_prompt(self, archetype, tweet_text="", context=""):
        """Get the system prompt addition for the selected archetype"""
        
        prompts = {
            "curious_skeptic": """
**ARCHETYPE: The Curious Skeptic**
Your role: Challenge assumptions, ask probing questions, build engaging conversation.

Reply style:
- Open with a contrarian take or thoughtful question
- Example openings: "Wait, what if...", "But what about...", "Here's a counterpoint...", "What if the market is underpricing this?"
- Express genuine curiosity: "Am I missing something?", "What's your take?", "Why do you think that?"
- Build the conversation, don't close it
- Do NOT include a link in your first reply (build thread first)
- Goal: Get them to reply back (engagement = visibility)

Example good replies:
- "Wait, what if the market is underpricing this? The polls show X but odds say Y. What's your take?"
- "But what about [specific scenario]? That would change everything. Am I missing something?"
- "Here's a counterpoint: [insight]. Why do you think traders are ignoring this?"
""",
            
            "pattern_finder": """
**ARCHETYPE: The Pattern Finder**
Your role: Spot trends, connections, and insights others miss. Be the smart observer.

Reply style:
- Point out patterns or connections: "Notice how...", "This reminds me of...", "Pattern I'm seeing..."
- Use specific examples: "X always happens before Y odds move", "When polls show Z, markets react by..."
- Connect to trading concepts: odds movement, volatility patterns, market reactions
- Include link naturally as a tracking/research tool
- Goal: Sound smart and credible (builds trust, people click for more insights)

Example good replies:
- "Notice how odds always spike 48h before polls drop? This feels like that pattern. Track it: [link]"
- "Pattern I'm seeing: when [X] happens, [Y] market moves within 24h. Here's where to watch: [link]"
- "This reminds me of [historical event]. Same dynamics, same outcome? Track: [link]"
""",
            
            "helper_authority": """
**ARCHETYPE: The Helper/Authority**
Your role: Share insider knowledge, pro tips, helpful resources. Be the expert guide.

Reply style:
- Share specific knowledge: "Traders in [market] are watching [metric]", "The smart money is betting on..."
- Provide actionable insight: "Here's where to track it", "You can monitor this via..."
- Include link as a resource/proof: "Track live: [link]", "Here's the data: [link]"
- Sound confident but helpful, not salesy
- Goal: Build trust through value (high conversion, people click because you helped)

Example good replies:
- "Traders in this market are watching [specific metric]. Here's where to track it live: [link]"
- "The smart money is betting on [outcome]. You can see the odds move in real-time: [link]"
- "Here's what I'm seeing: [insight]. Track this yourself: [link]"
"""
        }
        
        return prompts.get(archetype, prompts["pattern_finder"])
    
    def should_include_link(self, archetype, thread_id=None, reply_number=1):
        """Determine if link should be included based on archetype strategy"""
        
        strategy = self.archetype_link_strategies.get(archetype, "natural")
        
        if strategy == "build_thread":
            # For curious skeptic: No link in first reply, build thread, link in reply 2-3
            if thread_id:
                thread_count = self.thread_credibility.get(thread_id, 0)
                if thread_count == 0:
                    # First reply in thread, no link
                    self.thread_credibility[thread_id] = 1
                    return False
                elif thread_count >= 1:
                    # Second+ reply, include link
                    self.thread_credibility[thread_id] = thread_count + 1
                    return True
            # No thread_id provided, use reply_number as fallback
            return reply_number >= 2
        
        elif strategy == "natural":
            # Pattern finder: Include link naturally (50% chance to vary)
            return random.random() < 0.5
        
        elif strategy == "resource":
            # Helper/Authority: Include link as resource (always, it's the value prop)
            return True
        
        return True  # Default to including link
    
    def get_archetype_ending(self, archetype):
        """Get archetype-specific ending/question"""
        
        endings = {
            "curious_skeptic": [
                " What's your take?",
                " Am I missing something?",
                " What do you think?",
                " Why do you think that?",
                " Thoughts?",
                " Agree or disagree?"
            ],
            "pattern_finder": [
                " Track it:",
                " Watch this:",
                " Here's where to monitor:",
                " See for yourself:",
                " Worth watching:"
            ],
            "helper_authority": [
                " Track live:",
                " Here's the data:",
                " Monitor this:",
                " Check it out:",
                " See real-time:"
            ]
        }
        
        archetype_endings = endings.get(archetype, [" Thoughts?"])
        return random.choice(archetype_endings)

# Global instance
REPLY_PSYCHOLOGY = ReplyPsychology()

