"""OpenAI-powered caption generator for influencer mode."""

from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI

from bot.influencer_scraper import VideoCandidate


class CaptionGenerator:
    """Generates viral captions and hashtags using OpenAI."""

    def __init__(self, api_key: str, model: str, logger: logging.Logger):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.logger = logger

    def generate_caption(self, candidate: VideoCandidate, topic: Optional[str] = None) -> str:
        """
        Generate a viral caption with hashtags for a video.

        Args:
            candidate: VideoCandidate with tweet info
            topic: Optional topic context

        Returns:
            Caption text with hashtags
        """
        self.logger.info("Generating caption for video from @%s", candidate.author_handle)

        # Build context for the prompt
        context_parts = []

        if candidate.tweet_text:
            context_parts.append(f"Original tweet: {candidate.tweet_text[:200]}")

        if candidate.author_handle:
            context_parts.append(f"Author: @{candidate.author_handle}")

        if topic:
            context_parts.append(f"Topic: {topic}")

        context = "\n".join(context_parts) if context_parts else "No context available"

        # Create prompt for OpenAI
        prompt = f"""You are a viral X (Twitter) content creator. Create a short, punchy caption for a video repost.

Context:
{context}

Requirements:
- Keep it under 200 characters (this is X/Twitter)
- Make it engaging and viral-worthy
- Add 4-10 relevant hashtags at the end
- Don't use quotes or special formatting
- Sound natural and authentic
- Don't mention "repost" or credit the original

Example style:
"This is absolutely mind-blowing 🔥 The future is here #AI #Tech #Innovation #Startup #Future #GameChanger"

Generate caption:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a viral content creator for X (Twitter). Create short, engaging captions with hashtags.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.8,
            )

            caption = response.choices[0].message.content.strip()

            # Clean up caption
            caption = caption.replace('"', "").replace("'", "").strip()

            self.logger.info("Generated caption: %s", caption[:100])
            return caption

        except Exception as exc:
            self.logger.warning("OpenAI caption generation failed: %s", exc)
            # Fallback caption
            fallback = self._generate_fallback_caption(candidate, topic)
            self.logger.info("Using fallback caption: %s", fallback[:100])
            return fallback

    def _generate_fallback_caption(self, candidate: VideoCandidate, topic: Optional[str]) -> str:
        """Generate a simple fallback caption if OpenAI fails."""
        hashtags = ["#Viral", "#MustWatch", "#Trending"]

        if topic:
            # Add topic-based hashtags
            topic_tags = [f"#{word.capitalize()}" for word in topic.split()[:2]]
            hashtags.extend(topic_tags)

        caption_templates = [
            f"This is incredible 🔥 {' '.join(hashtags)}",
            f"You need to see this 👀 {' '.join(hashtags)}",
            f"Absolutely mind-blowing 🚀 {' '.join(hashtags)}",
            f"The future is here {' '.join(hashtags)}",
        ]

        import random

        return random.choice(caption_templates)

    def generate_reply(self, target_tweet_text: str, target_handle: str) -> str:
        """
        Generate a natural reply to a big account's tweet.

        Args:
            target_tweet_text: Text of the tweet to reply to
            target_handle: Handle of the account

        Returns:
            Reply text
        """
        self.logger.info("Generating reply for @%s", target_handle)

        prompt = f"""You are replying to a tweet from @{target_handle}.

Their tweet:
"{target_tweet_text[:280]}"

Requirements:
- Keep it under 150 characters
- Sound natural and human
- Be engaging but not spammy
- NO hashtags
- NO links
- NO promotional content
- Just a genuine, interesting response

Generate reply:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly, intelligent X (Twitter) user having genuine conversations.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=80,
                temperature=0.9,
            )

            reply = response.choices[0].message.content.strip()
            reply = reply.replace('"', "").replace("'", "").strip()

            # Ensure no hashtags snuck in
            if "#" in reply:
                reply = reply.split("#")[0].strip()

            self.logger.info("Generated reply: %s", reply)
            return reply

        except Exception as exc:
            self.logger.warning("OpenAI reply generation failed: %s", exc)
            return "Interesting perspective! 🤔"
