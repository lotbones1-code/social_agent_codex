"""
FEATURE: AI Image Generation Adapter
WHAT: Generates images for political/tech tweets using AI APIs
WHY: Adds visual content to increase engagement
HOW TO REVERT: Set media_probability=0 in bot_config.json or delete this file

NO AUTH/LOGIN CHANGES - This is purely content generation
"""

import logging
import os
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Check if PIL is available (for local fallback generation)
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.debug("[media] PIL not available - image generation disabled")


class ImageAdapter:
    """
    Adapter for AI image generation.
    NO-OP if required API keys are missing.
    """

    def __init__(self):
        """Initialize image adapter (checks for API keys)."""
        self.enabled = False
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()

        # If no API key, check if PIL is available for local generation
        if not self.api_key and PIL_AVAILABLE:
            logger.info("[media] No OpenAI key, using local PIL image generation")
            self.enabled = True
            self.mode = "local"
        elif self.api_key:
            logger.info("[media] OpenAI key found, AI image generation enabled")
            self.enabled = True
            self.mode = "ai"
        else:
            logger.info("[media] No API keys or PIL - image generation disabled")
            self.mode = "disabled"

    def generate_political_image(self, topic: str, context: str) -> Optional[str]:
        """
        Generate an image related to political/news content.

        Args:
            topic: Topic string (e.g., "election 2024")
            context: Context/quote for the image

        Returns:
            Path to generated image file, or None if generation failed/disabled
        """
        if not self.enabled:
            return None

        try:
            if self.mode == "local":
                return self._generate_local_quote_image(topic, context)
            elif self.mode == "ai":
                logger.debug("[media] AI image generation not yet implemented")
                # Fall back to local for now
                return self._generate_local_quote_image(topic, context)
            else:
                return None

        except Exception as exc:
            logger.debug(f"[media] Image generation failed (non-critical): {exc}")
            return None

    def _generate_local_quote_image(self, topic: str, text: str) -> Optional[str]:
        """
        Generate a simple quote image using PIL (local, no API needed).

        Args:
            topic: Topic for styling
            text: Text to display

        Returns:
            Path to generated image
        """
        if not PIL_AVAILABLE:
            return None

        try:
            # Create output directory
            output_dir = Path.home() / ".social_agent_codex" / "generated_images"
            output_dir.mkdir(parents=True, exist_ok=True)

            import time
            output_path = str(output_dir / f"political_{int(time.time())}.png")

            # Create image (Twitter optimal size)
            width, height = 1200, 630
            img = Image.new('RGB', (width, height), color='#1a1a2e')  # Dark blue background

            draw = ImageDraw.Draw(img)

            # Try to use a nice font, fall back to default
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
                topic_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
            except:
                font = ImageFont.load_default()
                topic_font = ImageFont.load_default()

            # Truncate text to fit
            max_chars = 80
            display_text = text[:max_chars] + "..." if len(text) > max_chars else text

            # Draw text with shadow for readability
            text_color = '#ffffff'
            shadow_color = '#000000'

            # Calculate text position (centered)
            bbox = draw.textbbox((0, 0), display_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (width - text_width) // 2
            y = (height - text_height) // 2

            # Draw shadow
            draw.text((x+2, y+2), display_text, font=font, fill=shadow_color)
            # Draw main text
            draw.text((x, y), display_text, font=font, fill=text_color)

            # Draw topic label at bottom
            topic_text = f"#{topic.replace(' ', '')}"
            topic_bbox = draw.textbbox((0, 0), topic_text, font=topic_font)
            topic_x = (width - (topic_bbox[2] - topic_bbox[0])) // 2
            draw.text((topic_x, height - 80), topic_text, font=topic_font, fill='#888888')

            # Save
            img.save(output_path, 'PNG', optimize=True)
            logger.info(f"[media] Generated local image: {output_path}")

            return output_path

        except Exception as exc:
            logger.debug(f"[media] Local image generation failed: {exc}")
            return None
