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
        add_ons = ["", "🔥", "🚀", "🤖", "✨"]
        decorated_summary = context.summary.strip()
        if not decorated_summary:
            decorated_summary = f"Great take on {context.topic}!"
        suffix = random.choice(add_ons)
        template = self.template
        if "{author}" in template:
            template = template.replace("{author}", "").replace("via ", "").replace("by ", "")
        base = template.format(summary=decorated_summary, author="").strip()
        caption = f"{base} {suffix}".strip()
        return self._sanitize_caption(caption)

    def _chatgpt_caption(self, context: VideoContext) -> Optional[str]:
        if not self.client:
            return None
        prompt = (
            "You are an expert viral social copywriter for X (Premium+ enabled). "
            "Write a concise, hype caption (260 chars max) for a video. Include 2-3 hashtags "
            "that match the topic and hook viewers. Keep it punchy and avoid emojis unless they add impact. "
            "Do NOT tag, credit, or mention any accounts or usernames in the caption.\n\n"
            f"Topic: {context.topic}\n"
            f"Video summary: {context.summary}\n"
            f"Original author: {context.author}\n"
            f"Source URL: {context.url}\n"
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
        without_mentions = re.sub(r"@\w+", "", caption)
        normalized = re.sub(r"\s+", " ", without_mentions).strip()
        return normalized


__all__ = ["CaptionGenerator", "VideoContext"]
