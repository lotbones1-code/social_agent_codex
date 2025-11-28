from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Optional

try:  # Optional dependency; enabled when OPENAI_API_KEY is set.
    from openai import OpenAI
except Exception:  # pragma: no cover - handled gracefully at runtime
    OpenAI = None


@dataclass
class InfluencerContext:
    author: str
    topic: str
    text: str
    url: str


class InfluencerCaptioner:
    """Generate viral-style captions + hashtag bundles for influencer posts."""

    def __init__(
        self,
        template: str,
        *,
        openai_api_key: str | None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.template = template
        self.model = model
        self.logger = logging.getLogger("influencer_captioner")
        self.client: Optional[OpenAI] = None
        if openai_api_key and OpenAI:
            try:
                self.client = OpenAI(api_key=openai_api_key)
                self.logger.info("ChatGPT influencer captions enabled with %s", model)
            except Exception as exc:  # pragma: no cover - network dependent
                self.logger.warning("Could not initialize ChatGPT client: %s", exc)

    def _fallback(self, ctx: InfluencerContext) -> str:
        base = self.template.format(
            summary=ctx.text.strip() or f"Wild take on {ctx.topic}!",
            author=ctx.author or "@unknown",
            topic=ctx.topic or "viral",
        )
        hashtags = [
            "#viral",
            "#fyp",
            "#trending",
            "#mustwatch",
            f"#{ctx.topic.split()[0].lower()}" if ctx.topic else "",
        ]
        deduped = []
        for tag in hashtags:
            clean = tag.strip()
            if clean and clean not in deduped:
                deduped.append(clean)
        random.shuffle(deduped)
        return f"{base}\n\n{' '.join(deduped[:6])}"

    def _ai_caption(self, ctx: InfluencerContext) -> Optional[str]:
        if not self.client:
            return None
        prompt = (
            "You are a viral X video captioner. Write a 1-2 sentence hook with a human tone "
            "(no cringe). Then append 4-10 strong hashtags tailored to X (avoid spaces, all lowercase). "
            "Keep everything under 280 characters.\n\n"
            f"Topic: {ctx.topic}\n"
            f"Original tweet text: {ctx.text}\n"
            f"Original author: {ctx.author}\n"
            f"Source URL: {ctx.url}\n"
        )
        try:  # pragma: no cover - network dependent
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=160,
                temperature=0.65,
            )
            content = response.choices[0].message.content if response.choices else None
            if content:
                caption = content.strip()
                if len(caption) > 280:
                    caption = caption[:277] + "..."
                return caption
        except Exception as exc:
            self.logger.warning("ChatGPT influencer caption failed: %s", exc)
        return None

    def generate(self, ctx: InfluencerContext) -> str:
        caption = self._ai_caption(ctx)
        if caption:
            return caption
        return self._fallback(ctx)


__all__ = ["InfluencerCaptioner", "InfluencerContext"]
