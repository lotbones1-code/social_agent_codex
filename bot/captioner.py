from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from typing import Optional

try:  # Optional dependency; enabled when OPENAI_API_KEY is set.
    from openai import OpenAI
except Exception:  # pragma: no cover - handled gracefully at runtime
    OpenAI = None


@dataclass
class VideoContext:
    author: str
    summary: str
    topic: str
    url: str


class CaptionGenerator:
    """Create social-ready captions for reposted videos.

    Falls back to a templated caption but will use ChatGPT (if configured) to
    craft a premium, hashtag-rich post optimized for engagement.
    """

    def __init__(self, template: str, *, openai_api_key: str | None = None, model: str = "gpt-4o-mini"):
        self.template = template
        self.model = model
        self.logger = logging.getLogger("captioner")
        self.client: Optional[OpenAI] = None
        if openai_api_key and OpenAI:
            try:
                self.client = OpenAI(api_key=openai_api_key)
                self.logger.info("ChatGPT captions enabled with model %s", model)
            except Exception as exc:  # pragma: no cover - network dependent
                self.logger.warning("Could not initialize ChatGPT client: %s", exc)

    def _fallback_caption(self, context: VideoContext) -> str:
        """Generate a viral-optimized fallback caption when AI generation fails or is not available."""
        # Better emoji choices based on content type
        topic_lower = context.topic.lower()
        if any(sport in topic_lower for sport in ["nfl", "nba", "mlb", "soccer", "football", "basketball"]):
            emojis = ["🔥", "⚡", "🏈", "🏀", ""]
            prefixes = ["THIS is crazy", "Absolutely INSANE", "No way", "Holy", ""]
        elif any(funny in topic_lower for funny in ["funny", "viral", "meme"]):
            emojis = ["😭", "💀", "😂", "", "lmao"]
            prefixes = ["I can't", "Why is this so", "This is the most", "Bro", ""]
        else:
            emojis = ["🔥", "🚀", "✨", "⚡", ""]
            prefixes = ["This is", "Absolutely", "Just", "Peak", ""]

        decorated_summary = context.summary.strip()
        if not decorated_summary:
            decorated_summary = f"{random.choice(prefixes)} {context.topic} content"

        # Build engaging caption
        prefix = random.choice(prefixes)
        emoji = random.choice(emojis)
        template = self.template

        # Ensure no {author} references leak through
        template = template.replace("{author}", "").replace("via ", "").replace("by ", "")

        # Format with summary
        base = template.format(summary=decorated_summary).strip()

        # Add prefix and emoji variation
        if prefix and random.random() > 0.5:
            caption = f"{prefix} {base} {emoji}".strip()
        else:
            caption = f"{base} {emoji}".strip()

        return self._sanitize_caption(caption)

    def _chatgpt_caption(self, context: VideoContext) -> Optional[str]:
        if not self.client:
            return None

        # Determine content strategy based on topic
        topic_lower = context.topic.lower()
        if any(sport in topic_lower for sport in ["nfl", "nba", "mlb", "soccer", "football", "basketball"]):
            style_hint = (
                "Write like a passionate sports fan. Use dramatic language, player names if mentioned, "
                "and capture the excitement. Examples: 'THIS is why [player] is HIM 🔥', "
                "'Absolutely INSANE play right here', 'No way this just happened 😳'"
            )
        elif any(funny in topic_lower for funny in ["funny", "viral", "meme"]):
            style_hint = (
                "Write like a viral meme account. Keep it relatable, witty, and shareable. "
                "Use internet slang naturally. Examples: 'I can't breathe 😭', "
                "'This is the most [adjective] thing I've seen today', 'Why is this so accurate lmao'"
            )
        elif "trending" in topic_lower or "news" in topic_lower:
            style_hint = (
                "Write like a breaking news account. Create urgency and FOMO. "
                "Examples: 'BREAKING: [event]', 'Everyone's talking about this', "
                "'This is blowing up right now 🚨'"
            )
        else:
            style_hint = (
                "Write like a viral content curator. Be engaging and shareable. "
                "Make people want to watch, like, and repost."
            )

        prompt = (
            "You are an EXPERT viral content creator for X (Twitter) with 1M+ followers. "
            "Your captions consistently get 10K+ likes because they're ENGAGING and SHAREABLE.\n\n"
            f"{style_hint}\n\n"
            "CAPTION REQUIREMENTS:\n"
            "✅ MAX 260 characters (leave room for video player)\n"
            "✅ Hook in first 5 words (make them STOP scrolling)\n"
            "✅ 2-3 strategic hashtags (trending + niche)\n"
            "✅ 1-2 emojis MAX (only if they add value)\n"
            "✅ Natural, conversational tone (not corporate)\n"
            "✅ Create curiosity or emotion (shock, humor, excitement)\n\n"
            "CRITICAL RULES:\n"
            "❌ NO @mentions, credits, attributions, 'via', 'from', 'by', 'source', 'h/t'\n"
            "❌ NO question marks in hooks (sounds desperate)\n"
            "❌ NO 'Check out', 'Watch', 'Look at' (boring)\n"
            "❌ NO emoji spam (looks fake)\n\n"
            f"Topic: {context.topic}\n"
            f"Video content: {context.summary}\n\n"
            "Write the caption NOW (ONLY the caption text, nothing else):"
        )
        try:  # pragma: no cover - remote call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,  # Increased from 120 for better captions
                temperature=0.8,  # Increased from 0.7 for more creative captions
            )
            content = response.choices[0].message.content if response.choices else None
            if content:
                caption = content.strip()
                # Remove quotes if GPT wrapped the caption
                caption = caption.strip('"').strip("'")
                if len(caption) > 260:
                    caption = caption[:257] + "..."
                return self._sanitize_caption(caption)
        except Exception as exc:
            self.logger.warning("ChatGPT caption failed, falling back: %s", exc)
        return None

    def generate(self, context: VideoContext) -> str:
        ai_caption = self._chatgpt_caption(context)
        if ai_caption:
            return ai_caption
        return self._fallback_caption(context)

    @staticmethod
    def _sanitize_caption(caption: str) -> str:
        """Remove any @mentions and normalize whitespace."""
        caption = strip_mentions_and_credits(caption)
        normalized = re.sub(r"\s+", " ", caption).strip()
        return normalized


__all__ = ["CaptionGenerator", "VideoContext"]


def strip_mentions_and_credits(text: str) -> str:
    """
    Aggressively remove all source attributions, mentions, and credits from caption text.
    Preserves hashtags (e.g., #NFL, #Ravens) but removes all @handles and source references.
    """
    # Remove @handles (but preserve hashtags)
    text = re.sub(r"@\w+", "", text)

    # Remove common source attribution patterns (case-insensitive)
    patterns = [
        r"📹\s*via\s+[^\n#]+",        # "📹 via ..."
        r"\bvia\s+[^\n#]+",           # "via SomeAccount"
        r"\bsourced\s+via\s+[^\n#]+", # "Sourced via ..."
        r"\bcredit\s+to\s+[^\n#]+",   # "credit to SomeAccount"
        r"\bcredits?\s*:\s*[^\n#]+",  # "credit:" or "credits:"
        r"\bsource\s*:\s*[^\n#]+",    # "source: something"
        r"\bfrom\s+@?\w+",            # "from @user"
        r"\bby\s+@?\w+",              # "by @user"
        r"\bh/?t\s+@?\w+",            # "h/t @user"
        r"\bshoutout\s+to\s+[^\n#]+", # "shoutout to"
        r"\bfollow\s+@?\w+",          # "follow @user"
        r"—\s*[^\n#]+$",              # "— anything at end"
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove orphaned punctuation
    text = re.sub(r"\s*[,;:]\s*$", "", text)
    text = re.sub(r"^\s*[,;:]\s*", "", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s*-\s*$", "", text)
    text = re.sub(r"\s*—\s*$", "", text)

    # Clean excessive whitespace
    text = " ".join(text.split())

    return text.strip()
