from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv


@dataclass
class AgentConfig:
    """Runtime configuration for the influencer bot."""

    headless: bool = True
    debug: bool = False
    auth_state: Path = Path("auth.json")
    user_data_dir: Path = Path.home() / ".social_agent/browser"
    download_dir: Path = Path("downloads")
    search_topics: List[str] = field(default_factory=lambda: ["automation", "ai agents"])
    max_videos_per_topic: int = 2
    caption_template: str = "{summary}\n🚀 Sourced via {author} — #ai #automation"
    growth_actions_per_cycle: int = 3
    auto_replies_per_cycle: int = 2
    auto_reply_template: str = "Thanks for the mention, {author}! 🚀"
    trending_enabled: bool = True
    trending_max_topics: int = 6
    trending_refresh_minutes: int = 45
    openai_api_key: str | None = None
    gpt_caption_model: str = "gpt-4o-mini"
    download_user_agent: str | None = None
    action_delay_min: int = 6
    action_delay_max: int = 16
    loop_delay_seconds: int = 300
    influencer_mode: bool = False
    strict_mode: bool = True
    influencer_posts_min_per_day: int = 4
    influencer_posts_max_per_day: int = 7
    influencer_delay_min_seconds: int = 7200
    influencer_delay_max_seconds: int = 25200
    influencer_candidate_cap: int = 30
    influencer_inbox_dir: Path = Path("media/influencer_inbox")
    influencer_posted_dir: Path = Path("media/influencer_posted")
    influencer_reply_targets: List[str] = field(default_factory=list)
    influencer_replies_per_target: int = 1
    influencer_reply_delay_min_seconds: int = 300
    influencer_reply_delay_max_seconds: int = 900
    influencer_caption_template: str = (
        "{summary}\n\n🔥 via {author} | #{topic} #viral #fyp #trending"
    )

    def ensure_paths(self) -> None:
        self.auth_state.parent.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.influencer_inbox_dir.mkdir(parents=True, exist_ok=True)
        self.influencer_posted_dir.mkdir(parents=True, exist_ok=True)


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_config() -> AgentConfig:
    """Load configuration from environment variables."""

    load_dotenv()

    cfg = AgentConfig()
    cfg.headless = _parse_bool(os.getenv("HEADLESS"), cfg.headless)
    cfg.debug = _parse_bool(os.getenv("DEBUG"), cfg.debug)
    cfg.influencer_mode = _parse_bool(os.getenv("INFLUENCER_MODE"), cfg.influencer_mode)
    cfg.strict_mode = _parse_bool(os.getenv("STRICT_MODE"), cfg.strict_mode)

    auth_path = os.getenv("AUTH_FILE") or os.getenv("AUTH_STATE")
    if auth_path:
        cfg.auth_state = Path(auth_path).expanduser()

    user_data_dir = os.getenv("USER_DATA_DIR")
    if user_data_dir:
        cfg.user_data_dir = Path(user_data_dir).expanduser()

    download_dir = os.getenv("DOWNLOAD_DIR")
    if download_dir:
        cfg.download_dir = Path(download_dir).expanduser()

    inbox_dir = os.getenv("INFLUENCER_INBOX_DIR")
    if inbox_dir:
        cfg.influencer_inbox_dir = Path(inbox_dir).expanduser()

    posted_dir = os.getenv("INFLUENCER_POSTED_DIR")
    if posted_dir:
        cfg.influencer_posted_dir = Path(posted_dir).expanduser()

    topics = os.getenv("SEARCH_TOPICS")
    if topics:
        cfg.search_topics = [topic.strip() for topic in topics.replace("|", ",").split(",") if topic.strip()]

    template = os.getenv("CAPTION_TEMPLATE")
    if template:
        cfg.caption_template = template

    reply_template = os.getenv("AUTO_REPLY_TEMPLATE")
    if reply_template:
        cfg.auto_reply_template = reply_template

    influencer_caption_template = os.getenv("INFLUENCER_CAPTION_TEMPLATE")
    if influencer_caption_template:
        cfg.influencer_caption_template = influencer_caption_template

    cfg.max_videos_per_topic = int(os.getenv("MAX_VIDEOS_PER_TOPIC", cfg.max_videos_per_topic))
    cfg.growth_actions_per_cycle = int(
        os.getenv("GROWTH_ACTIONS_PER_CYCLE", cfg.growth_actions_per_cycle)
    )
    cfg.auto_replies_per_cycle = int(
        os.getenv("AUTO_REPLIES_PER_CYCLE", cfg.auto_replies_per_cycle)
    )
    cfg.influencer_posts_min_per_day = int(
        os.getenv("INFLUENCER_POSTS_MIN", cfg.influencer_posts_min_per_day)
    )
    cfg.influencer_posts_max_per_day = int(
        os.getenv("INFLUENCER_POSTS_MAX", cfg.influencer_posts_max_per_day)
    )
    cfg.influencer_delay_min_seconds = int(
        os.getenv("INFLUENCER_DELAY_MIN_SECONDS", cfg.influencer_delay_min_seconds)
    )
    cfg.influencer_delay_max_seconds = int(
        os.getenv("INFLUENCER_DELAY_MAX_SECONDS", cfg.influencer_delay_max_seconds)
    )
    cfg.influencer_candidate_cap = int(
        os.getenv("INFLUENCER_CANDIDATE_CAP", cfg.influencer_candidate_cap)
    )
    cfg.influencer_replies_per_target = int(
        os.getenv("INFLUENCER_REPLIES_PER_TARGET", cfg.influencer_replies_per_target)
    )
    cfg.influencer_reply_delay_min_seconds = int(
        os.getenv(
            "INFLUENCER_REPLY_DELAY_MIN_SECONDS", cfg.influencer_reply_delay_min_seconds
        )
    )
    cfg.influencer_reply_delay_max_seconds = int(
        os.getenv(
            "INFLUENCER_REPLY_DELAY_MAX_SECONDS", cfg.influencer_reply_delay_max_seconds
        )
    )
    cfg.trending_enabled = _parse_bool(os.getenv("TRENDING_ENABLED"), cfg.trending_enabled)
    cfg.trending_max_topics = int(
        os.getenv("TRENDING_MAX_TOPICS", cfg.trending_max_topics)
    )
    cfg.trending_refresh_minutes = int(
        os.getenv("TRENDING_REFRESH_MINUTES", cfg.trending_refresh_minutes)
    )
    cfg.openai_api_key = os.getenv("OPENAI_API_KEY") or None
    cfg.gpt_caption_model = os.getenv("GPT_CAPTION_MODEL", cfg.gpt_caption_model)
    cfg.download_user_agent = os.getenv("DOWNLOAD_USER_AGENT") or None
    cfg.action_delay_min = int(os.getenv("ACTION_DELAY_MIN", cfg.action_delay_min))
    cfg.action_delay_max = int(os.getenv("ACTION_DELAY_MAX", cfg.action_delay_max))
    cfg.loop_delay_seconds = int(os.getenv("LOOP_DELAY_SECONDS", cfg.loop_delay_seconds))

    reply_targets = os.getenv("INFLUENCER_REPLY_TARGETS")
    if reply_targets:
        cfg.influencer_reply_targets = [
            handle.strip().lstrip("@")
            for handle in reply_targets.replace("|", ",").split(",")
            if handle.strip()
        ]

    cfg.ensure_paths()
    return cfg
