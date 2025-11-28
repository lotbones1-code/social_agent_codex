"""AI-powered caption generator using OpenAI."""
from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI


class AICaptioner:
    """Generate viral captions for videos using OpenAI."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 100,
        temperature: float = 0.9,
        logger: Optional[logging.Logger] = None,
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.logger = logger or logging.getLogger(__name__)

    def generate_caption(
        self,
        video_text: str,
        author: str,
        topic: str,
        style: str = "hype_short",
    ) -> str:
        """
        Generate a viral caption for a video.

        Args:
            video_text: The original text from the video tweet
            author: The author's handle
            topic: The topic/category (sports, fails, funny, etc.)
            style: Caption style (hype_short, storytelling, educational)

        Returns:
            Generated caption string
        """
        prompts = {
            "hype_short": (
                "You are a viral X (Twitter) influencer who knows how to make content go viral. "
                "Write a short, catchy caption (max 200 characters) for this video. "
                "Make it exciting, use emojis, and make people want to watch. "
                "Do NOT use hashtags. Keep it natural and hype.\n\n"
                f"Topic: {topic}\n"
                f"Original text: {video_text}\n\n"
                "Caption:"
            ),
            "storytelling": (
                "You are a master storyteller on X (Twitter). "
                "Write a compelling 1-2 sentence caption that tells a mini-story or sets up intrigue. "
                "Use emojis where appropriate. No hashtags.\n\n"
                f"Topic: {topic}\n"
                f"Original text: {video_text}\n\n"
                "Caption:"
            ),
            "educational": (
                "You are an educational content creator on X (Twitter). "
                "Write an informative but engaging caption that adds context or a fun fact. "
                "Keep it concise and use 1-2 emojis. No hashtags.\n\n"
                f"Topic: {topic}\n"
                f"Original text: {video_text}\n\n"
                "Caption:"
            ),
        }

        prompt = prompts.get(style, prompts["hype_short"])

        try:
            self.logger.info(f"Generating {style} caption for topic: {topic}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a viral content creator."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            caption = response.choices[0].message.content.strip()

            # Add credit line
            credit = f"\n\n📹 via {author}"
            full_caption = caption + credit

            self.logger.info(f"Generated caption: {full_caption[:100]}...")
            return full_caption

        except Exception as exc:
            self.logger.warning(f"Failed to generate AI caption: {exc}")
            # Fallback caption
            fallback = f"{video_text[:200]}\n\n📹 via {author}"
            self.logger.info("Using fallback caption")
            return fallback


__all__ = ["AICaptioner"]
