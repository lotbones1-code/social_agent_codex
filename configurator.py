"""Environment configuration utilities for the social agent bot."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from dotenv import dotenv_values


TEMPLATE_DELIMITER = "||"


DEFAULT_REPLY_TEMPLATES: List[str] = [
    "Been riffing with other builders about {topic}, and this {focus} breakdown keeps delivering wins. Passing along the resource that shortcuts the work: {ref_link}",
    "Every time {topic} comes up in my circles, I point people to this {focus} playbook. Saved me weeks of spinning wheels—see for yourself: {ref_link}",
    "Your perspective on {topic} reminded me of the field notes we compiled on {focus}. I bundled everything up here if you want the cheat sheet: {ref_link}",
    "I’m deep in {topic} experiments too, and the biggest unlock so far lives in this {focus} guide. Happy to share the exact link: {ref_link}",
    "When clients ask how we tackle {topic}, I send them this {focus} walkthrough. It’s the clearest map we’ve found: {ref_link}",
    "Loved the way you framed {topic}. Here’s the {focus} resource that helped our team ship faster last sprint: {ref_link}",
    "I just helped a founder navigate {topic} yesterday using this {focus} toolkit. Figured you might vibe with it too: {ref_link}",
    "Noticed you’re dialed into {topic}; this {focus} blueprint is what moved the needle for us last quarter. Dive in here: {ref_link}",
    "My mastermind chat won’t stop talking about {topic}, and this {focus} case study is the reason why. Passing it along: {ref_link}",
    "Whenever I audit a {topic} workflow, I start with the plays outlined in this {focus} memo. Here’s the link in case it helps: {ref_link}",
]


DEFAULT_DM_TEMPLATES: List[str] = [
    "Hey {name}! Loved how you framed {focus}. I’ve got a behind-the-scenes walkthrough with screenshots that might give you a head start—mind if I share the link? {ref_link}",
    "Appreciate how deep you went on {focus}. I documented my own playbook after a bunch of trial and error. If you want it, here you go: {ref_link}",
    "You sound serious about mastering {focus}. This is the exact toolkit I’m using with clients right now—thought you’d enjoy an early look: {ref_link}",
    "Couldn’t help but notice your questions around {focus}. I recorded a mini breakdown for the team yesterday; happy to let you peek: {ref_link}",
    "Your energy around {focus} is infectious. Sharing the resource that finally clicked for me, just in case it sparks something for you too: {ref_link}",
]


ENV_DEFAULTS: Dict[str, str] = {
    "SEARCH_TOPICS": "AI automation||growth hacking||product launches",
    "USERNAME": "changeme@example.com",
    "PASSWORD": "super-secret-password",
    "REFERRAL_LINK": "https://example.com/my-referral",
    "REPLY_TEMPLATES": TEMPLATE_DELIMITER.join(DEFAULT_REPLY_TEMPLATES),
    "DM_TEMPLATES": TEMPLATE_DELIMITER.join(DEFAULT_DM_TEMPLATES),
    "RELEVANT_KEYWORDS": "AI||automation||growth||launch||community||creator economy",
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
    "X_USERNAME": "<set-your-x-username>",
    "X_PASSWORD": "<set-your-x-password>",
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


def main(args: Sequence[str] | None = None) -> Path:
    """CLI entrypoint to ensure a .env file exists.

    Args:
        args: Optional argument list. If provided, the first element should be
            the project root directory where the .env file should live. If not
            provided, the current working directory is used.

    Returns:
        The path to the ensured .env file.
    """

    argv = list(args) if args is not None else sys.argv[1:]
    root = Path(argv[0]) if argv else Path.cwd()
    if not root.exists():
        raise FileNotFoundError(f"Root path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Root path must be a directory: {root}")

    env_path = ensure_env_file(root)
    print(f"Environment file ensured at {env_path}")
    return env_path


if __name__ == "__main__":
    main()
