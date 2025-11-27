from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass
class VideoContext:
    author: str
    summary: str
    topic: str
    url: str


class CaptionGenerator:
    """Create social-ready captions for reposted videos."""

    def __init__(self, template: str):
        self.template = template

    def generate(self, context: VideoContext) -> str:
        add_ons = ["", "🔥", "🚀", "🤖", "✨"]
        decorated_summary = context.summary.strip()
        if not decorated_summary:
            decorated_summary = f"Great take on {context.topic}!"
        suffix = random.choice(add_ons)
        base = self.template.format(summary=decorated_summary, author=context.author or "@unknown")
        return f"{base} {suffix}".strip()


__all__ = ["CaptionGenerator", "VideoContext"]
