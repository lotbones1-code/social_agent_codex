"""
FEATURE: Political Engagement Templates + GPT Integration
WHAT: Templates and tactics for civil political debate, with optional GPT-4o-mini
WHY: Enables engaging with political content in a thoughtful, non-toxic way
HOW TO REVERT: Set USE_NEW_CONFIG=false in .env or delete this file

NO AUTH/LOGIN CHANGES - This is purely content generation
SAFETY: No hate speech, no slurs, no protected-class attacks
"""

import logging
import random
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PoliticalReplyGenerator:
    """
    Generates civil, engaging replies for political content.
    Focuses on thoughtful debate, not divisiveness.
    """

    # Analytical stance templates (fact-based)
    ANALYTICAL_TEMPLATES = [
        "Interesting point on {focus}. The data actually shows {perspective}. Worth considering {question}",
        "I see your angle on {focus}. However, recent analysis suggests {perspective}. Thoughts on {question}?",
        "Valid concern about {focus}. From what I've seen, {perspective}. How do you think {question}",
        "The {focus} discussion is important. Research indicates {perspective}. Curious about {question}",
        "{focus} is nuanced. Historical precedent shows {perspective}. What's your take on {question}?",
    ]

    # Questioning templates (Socratic method)
    QUESTIONING_TEMPLATES = [
        "Genuine question about {focus}: {question}",
        "Help me understand {focus} better. {question}",
        "Interesting take on {focus}. What happens if {question}?",
        "I'm curious about {focus}. Have you considered {question}?",
        "Good point on {focus}. Follow-up: {question}",
    ]

    # Supportive templates (building on good points)
    SUPPORTIVE_TEMPLATES = [
        "Exactly right about {focus}. This also connects to {perspective}. {question}",
        "Nailed it on {focus}. Building on that: {perspective}. Do you think {question}?",
        "Strong point on {focus}. Adding to this: {perspective}. Interested in {question}",
        "100% on {focus}. This is why {perspective}. What's your view on {question}?",
        "Spot on about {focus}. Especially when you consider {perspective}. {question}",
    ]

    # Critical (but civil) templates
    CRITICAL_CIVIL_TEMPLATES = [
        "I respectfully disagree on {focus}. {perspective}. Open to hearing your thoughts on {question}",
        "Different take on {focus}: {perspective}. How do you reconcile {question}?",
        "I see the logic on {focus}, but {perspective}. Curious how {question}",
        "Fair point on {focus}, though {perspective}. What about {question}?",
        "Understand the concern on {focus}, but evidence suggests {perspective}. Thoughts on {question}?",
    ]

    # Perspectives (to fill in templates)
    PERSPECTIVES = [
        "the unintended consequences could be significant",
        "there are strong counterarguments to consider",
        "the historical context matters here",
        "this impacts multiple stakeholders differently",
        "the tradeoffs aren't being fully discussed",
        "short-term vs long-term effects differ",
        "the implementation challenges are real",
        "public opinion is shifting on this",
    ]

    # Questions (Socratic follow-ups)
    QUESTIONS = [
        "how would this scale?",
        "who benefits most from this approach?",
        "what's the historical precedent?",
        "how do we measure success here?",
        "what are the second-order effects?",
        "where's the line being drawn?",
        "what's the accountability mechanism?",
        "how does this compare to alternatives?",
    ]

    # Call-to-action endings (promoting the bot itself - STRONG SALES COPY)
    CTA_ENDINGS = [
        "Btw I automate all my engagement with this bot - 100+ replies/day, zero bans: {link}",
        "This reply was automated. Bot handles everything (posts, replies, follows) on autopilot: {link}",
        "Built this automation bot to scale engagement 24/7 without getting banned: {link}",
        "FYI this is automated - bot grows your account while you sleep: {link}",
        "Using this bot to automate my entire feed - posts, replies, images, all automated: {link}",
        "Automated engagement bot I built - handles everything without manual work: {link}",
        "This bot does 100+ political replies/day for me automatically: {link}",
        "Running this automation - best way to grow your account on autopilot: {link}",
        "Built this to automate my engagement 24/7 - game changer: {link}",
        "This is automated btw. Bot handles all my replies and posts: {link}",
    ]

    def __init__(self, config_loader):
        """
        Initialize political reply generator.

        Args:
            config_loader: BotConfigLoader instance
        """
        self.config = config_loader

        # FEATURE ADD: Optional GPT-4o-mini integration for more unique replies
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.use_gpt = False
        self.openai_client = None

        if self.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.openai_api_key)
                self.use_gpt = True
                logger.info("[GPT] ✅ GPT-4o-mini enabled for reply generation (costs ~$1-2/month)")
            except ImportError:
                logger.warning("[GPT] OpenAI package not installed. Run: pip install openai")
                logger.info("[GPT] Falling back to template-based replies (free)")
            except Exception as e:
                logger.warning(f"[GPT] Failed to initialize OpenAI: {e}")
                logger.info("[GPT] Falling back to template-based replies (free)")
        else:
            logger.info("[GPT] No OPENAI_API_KEY found - using template-based replies (free)")

    def generate_reply(
        self,
        tweet_text: str,
        topic: str,
        tone: Optional[str] = None,
        include_link: bool = False
    ) -> str:
        """
        Generate a political reply based on tweet content.

        Args:
            tweet_text: Original tweet text
            topic: Topic being discussed
            tone: Desired tone (analytical/questioning/supportive/critical-civil)
            include_link: Whether to include promo link

        Returns:
            Generated reply text
        """
        # Select tone
        if tone is None:
            tone = random.choice(self.config.config.get('reply_tones', ['analytical']))

        # FEATURE ADD: Try GPT first, fallback to templates if it fails
        if self.use_gpt and self.openai_client:
            try:
                reply = self._generate_gpt_reply(tweet_text, topic, tone, include_link)
                if reply:
                    return reply
                # If GPT returns empty, fall through to templates
                logger.debug("[GPT] Empty response, using templates")
            except Exception as e:
                logger.warning(f"[GPT] API failed: {e}, using templates")
                # Fall through to template-based generation

        # TEMPLATE-BASED GENERATION (original code - fallback)
        # Extract focus (key phrase from tweet)
        focus = self._extract_focus(tweet_text)

        # Select templates based on tone
        if tone == "analytical":
            templates = self.ANALYTICAL_TEMPLATES
        elif tone == "questioning":
            templates = self.QUESTIONING_TEMPLATES
        elif tone == "supportive":
            templates = self.SUPPORTIVE_TEMPLATES
        elif tone == "critical-civil":
            templates = self.CRITICAL_CIVIL_TEMPLATES
        else:
            templates = self.ANALYTICAL_TEMPLATES

        # Generate base reply
        template = random.choice(templates)
        perspective = random.choice(self.PERSPECTIVES)
        question = random.choice(self.QUESTIONS)

        reply = template.format(
            focus=focus,
            perspective=perspective,
            question=question
        )

        # Maybe add hashtag (at most one)
        if random.random() < 0.3:  # 30% chance
            hashtag = random.choice(self.config.config.get('hashtags_allowlist', ['#Politics']))
            reply = f"{reply} {hashtag}"

        # Maybe add promo link (if include_link=True)
        if include_link:
            link = self.config.get_promo_link('gumroad')
            if link:
                cta = random.choice(self.CTA_ENDINGS).format(link=link)
                reply = f"{reply} {cta}"

        # Ensure length limit
        max_length = self.config.config.get('max_reply_length', 270)
        if len(reply) > max_length:
            # Truncate and remove partial word
            reply = reply[:max_length].rsplit(' ', 1)[0] + "..."

        return reply

    def _generate_gpt_reply(
        self,
        tweet_text: str,
        topic: str,
        tone: str,
        include_link: bool
    ) -> Optional[str]:
        """
        Generate reply using GPT-4o-mini.

        Args:
            tweet_text: Original tweet text
            topic: Topic being discussed
            tone: Desired tone
            include_link: Whether to include promo link

        Returns:
            Generated reply text, or None if failed
        """
        try:
            # Build system prompt based on tone
            tone_instructions = {
                "analytical": "Use data and evidence. Be thoughtful and fact-based.",
                "questioning": "Ask probing questions. Use Socratic method.",
                "supportive": "Build on good points. Be constructive.",
                "critical-civil": "Respectfully disagree. Present counterarguments politely."
            }

            tone_instruction = tone_instructions.get(tone, "Be analytical and thoughtful.")

            system_prompt = f"""You are engaging in political discussion on Twitter. Your style:
- {tone_instruction}
- Keep it concise (under 240 characters to leave room for links)
- Be civil and thoughtful, not divisive
- Focus on substance, not personal attacks
- Topic: {topic}"""

            user_prompt = f'Reply to this tweet thoughtfully: "{tweet_text}"'

            # Call GPT-4o-mini
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,
                temperature=0.8,
                timeout=10
            )

            reply = response.choices[0].message.content.strip()

            # Add promo link if requested
            if include_link:
                link = self.config.get_promo_link('gumroad')
                if link:
                    cta = random.choice(self.CTA_ENDINGS).format(link=link)
                    reply = f"{reply} {cta}"

            # Ensure length limit
            max_length = self.config.config.get('max_reply_length', 270)
            if len(reply) > max_length:
                reply = reply[:max_length].rsplit(' ', 1)[0] + "..."

            logger.debug(f"[GPT] Generated reply: {reply[:50]}...")
            return reply

        except Exception as e:
            logger.error(f"[GPT] Reply generation failed: {e}")
            return None

    def _extract_focus(self, tweet_text: str, max_chars: int = 30) -> str:
        """
        Extract key focus phrase from tweet.

        Args:
            tweet_text: Tweet text
            max_chars: Max characters for focus

        Returns:
            Focus phrase
        """
        # Clean text
        text = tweet_text.strip()

        # Remove URLs
        words = [w for w in text.split() if not w.startswith('http')]
        text = ' '.join(words)

        # Truncate if needed
        if len(text) > max_chars:
            text = text[:max_chars].rsplit(' ', 1)[0]

        return text if text else "this topic"

    def is_safe_to_reply(self, tweet_text: str) -> bool:
        """
        Check if tweet is safe to reply to (no hate speech triggers).

        Args:
            tweet_text: Tweet text to check

        Returns:
            True if safe to reply, False otherwise
        """
        # Block list (hate speech indicators, slurs, etc)
        unsafe_patterns = [
            # Add patterns to block here
            # Examples (not exhaustive):
            "kill all", "death to", "subhuman",
            # etc - expand as needed
        ]

        text_lower = tweet_text.lower()
        for pattern in unsafe_patterns:
            if pattern in text_lower:
                logger.warning(f"[politics] Blocked unsafe tweet containing: {pattern}")
                return False

        return True
