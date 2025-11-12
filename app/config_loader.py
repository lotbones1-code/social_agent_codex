"""
FEATURE: Political Mode Configuration Loader
WHAT: Loads bot_config.json for political engagement mode
WHY: Allows switching from gambling to politics without breaking existing code
HOW TO REVERT: Set USE_NEW_CONFIG=false in .env or delete this file

NO AUTH/LOGIN CHANGES - This module only reads config files
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class BotConfigLoader:
    """
    Loads and validates bot_config.json for political mode.
    Falls back to safe defaults if file missing or invalid.
    """

    DEFAULT_CONFIG = {
        "modes": ["politics"],
        "rotation_enabled": False,
        "single_mode_override": "politics",
        "promo_links": {},
        "exclude_domains": ["rainbet", "stake", "rollbit"],
        "promo_frequency": 0.0,  # Safe default: no promotion
        "media_probability": 0.0,  # Safe default: no media
        "max_reply_length": 270,
        "hashtags_allowlist": ["#Breaking", "#News"],
        "debate_style": "confident-civil",
        "political_topics": ["US politics", "policy debate"],
        "reply_tones": ["analytical"]
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize config loader.

        Args:
            config_path: Path to bot_config.json (default: config/bot_config.json)
        """
        if config_path is None:
            config_path = str(Path(__file__).parent.parent / "config" / "bot_config.json")

        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """
        Load config from JSON file with safe fallback.

        Returns:
            Dict with configuration (defaults if file missing/invalid)
        """
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"[config] Config file not found: {self.config_path}, using defaults")
                return self.DEFAULT_CONFIG.copy()

            with open(self.config_path, 'r') as f:
                config = json.load(f)

            # Validate and cap dangerous values
            config['promo_frequency'] = min(float(config.get('promo_frequency', 0.25)), 0.3)
            config['media_probability'] = min(float(config.get('media_probability', 0.25)), 0.3)
            config['max_reply_length'] = min(int(config.get('max_reply_length', 270)), 280)

            logger.info(f"[config] Loaded config from {self.config_path}")
            logger.info(f"[config] Active modes: {config.get('modes', [])}")
            logger.info(f"[config] Promo frequency: {config['promo_frequency']}")

            return config

        except json.JSONDecodeError as e:
            logger.error(f"[config] Invalid JSON in {self.config_path}: {e}")
            logger.warning("[config] Using default config due to JSON error")
            return self.DEFAULT_CONFIG.copy()

        except Exception as e:
            logger.error(f"[config] Failed to load config: {e}")
            logger.warning("[config] Using default config due to error")
            return self.DEFAULT_CONFIG.copy()

    def get_active_mode(self) -> str:
        """
        Get the current active mode (respects single_mode_override).

        Returns:
            Mode string (e.g., "politics", "tech")
        """
        override = self.config.get('single_mode_override', '').strip()
        if override:
            return override

        # If rotation enabled, return first mode (rotation logic elsewhere)
        modes = self.config.get('modes', ['politics'])
        return modes[0] if modes else 'politics'

    def get_topics_for_mode(self, mode: str) -> list:
        """
        Get search topics for a specific mode.

        Args:
            mode: Mode name (e.g., "politics")

        Returns:
            List of topic strings
        """
        if mode == "politics":
            return self.config.get('political_topics', self.DEFAULT_CONFIG['political_topics'])
        elif mode == "tech":
            return ["AI news", "tech policy", "Silicon Valley", "startups", "tech debate"]
        elif mode == "culture":
            return ["social trends", "media analysis", "cultural debate", "entertainment"]
        else:
            return self.config.get('political_topics', self.DEFAULT_CONFIG['political_topics'])

    def should_include_promo(self) -> bool:
        """
        Determine if this reply should include a promo link.

        Returns:
            True if promo should be included (based on frequency)
        """
        import random
        return random.random() < self.config['promo_frequency']

    def should_include_media(self) -> bool:
        """
        Determine if this reply should include media (image/video).

        Returns:
            True if media should be included (based on probability)
        """
        import random
        return random.random() < self.config['media_probability']

    def get_promo_link(self, link_type: str = "gumroad") -> Optional[str]:
        """
        Get a promotional link by type.

        Args:
            link_type: Type of link (e.g., "gumroad")

        Returns:
            Link URL or None if not configured
        """
        return self.config.get('promo_links', {}).get(link_type)

    def is_excluded_domain(self, url: str) -> bool:
        """
        Check if a URL contains an excluded domain.

        Args:
            url: URL to check

        Returns:
            True if URL contains excluded domain
        """
        url_lower = url.lower()
        for domain in self.config.get('exclude_domains', []):
            if domain.lower() in url_lower:
                return True
        return False


# Singleton instance for easy access
_config_instance: Optional[BotConfigLoader] = None


def get_config() -> BotConfigLoader:
    """
    Get singleton config instance.

    Returns:
        BotConfigLoader instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = BotConfigLoader()
    return _config_instance
