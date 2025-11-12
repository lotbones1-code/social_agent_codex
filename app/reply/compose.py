"""
FEATURE: Human-like Reply Composer
WHAT: Orchestrates reply generation with media, links, and civil debate
WHY: Creates engaging, authentic political/topical replies
HOW TO REVERT: Set USE_NEW_CONFIG=false in .env or delete this file

NO AUTH/LOGIN CHANGES - This is purely content generation
"""

import logging
import random
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ReplyComposer:
    """
    Composes human-like replies for political/topical content.
    Orchestrates: tone adaptation, media generation, link inclusion.
    """

    def __init__(self, config_loader, image_adapter, video_adapter, politics_generator):
        """
        Initialize reply composer.

        Args:
            config_loader: BotConfigLoader instance
            image_adapter: ImageAdapter instance
            video_adapter: VideoAdapter instance
            politics_generator: PoliticalReplyGenerator instance
        """
        self.config = config_loader
        self.image_adapter = image_adapter
        self.video_adapter = video_adapter
        self.politics_generator = politics_generator

    def compose_reply(
        self,
        tweet_text: str,
        tweet_author: str,
        topic: str,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Compose a complete reply with text, optional media, and link.

        Args:
            tweet_text: Original tweet text
            tweet_author: Tweet author handle
            topic: Topic being discussed
            dry_run: If True, don't actually generate media (faster)

        Returns:
            Dict with 'text', 'media_path' (optional), 'should_post' (bool)
        """
        result = {
            'text': '',
            'media_path': None,
            'should_post': False
        }

        try:
            # Safety check: don't reply to unsafe content
            if not self.politics_generator.is_safe_to_reply(tweet_text):
                logger.warning(f"[composer] Blocked unsafe tweet from @{tweet_author}")
                return result

            # Check if tweet contains excluded domains (gambling, etc)
            if self._contains_excluded_domain(tweet_text):
                logger.debug(f"[composer] Skipping tweet with excluded domain")
                return result

            # Determine if we should include promo link
            include_link = self.config.should_include_promo()

            # Select tone based on tweet content
            tone = self._select_tone(tweet_text)

            # Generate reply text
            reply_text = self.politics_generator.generate_reply(
                tweet_text=tweet_text,
                topic=topic,
                tone=tone,
                include_link=include_link
            )

            # Maybe generate media (only if beneficial and not dry_run)
            media_path = None
            if not dry_run and self.config.should_include_media():
                if self._would_benefit_from_media(tweet_text, topic):
                    media_path = self._generate_media(topic, reply_text)

            result['text'] = reply_text
            result['media_path'] = media_path
            result['should_post'] = True

            logger.info(f"[composer] Composed reply ({len(reply_text)} chars, media={bool(media_path)})")
            return result

        except Exception as exc:
            logger.error(f"[composer] Failed to compose reply: {exc}")
            return result

    def _select_tone(self, tweet_text: str) -> str:
        """
        Select appropriate tone based on tweet content.

        Args:
            tweet_text: Tweet text

        Returns:
            Tone string (analytical/questioning/supportive/critical-civil)
        """
        text_lower = tweet_text.lower()

        # Detect question marks -> use questioning tone
        if '?' in tweet_text:
            return 'questioning'

        # Detect positive sentiment -> use supportive tone
        positive_keywords = ['great', 'excellent', 'agree', 'exactly', 'correct', 'right', 'smart']
        if any(word in text_lower for word in positive_keywords):
            return 'supportive'

        # Detect debate/controversy -> use critical-civil tone
        debate_keywords = ['disagree', 'wrong', 'false', 'misleading', 'actually']
        if any(word in text_lower for word in debate_keywords):
            return 'critical-civil'

        # Default to analytical
        return 'analytical'

    def _would_benefit_from_media(self, tweet_text: str, topic: str) -> bool:
        """
        Determine if reply would benefit from media (image/video).

        Args:
            tweet_text: Tweet text
            topic: Topic

        Returns:
            True if media would enhance reply
        """
        # Heuristics: media works well for:
        # - Data/statistics discussions
        # - Policy announcements
        # - Breaking news
        # - Visual topics

        text_lower = tweet_text.lower()

        media_keywords = [
            'data', 'chart', 'graph', 'statistic', 'number', 'percent',
            'breaking', 'announcement', 'report', 'study', 'analysis',
            'visual', 'video', 'photo', 'image', 'show'
        ]

        return any(keyword in text_lower for keyword in media_keywords)

    def _generate_media(self, topic: str, context: str) -> Optional[str]:
        """
        Generate media (image or video) for reply.

        Args:
            topic: Topic
            context: Reply text context

        Returns:
            Path to media file, or None if generation failed
        """
        # Try image first (faster, more reliable)
        media_path = self.image_adapter.generate_political_image(topic, context)

        # Could try video as fallback/alternative in future
        # if not media_path:
        #     media_path = self.video_adapter.generate_political_video(topic, context)

        return media_path

    def _contains_excluded_domain(self, text: str) -> bool:
        """
        Check if text contains any excluded domains.

        Args:
            text: Text to check

        Returns:
            True if excluded domain found
        """
        return self.config.is_excluded_domain(text)


# Dry-run mode for testing
def dry_run_demo():
    """
    Demo the reply composer without posting.
    """
    print("=== Reply Composer Dry Run Demo ===\n")

    # Import dependencies
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

    from app.config_loader import get_config
    from app.media.image_adapter import ImageAdapter
    from app.media.video_adapter import VideoAdapter
    from app.engagement.politics_reply import PoliticalReplyGenerator

    # Initialize
    config = get_config()
    image_adapter = ImageAdapter()
    video_adapter = VideoAdapter()
    politics_gen = PoliticalReplyGenerator(config)
    composer = ReplyComposer(config, image_adapter, video_adapter, politics_gen)

    # Test tweets
    test_tweets = [
        ("Election turnout is at historic lows. We need reform.", "politics_user", "election 2024"),
        ("New AI policy could reshape tech regulation. Thoughts?", "tech_user", "tech policy"),
        ("The data shows inflation cooling faster than expected.", "econ_user", "economic policy"),
    ]

    for tweet_text, author, topic in test_tweets:
        print(f"Original Tweet: {tweet_text}")
        print(f"Author: @{author}, Topic: {topic}\n")

        result = composer.compose_reply(
            tweet_text=tweet_text,
            tweet_author=author,
            topic=topic,
            dry_run=True  # Don't generate actual media
        )

        if result['should_post']:
            print(f"Generated Reply: {result['text']}")
            print(f"Media: {result['media_path']}")
        else:
            print("(Would not post - safety check failed)")

        print("-" * 80 + "\n")


if __name__ == "__main__":
    dry_run_demo()
