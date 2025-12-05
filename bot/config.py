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
    strict_mode: bool = True
    auth_state: Path = Path("auth.json")
    user_data_dir: Path = Path(".pwprofile")
    download_dir: Path = Path("downloads")
    search_topics: List[str] = field(
        default_factory=lambda: ["ai", "automation", "viral tech"]
    )
    max_videos_per_topic: int = 2
    max_posts_per_cycle: int = 2
    caption_template: str = "{summary}\n#AI #Automation"
    growth_actions_per_cycle: int = 3
    auto_replies_per_cycle: int = 0
    auto_reply_template: str = ""
    trending_enabled: bool = True
    trending_max_topics: int = 6
    trending_refresh_minutes: int = 45
    require_trending: bool = False
    openai_api_key: str | None = None
    gpt_caption_model: str = "gpt-4o-mini"
    download_user_agent: str | None = None
    action_delay_min: int = 6
    action_delay_max: int = 16
    loop_delay_seconds: int = 300
    min_viral_score: float = 0.25
    upload_retry_attempts: int = 3
    post_retry_attempts: int = 3
    # Reply bot settings
    reply_templates: List[str] = field(default_factory=list)
    referral_link: str = ""
    max_replies_per_topic: int = 3
    relevant_keywords: List[str] = field(
        default_factory=lambda: ["AI", "automation", "growth", "launch"]
    )
    spam_keywords: List[str] = field(
        default_factory=lambda: ["giveaway", "airdrop", "casino", "xxx"]
    )
    min_tweet_length: int = 60
    min_keyword_matches: int = 1
    enable_replies: bool = True

    def ensure_paths(self) -> None:
        self.auth_state.parent.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)


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

    topics = os.getenv("SEARCH_TOPICS")
    if topics:
        cfg.search_topics = [topic.strip() for topic in topics.replace("|", ",").split(",") if topic.strip()]

    template = os.getenv("CAPTION_TEMPLATE")
    if template:
        cfg.caption_template = template

    reply_template = os.getenv("AUTO_REPLY_TEMPLATE")
    if reply_template:
        cfg.auto_reply_template = reply_template

    cfg.max_videos_per_topic = int(os.getenv("MAX_VIDEOS_PER_TOPIC", cfg.max_videos_per_topic))
    cfg.max_posts_per_cycle = int(os.getenv("MAX_POSTS_PER_CYCLE", cfg.max_posts_per_cycle))
    cfg.growth_actions_per_cycle = int(
        os.getenv("GROWTH_ACTIONS_PER_CYCLE", cfg.growth_actions_per_cycle)
    )
    cfg.auto_replies_per_cycle = int(
        os.getenv("AUTO_REPLIES_PER_CYCLE", cfg.auto_replies_per_cycle)
    )
    cfg.trending_enabled = _parse_bool(os.getenv("TRENDING_ENABLED"), cfg.trending_enabled)
    cfg.trending_max_topics = int(
        os.getenv("TRENDING_MAX_TOPICS", cfg.trending_max_topics)
    )
    cfg.trending_refresh_minutes = int(
        os.getenv("TRENDING_REFRESH_MINUTES", cfg.trending_refresh_minutes)
    )
    cfg.require_trending = _parse_bool(
        os.getenv("REQUIRE_TRENDING"), cfg.require_trending
    )
    cfg.openai_api_key = os.getenv("OPENAI_API_KEY") or None
    cfg.gpt_caption_model = os.getenv("GPT_CAPTION_MODEL", cfg.gpt_caption_model)
    cfg.download_user_agent = os.getenv("DOWNLOAD_USER_AGENT") or None
    cfg.action_delay_min = int(os.getenv("ACTION_DELAY_MIN", cfg.action_delay_min))
    cfg.action_delay_max = int(os.getenv("ACTION_DELAY_MAX", cfg.action_delay_max))
    cfg.loop_delay_seconds = int(os.getenv("LOOP_DELAY_SECONDS", cfg.loop_delay_seconds))
    cfg.min_viral_score = float(os.getenv("MIN_VIRAL_SCORE", cfg.min_viral_score))
    cfg.upload_retry_attempts = int(
        os.getenv("UPLOAD_RETRY_ATTEMPTS", cfg.upload_retry_attempts)
    )
    cfg.post_retry_attempts = int(os.getenv("POST_RETRY_ATTEMPTS", cfg.post_retry_attempts))

    # Reply bot settings
    cfg.referral_link = os.getenv("REFERRAL_LINK", cfg.referral_link)
    cfg.max_replies_per_topic = int(os.getenv("MAX_REPLIES_PER_TOPIC", cfg.max_replies_per_topic))
    cfg.min_tweet_length = int(os.getenv("MIN_TWEET_LENGTH", cfg.min_tweet_length))
    cfg.min_keyword_matches = int(os.getenv("MIN_KEYWORD_MATCHES", cfg.min_keyword_matches))
    cfg.enable_replies = _parse_bool(os.getenv("ENABLE_REPLIES"), cfg.enable_replies)

    # Parse reply templates (pipe-separated)
    reply_templates_raw = os.getenv("REPLY_TEMPLATES", "")
    if reply_templates_raw:
        cfg.reply_templates = [t.strip() for t in reply_templates_raw.split("||") if t.strip()]

    # Parse keywords (pipe-separated)
    keywords_raw = os.getenv("RELEVANT_KEYWORDS", "")
    if keywords_raw:
        cfg.relevant_keywords = [k.strip() for k in keywords_raw.split("||") if k.strip()]

    spam_raw = os.getenv("SPAM_KEYWORDS", "")
    if spam_raw:
        cfg.spam_keywords = [k.strip() for k in spam_raw.split("||") if k.strip()]

    cfg.ensure_paths()
    return cfg
