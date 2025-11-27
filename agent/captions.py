"""Caption generation utilities."""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List

from .config import BotSettings
from .scraper import VideoItem


@dataclass(slots=True)
class CaptionGenerator:
    templates: List[str]
    hashtags: List[str]

    @classmethod
    def from_config(cls, config: BotSettings) -> "CaptionGenerator":
        return cls(templates=config.captions, hashtags=config.hashtags)

    def render(self, item: VideoItem) -> str:
        hook_options = [
            f"This clip on {item.topic} is worth a save",
            f"Sharing a quick {item.topic} gem",
            f"Builders will like this {item.topic} drop",
        ]
        hook = random.choice(hook_options)
        hashtags = " ".join(self.hashtags)
        template = random.choice(self.templates)
        return template.format(hook=hook, source=item.source, topic=item.topic, hashtags=hashtags)
