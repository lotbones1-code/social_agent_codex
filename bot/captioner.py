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
        """Generate a simple fallback caption when AI generation fails or is not available."""
        add_ons = ["", "🔥", "🚀", "✨"]
        decorated_summary = context.summary.strip()
        if not decorated_summary:
            decorated_summary = f"Check out this {context.topic} content!"

        suffix = random.choice(add_ons)
        template = self.template

        # Ensure no {author} references leak through
        template = template.replace("{author}", "").replace("via ", "").replace("by ", "")

        # Format with just the summary
        base = template.format(summary=decorated_summary).strip()
        caption = f"{base} {suffix}".strip()

        return self._sanitize_caption(caption)

    def _chatgpt_caption(self, context: VideoContext) -> Optional[str]:
        if not self.client:
            return None
        prompt = (
            "You are an expert viral social copywriter for X (formerly Twitter). "
            "Write a concise, engaging caption (max 260 chars) for a video post. Include 2-3 relevant hashtags. "
            "Keep it punchy, authentic, and scroll-stopping. Use emojis sparingly and only when they add value.\n\n"
            "CRITICAL RULES:\n"
            "- DO NOT tag, mention, or credit ANY accounts (@handles)\n"
            "- DO NOT include 'via', 'from', 'by', 'credit', 'source', 'h/t', or similar attributions\n"
            "- DO NOT reference the original author or creator in any way\n"
            "- ONLY output the caption text + hashtags (nothing else)\n\n"
            f"Topic: {context.topic}\n"
            f"Video summary: {context.summary}\n"
        )
        try:  # pragma: no cover - remote call
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
                temperature=0.7,
            )
            content = response.choices[0].message.content if response.choices else None
            if content:
                caption = content.strip()
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
        r"\bvia\s+[^\n#]+",           # "via SomeAccount" or "via @user"
        r"\bcredit\s+to\s+[^\n#]+",   # "credit to SomeAccount"
        r"\bcredits?\s*:\s*[^\n#]+",  # "credit:" or "credits:"
        r"\bsource\s*:\s*[^\n#]+",    # "source: something"
        r"\bfrom\s+@?\w+",             # "from @user" or "from Account"
        r"\bby\s+@?\w+",               # "by @user" or "by Account"
        r"\bh/?t\s+@?\w+",             # "h/t @user" (hat tip)
        r"\bshoutout\s+to\s+[^\n#]+", # "shoutout to @user"
        r"\bfollow\s+@?\w+",           # "follow @user"
    ]

    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove orphaned punctuation left behind
    text = re.sub(r"\s*[,;:]\s*$", "", text)  # Trailing commas/semicolons
    text = re.sub(r"^\s*[,;:]\s*", "", text)  # Leading commas/semicolons
    text = re.sub(r"\.{2,}", ".", text)        # Multiple dots
    text = re.sub(r"\s*-\s*$", "", text)       # Trailing dashes

    # Clean excessive whitespace
    text = " ".join(text.split())

    return text.strip()
