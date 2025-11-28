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
            style: Caption style (hype_short, storytelling, educational, meme, curiosity)

        Returns:
            Generated caption string
        """
        prompts = {
            "hype_short": (
                "You are a viral X (Twitter) influencer who masters engagement psychology. "
                "Write an ultra-catchy, scroll-stopping caption (max 180 characters) for this video. "
                "Use powerful words, strategic emojis, and create FOMO. "
                "Make people NEED to watch this. No hashtags, pure viral energy.\n\n"
                f"Topic: {topic}\n"
                f"Original: {video_text[:300]}\n\n"
                "Rules:\n"
                "- Start with a hook (\"Wait for it...\", \"No way...\", \"This is insane\")\n"
                "- Use 2-3 relevant emojis maximum\n"
                "- Create curiosity gap\n"
                "- Sound casual but exciting\n\n"
                "Caption:"
            ),
            "storytelling": (
                "You are a master storyteller on X who knows how to hook readers instantly. "
                "Write a compelling 2-3 sentence caption that creates intrigue and emotion. "
                "Use narrative techniques: setup, tension, payoff tease. "
                "Strategic emojis only. No hashtags.\n\n"
                f"Topic: {topic}\n"
                f"Original: {video_text[:300]}\n\n"
                "Make readers feel something. Create anticipation.\n\n"
                "Caption:"
            ),
            "educational": (
                "You are an educational content creator who makes learning addictive. "
                "Write an informative caption that adds surprising context, a fun fact, or expert insight. "
                "Make people smarter in 2 sentences. Use 1-2 brain/lightbulb emojis. No hashtags.\n\n"
                f"Topic: {topic}\n"
                f"Original: {video_text[:300]}\n\n"
                "Caption:"
            ),
            "meme": (
                "You are a meme lord who speaks fluent internet culture. "
                "Write a hilarious, relatable caption that makes this video even funnier. "
                "Use meme language, reaction phrases, and perfect comedic timing. "
                "2-3 emojis max. No hashtags.\n\n"
                f"Topic: {topic}\n"
                f"Original: {video_text[:300]}\n\n"
                "Make them laugh out loud.\n\n"
                "Caption:"
            ),
            "curiosity": (
                "You are a curiosity engineer who makes people unable to scroll past. "
                "Write a caption that creates an irresistible curiosity gap. "
                "Tease the outcome without revealing it. Use pattern interrupts. "
                "Examples: 'The ending...', 'Watch what happens next', 'Nobody expected this'\n"
                "1-2 emojis. No hashtags.\n\n"
                f"Topic: {topic}\n"
                f"Original: {video_text[:300]}\n\n"
                "Caption:"
            ),
        }

        prompt = prompts.get(style, prompts["hype_short"])

        try:
            self.logger.info(f"Generating {style} caption for topic: {topic}")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert viral content creator who understands X/Twitter's algorithm. "
                            "You know exactly how to write captions that maximize engagement: "
                            "hooks, curiosity gaps, emotional triggers, and scroll-stopping power. "
                            "Every word counts. Make them want to watch, like, and share."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            caption = response.choices[0].message.content.strip()

            # Remove "Caption:" prefix if GPT added it
            if caption.lower().startswith("caption:"):
                caption = caption[8:].strip()

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
