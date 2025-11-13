#!/usr/bin/env python3
"""
AI Reply Generator - GPT-4o-mini Integration
Generates intelligent, context-aware replies using OpenAI's API
Falls back to templates if GPT fails or isn't configured

Cost: ~$0.003 per reply (~$1-5/month for typical usage)
"""

from __future__ import annotations

import logging
import os
import random
from typing import Optional

logger = logging.getLogger(__name__)


class AIReplyGenerator:
    """
    Generates AI-powered replies with automatic fallback to templates.

    Features:
    - GPT-4o-mini integration for natural, context-aware replies
    - Automatic fallback to templates if API fails
    - Cost-effective (~$0.003 per reply)
    - Respects your referral link and topic focus
    """

    def __init__(self, enable_ai: bool = True):
        """
        Initialize AI reply generator.

        Args:
            enable_ai: Whether to try using AI (requires OPENAI_API_KEY in env)
        """
        self.enabled = False
        self.client = None

        if not enable_ai:
            logger.info("[AI] AI reply generation disabled by config")
            return

        api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not api_key:
            logger.info("[AI] No OPENAI_API_KEY found - using template-based replies (free)")
            return

        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
            self.enabled = True
            logger.info("[AI] ✅ GPT-4o-mini enabled for reply generation (costs ~$1-5/month)")
        except ImportError:
            logger.warning("[AI] OpenAI package not installed. Run: pip install openai")
            logger.info("[AI] Using template-based replies (free)")
        except Exception as exc:
            logger.warning("[AI] Failed to initialize OpenAI: %s", exc)
            logger.info("[AI] Using template-based replies (free)")

    def generate_reply(
        self,
        tweet_text: str,
        topic: str,
        referral_link: Optional[str] = None,
        max_length: int = 270,
    ) -> Optional[str]:
        """
        Generate an AI-powered reply to a tweet.

        Args:
            tweet_text: The tweet to reply to
            topic: The topic being discussed (e.g., "AI automation")
            referral_link: Optional link to include
            max_length: Maximum reply length in characters

        Returns:
            Generated reply text, or None if AI generation failed
        """
        if not self.enabled or not self.client:
            return None

        try:
            # Calculate space needed for link FIRST (to avoid truncating it later)
            link_space = 0
            link_suffix = ""
            # Only include link 70% of the time (more natural/not spammy)
            if referral_link and random.random() < 0.7:
                # Reserve space for link + CTA (worst case scenario)
                ctas = [
                    f" Here's what helped me: {referral_link}",
                    f" I wrote about this here: {referral_link}",
                    f" More on this: {referral_link}",
                    f" Check this out: {referral_link}",
                    f" Found this helpful: {referral_link}",
                    f" This might help: {referral_link}",
                ]
                max_cta_length = max(len(cta) for cta in ctas)
                link_space = max_cta_length + 5  # Extra buffer

                # Decide now which suffix to use (40% with CTA, 60% without)
                if random.random() < 0.4:
                    link_suffix = random.choice(ctas)
                else:
                    link_suffix = f" {referral_link}"

            # Generate reply with space reserved for link
            available_chars = max_length - link_space
            system_prompt = f"""You're a real person replying to tweets about {topic}.

Be GENUINELY helpful:
- If they're asking for recommendations, actually help them
- If they need a solution, share what worked for you
- Sound like a friend, not a marketer
- Be specific and authentic
- Keep under {available_chars} characters
- NO hashtags or emojis
- NO corporate/salesy language

Be conversational and real. If they're looking for something, genuinely try to help."""

            user_prompt = f'Write a natural, helpful reply to: "{tweet_text}"\n\nBe genuine and specific. If they\'re asking for help/recommendations, give them actual advice.'

            # Call GPT-4o-mini (cheapest model, very capable)
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=100,  # Enough for good replies
                temperature=0.85,  # Creative but focused
                timeout=10,
            )

            reply = response.choices[0].message.content.strip()

            # Remove quotes if GPT added them
            if reply.startswith('"') and reply.endswith('"'):
                reply = reply[1:-1]

            # Truncate reply if needed BEFORE adding link
            if len(reply) > available_chars:
                reply = reply[:available_chars].rsplit(' ', 1)[0]
                if not reply.endswith(('...', '.', '!', '?')):
                    reply += "..."

            # NOW add the link (guaranteed to fit!)
            reply = reply + link_suffix

            # Final safety check
            if len(reply) > max_length:
                logger.warning("[AI] Reply still too long after adding link, truncating")
                reply = reply[:max_length].rsplit(' ', 1)[0] + "..."

            logger.debug("[AI] Generated: %s", reply[:60] + "..." if len(reply) > 60 else reply)
            return reply

        except Exception as exc:
            logger.warning("[AI] Reply generation failed: %s", exc)
            return None


def create_ai_generator(config) -> AIReplyGenerator:
    """
    Factory function to create an AI generator from bot config.

    Args:
        config: BotConfig instance from social_agent.py

    Returns:
        AIReplyGenerator instance
    """
    # Check if AI is enabled via environment variable
    enable_ai = os.getenv("ENABLE_AI_REPLIES", "true").strip().lower() in {"1", "true", "yes", "y", "on"}
    return AIReplyGenerator(enable_ai=enable_ai)


# Backwards compatibility: allow direct import
if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ai_reply_generator.py '<tweet text>'")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    generator = AIReplyGenerator()
    tweet = sys.argv[1]
    reply = generator.generate_reply(
        tweet_text=tweet,
        topic="AI automation",
        referral_link="https://example.com/my-guide"
    )

    if reply:
        print(f"\n✅ AI Reply:\n{reply}\n")
    else:
        print("\n❌ AI generation failed (check OPENAI_API_KEY)\n")
