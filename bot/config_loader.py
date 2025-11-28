"""Configuration loader for influencer bot."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml
from dotenv import load_dotenv


@dataclass
class InfluencerConfig:
    """Influencer bot settings."""
    enabled: bool = True
    daily_post_min: int = 4
    daily_post_max: int = 7
    cycles_per_day: int = 10
    topics: List[str] = field(default_factory=lambda: ["sports", "fails", "funny"])
    language: str = "english"
    caption_style: str = "hype_short"
    reply_to_big_accounts: bool = False
    retweet_after_post: bool = True
    like_source_tweets: bool = True
    big_accounts: List[str] = field(default_factory=list)


@dataclass
class BrowserConfig:
    """Browser connection settings."""
    use_cdp: bool = True
    cdp_url: str = "http://localhost:9222"
    headless: bool = False


@dataclass
class DownloadConfig:
    """Download settings."""
    dir: str = "downloads"
    cleanup_after_post: bool = False


@dataclass
class SafetyConfig:
    """Safety and rate limiting settings."""
    action_delay_min: int = 3
    action_delay_max: int = 8
    cycle_delay_seconds: int = 600
    max_daily_posts: int = 7
    post_tracking_file: str = "logs/daily_posts.json"


@dataclass
class OpenAIConfig:
    """OpenAI API settings."""
    model: str = "gpt-4o-mini"
    max_tokens: int = 100
    temperature: float = 0.9
    api_key: str = ""


@dataclass
class BotConfig:
    """Complete bot configuration."""
    influencer: InfluencerConfig
    browser: BrowserConfig
    download: DownloadConfig
    safety: SafetyConfig
    openai: OpenAIConfig


def load_config(config_path: str = "config.yaml") -> BotConfig:
    """Load configuration from YAML file and environment variables."""
    load_dotenv()

    # Load YAML
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            data = yaml.safe_load(f)
    else:
        data = {}

    # Parse influencer config
    inf_data = data.get("influencer", {})
    influencer = InfluencerConfig(
        enabled=inf_data.get("enabled", True),
        daily_post_min=inf_data.get("daily_post_min", 4),
        daily_post_max=inf_data.get("daily_post_max", 7),
        cycles_per_day=inf_data.get("cycles_per_day", 10),
        topics=inf_data.get("topics", ["sports", "fails", "funny"]),
        language=inf_data.get("language", "english"),
        caption_style=inf_data.get("caption_style", "hype_short"),
        reply_to_big_accounts=inf_data.get("reply_to_big_accounts", False),
        retweet_after_post=inf_data.get("retweet_after_post", True),
        like_source_tweets=inf_data.get("like_source_tweets", True),
        big_accounts=inf_data.get("big_accounts", []),
    )

    # Parse browser config
    browser_data = data.get("browser", {})
    browser = BrowserConfig(
        use_cdp=browser_data.get("use_cdp", True),
        cdp_url=browser_data.get("cdp_url", "http://localhost:9222"),
        headless=browser_data.get("headless", False),
    )

    # Parse download config
    download_data = data.get("download", {})
    download = DownloadConfig(
        dir=download_data.get("dir", "downloads"),
        cleanup_after_post=download_data.get("cleanup_after_post", False),
    )

    # Parse safety config
    safety_data = data.get("safety", {})
    safety = SafetyConfig(
        action_delay_min=safety_data.get("action_delay_min", 3),
        action_delay_max=safety_data.get("action_delay_max", 8),
        cycle_delay_seconds=safety_data.get("cycle_delay_seconds", 600),
        max_daily_posts=safety_data.get("max_daily_posts", 7),
        post_tracking_file=safety_data.get("post_tracking_file", "logs/daily_posts.json"),
    )

    # Parse OpenAI config (with env override)
    openai_data = data.get("openai", {})
    openai = OpenAIConfig(
        model=openai_data.get("model", "gpt-4o-mini"),
        max_tokens=openai_data.get("max_tokens", 100),
        temperature=openai_data.get("temperature", 0.9),
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )

    return BotConfig(
        influencer=influencer,
        browser=browser,
        download=download,
        safety=safety,
        openai=openai,
    )


__all__ = ["BotConfig", "load_config"]
