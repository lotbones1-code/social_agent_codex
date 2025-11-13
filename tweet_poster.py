"""
Tweet Poster - Automatically post original tweets with AI-generated images

This module handles posting original content to Twitter/X with:
- AI-generated tweet text about your topics
- AI-generated images using DALL-E
- Smart scheduling to avoid spam
"""

import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)


class TweetPoster:
    """Handles posting original tweets with AI content and images"""

    def __init__(self, enable_posting: bool = True):
        """
        Initialize the tweet poster

        Args:
            enable_posting: Whether to enable automated tweet posting
        """
        self.enabled = False
        self.client = None

        if not enable_posting:
            logger.info("[POSTER] Tweet posting disabled")
            return

        if not OPENAI_AVAILABLE:
            logger.warning("[POSTER] OpenAI not installed, tweet posting disabled")
            return

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            logger.warning("[POSTER] No OPENAI_API_KEY, tweet posting disabled")
            return

        try:
            self.client = OpenAI(api_key=api_key)
            self.enabled = True
            logger.info("[POSTER] ✅ Tweet posting enabled with AI content & images")
        except Exception as e:
            logger.warning("[POSTER] Failed to initialize OpenAI: %s", e)

    def generate_tweet_text(self, topic: str, referral_link: Optional[str] = None) -> Optional[str]:
        """
        Generate engaging tweet text about a topic

        Args:
            topic: Topic to tweet about
            referral_link: Optional link to include

        Returns:
            Generated tweet text or None on failure
        """
        if not self.enabled or not self.client:
            return None

        try:
            system_prompt = """You are a Twitter/X content creator posting about tech, automation, and growth.

Your style:
- Engaging and valuable, not promotional
- Share insights, tips, or interesting observations
- Conversational and authentic
- Use line breaks for readability
- No hashtags (they look spammy)
- 200-250 characters max

Goal: Provide value and spark engagement."""

            user_prompt = f"Write an engaging tweet about: {topic}"

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=120,
                temperature=0.9,
                timeout=10,
            )

            tweet = response.choices[0].message.content.strip()

            # Remove quotes if added
            if tweet.startswith('"') and tweet.endswith('"'):
                tweet = tweet[1:-1]

            # Add link if provided (20% of the time to not be too promotional)
            if referral_link and random.random() < 0.2:
                tweet = f"{tweet}\n\n{referral_link}"

            # Ensure within Twitter's limit
            if len(tweet) > 280:
                tweet = tweet[:277] + "..."

            logger.debug("[POSTER] Generated tweet: %s", tweet[:50] + "...")
            return tweet

        except Exception as e:
            logger.warning("[POSTER] Failed to generate tweet text: %s", e)
            return None

    def generate_image(self, topic: str, output_path: str) -> bool:
        """
        Generate an AI image for the tweet

        Args:
            topic: Topic for image generation
            output_path: Where to save the image

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.client:
            return False

        try:
            import requests

            # Create image prompt
            image_prompts = [
                f"Modern minimalist illustration of {topic}, clean design, professional",
                f"Abstract representation of {topic}, colorful, tech-inspired",
                f"Isometric illustration showing {topic}, bright colors, simple",
                f"Flat design illustration of {topic}, vibrant, modern style",
            ]

            prompt = random.choice(image_prompts)

            logger.info("[POSTER] Generating image: %s", prompt[:50] + "...")

            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            image_url = response.data[0].url

            # Download image
            r = requests.get(image_url, timeout=60)
            r.raise_for_status()

            # Save image
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(r.content)

            logger.info("[POSTER] ✅ Image saved to %s", output_path)
            return True

        except Exception as e:
            logger.warning("[POSTER] Failed to generate image: %s", e)
            return False

    def post_tweet(self, page, tweet_text: str, image_path: Optional[str] = None) -> bool:
        """
        Post a tweet to Twitter/X

        Args:
            page: Playwright page object
            tweet_text: Text to post
            image_path: Optional path to image to attach

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("[POSTER] Posting tweet...")

            # Navigate to home if not already there
            if "home" not in page.url:
                page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

            # Find the compose box
            compose_box = page.locator("[data-testid='tweetTextarea_0']").first
            compose_box.wait_for(state="visible", timeout=10000)
            compose_box.click()
            time.sleep(500)

            # Type the tweet
            compose_box.fill(tweet_text)
            time.sleep(1000)

            # Upload image if provided
            if image_path and Path(image_path).exists():
                logger.info("[POSTER] Uploading image...")
                file_input = page.locator("input[type='file']").first
                file_input.set_input_files(image_path)
                time.sleep(3000)  # Wait for image upload

            # Click post button
            post_button = page.locator("[data-testid='tweetButtonInline']").first
            post_button.wait_for(state="visible", timeout=10000)
            post_button.click()

            time.sleep(3000)
            logger.info("[POSTER] ✅ Tweet posted successfully!")
            return True

        except Exception as e:
            logger.error("[POSTER] Failed to post tweet: %s", e)
            return False


def create_tweet_poster() -> TweetPoster:
    """
    Factory function to create a TweetPoster instance

    Returns:
        TweetPoster instance
    """
    enable = os.getenv("ENABLE_TWEET_POSTING", "false").strip().lower() in {"1", "true", "yes", "y", "on"}
    return TweetPoster(enable_posting=enable)
