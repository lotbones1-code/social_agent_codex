"""Environment configuration utilities for the social agent bot."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from dotenv import dotenv_values


TEMPLATE_DELIMITER = "||"


DEFAULT_REPLY_TEMPLATES: List[str] = [
    "Love this breakdown on {topic}! Always hunting for fresh automation wins.",
    "This perspective on {focus} is 🔥 — saving it for the next build sprint.",
    "Big nod to this thread about {topic}. Sharing it with my team tonight.",
    "Appreciate the clarity on {focus}. Exactly the kind of insight that ships features.",
]


DEFAULT_DM_TEMPLATES: List[str] = [
    "Hey {name}! Your notes on {focus} were super helpful. Always down to trade playbooks.",
    "Loved the depth you brought to {focus}. If you ever want to swap automations, I’m around.",
    "Appreciate how you framed {focus}. Let me know if you want to riff on it further.",
    "Your take on {focus} made my bookmarks. Happy to compare builds anytime.",
]


ENV_DEFAULTS: Dict[str, str] = {
    "SEARCH_TOPICS": "AI automation||viral clips||creator tools",
    "REPLY_TEMPLATES": TEMPLATE_DELIMITER.join(DEFAULT_REPLY_TEMPLATES),
    "DM_TEMPLATES": TEMPLATE_DELIMITER.join(DEFAULT_DM_TEMPLATES),
    "RELEVANT_KEYWORDS": "AI||automation||growth||launch||creator economy",
    "SPAM_KEYWORDS": "giveaway||airdrop||pump||casino||xxx||nsfw",
    "ENABLE_DMS": "true",
    "MIN_TWEET_LENGTH": "60",
    "MIN_KEYWORD_MATCHES": "1",
    "MAX_REPLIES_PER_TOPIC": "3",
    "LOOP_DELAY_SECONDS": "900",
    "DM_TRIGGER_LENGTH": "220",
    "DM_QUESTION_WEIGHT": "0.75",
    "DM_INTEREST_THRESHOLD": "3.2",
    "ACTION_DELAY_MIN_SECONDS": "60",
    "ACTION_DELAY_MAX_SECONDS": "600",
    "MESSAGE_REGISTRY_PATH": "logs/messaged_users.json",
    "IMAGE_PROVIDER": "openai",
    "IMAGE_MODEL": "dall-e-3",
    "IMAGE_SIZE": "1024x1024",
    "VIDEO_PROVIDER": "replicate",
    "VIDEO_MODEL": "pika-labs/pika-1.0",
    "VIDEO_DURATION_SECONDS": "8",
    "TRENDING_HASHTAG_URL": "",
    "HASHTAG_REFRESH_MINUTES": "45",
    "OPENAI_API_KEY": "<set-your-openai-api-key>",
    "REPLICATE_API_TOKEN": "<set-your-replicate-api-token>",
    "REPL_IMAGE_MODEL": "",
    "REPL_IMAGE_VERSION": "",
    "REPL_IMAGE_INPUT": "",
}


def ensure_env_file(root: Path) -> Path:
    """Ensure the project .env file exists and contains required defaults."""

    env_path = root / ".env"
    if env_path.exists():
        existing = dotenv_values(env_path)
    else:
        existing = {}

    merged: Dict[str, str] = {}
    changed = not env_path.exists()

    for key, value in existing.items():
        if value is not None:
            merged[key] = value

    for key, default in ENV_DEFAULTS.items():
        current = merged.get(key, "").strip()
        if not current:
            merged[key] = default
            changed = True

    if changed:
        write_env(env_path, merged)

    return env_path


def write_env(env_path: Path, values: Dict[str, str]) -> None:
    lines = [f"{key}={_escape_value(value)}\n" for key, value in sorted(values.items())]
    env_path.write_text("".join(lines), encoding="utf-8")


def update_env(env_path: Path, updates: Dict[str, str]) -> None:
    """Update the .env file with the provided key/value overrides."""

    current = dotenv_values(env_path) if env_path.exists() else {}
    merged: Dict[str, str] = {}
    for key, value in current.items():
        if value is not None:
            merged[key] = value
    merged.update(updates)
    write_env(env_path, merged)


def _escape_value(value: str) -> str:
    if not value:
        return ""
    if any(char in value for char in (" ", "#", "\n")):
        escaped = value.replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def parse_delimited_list(raw: str) -> List[str]:
    if not raw:
        return []
    normalized = raw.replace(TEMPLATE_DELIMITER, "\n")
    items: List[str] = []
    for line in normalized.splitlines():
        for piece in line.split(","):
            item = piece.strip()
            if item:
                items.append(item)
    return items
