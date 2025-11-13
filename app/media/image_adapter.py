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

        # Check for API keys (priority order)
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()

        # Determine mode
        if self.hf_api_key:
            logger.info("[media] 🎨 Hugging Face API key found - FREE AI image generation enabled!")
            self.enabled = True
            self.mode = "huggingface"
        elif self.openai_api_key:
            logger.info("[media] OpenAI key found - AI image generation enabled")
            self.enabled = True
            self.mode = "openai"
        elif PIL_AVAILABLE:
            logger.info("[media] No AI API keys, using local PIL image generation (basic)")
            self.enabled = True
            self.mode = "local"
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
            if self.mode == "huggingface":
                return self._generate_huggingface_image(topic, context)
            elif self.mode == "openai":
                logger.debug("[media] OpenAI image generation not yet implemented")
                # Fall back to local for now
                if PIL_AVAILABLE:
                    return self._generate_local_quote_image(topic, context)
                return None
            elif self.mode == "local":
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

    def _generate_huggingface_image(self, topic: str, context: str) -> Optional[str]:
        """
        Generate AI image using Hugging Face Inference API (FREE!).

        Args:
            topic: Topic for the image
            context: Context to generate from

        Returns:
            Path to generated image file
        """
        # Safety check: don't call API if no key
        if not self.hf_api_key:
            logger.debug("[media] No Hugging Face API key, skipping HF generation")
            if PIL_AVAILABLE:
                return self._generate_local_quote_image(topic, context)
            return None

        try:
            import requests
            import time

            # Create output directory
            output_dir = Path.home() / ".social_agent_codex" / "generated_images"
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = str(output_dir / f"ai_{int(time.time())}.png")

            # Create prompt for political/news image
            prompt = self._create_image_prompt(topic, context)

            logger.debug(f"[media] Generating AI image with Hugging Face: {prompt[:50]}...")

            # Use Stable Diffusion model on Hugging Face (FREE!)
            API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2-1"
            headers = {"Authorization": f"Bearer {self.hf_api_key}"}

            payload = {
                "inputs": prompt,
                "parameters": {
                    "negative_prompt": "text, watermark, signature, blurry, low quality",
                    "num_inference_steps": 30,
                }
            }

            response = requests.post(API_URL, headers=headers, json=payload, timeout=10)

            if response.status_code == 200:
                # Save image
                with open(output_path, 'wb') as f:
                    f.write(response.content)

                logger.info(f"[media] ✓ Generated AI image: {output_path}")
                return output_path

            elif response.status_code == 503:
                logger.debug("[media] Hugging Face model loading (503), falling back to local")
                # Model is loading, fall back to local
                if PIL_AVAILABLE:
                    return self._generate_local_quote_image(topic, context)
                return None

            else:
                logger.debug(f"[media] Hugging Face API error {response.status_code}, falling back")
                if PIL_AVAILABLE:
                    return self._generate_local_quote_image(topic, context)
                return None

        except requests.exceptions.Timeout:
            logger.debug("[media] Hugging Face API timeout, falling back to local")
            if PIL_AVAILABLE:
                return self._generate_local_quote_image(topic, context)
            return None

        except Exception as exc:
            logger.debug(f"[media] Hugging Face generation failed: {exc}, falling back")
            if PIL_AVAILABLE:
                return self._generate_local_quote_image(topic, context)
            return None

    def _create_image_prompt(self, topic: str, context: str) -> str:
        """Create AI image prompt from topic and context."""
        # Create clean, visual prompt for political/news content
        topic_clean = topic.lower().strip()

        if "election" in topic_clean or "politics" in topic_clean:
            base = "professional news photography, capitol building, voting, democracy, american flag"
        elif "tech" in topic_clean or "ai" in topic_clean:
            base = "futuristic technology, digital art, modern clean design, blue and white tones"
        elif "economic" in topic_clean or "policy" in topic_clean:
            base = "business professional setting, charts and graphs, modern office"
        else:
            base = "professional news photography, modern journalism, clean composition"

        return f"{base}, high quality, sharp focus, professional lighting, 4k"
