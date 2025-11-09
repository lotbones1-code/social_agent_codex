"""Environment configuration utilities for the social agent bot."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List

from dotenv import dotenv_values


TEMPLATE_DELIMITER = "||"


DEFAULT_REPLY_TEMPLATES: List[str] = [
    "Been coaching a handful of builders on {focus} lately, and every single one thanked me for this playbook—dropping it here so you can try it too: {ref_link}",
    "When I hit a wall with {focus}, this resource bailed me out fast. If you want the shortcut I wish I had sooner, it’s right here: {ref_link}",
    "I keep hearing friends rave about how this {focus} framework 3×'d their results—count me in that crew now. Passing you the same link: {ref_link}",
    "Your take on {focus} reminded me of a case study we just ran. I wrote up the steps if you want to skim what’s working for us: {ref_link}",
    "Not to be dramatic, but every time I share this {focus} breakdown people DM me the next day with wins. Grab it while it’s hot: {ref_link}",
    "This is the exact {focus} starter kit we hand over to clients when they sign with us. Figured you’d vibe with it too: {ref_link}",
    "I owe two big wins this quarter to the walkthrough in here—if {focus} is on your radar, you’ll want to bookmark this: {ref_link}",
    "Saw you dialed in on {focus}; I’m running the same experiments and documenting everything. My notes & tools are bundled here: {ref_link}",
    "Hate to fuel FOMO, but our private Slack won’t shut up about the leap they got from this {focus} blueprint. Jump in before everyone else does: {ref_link}",
    "Every investor I respect keeps asking for this {focus} resource, so I finally made it public. Let me know what you test first: {ref_link}",
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
    parts: Iterable[str]
    if TEMPLATE_DELIMITER in raw:
        parts = raw.split(TEMPLATE_DELIMITER)
    else:
        parts = raw.splitlines()
    return [part.strip() for part in parts if part.strip()]
