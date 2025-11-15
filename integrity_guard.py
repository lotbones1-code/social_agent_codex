"""
Integrity Guard - Prevents the bot from running if critical features are missing.

This module performs a hard check at startup to ensure all core features,
functions, classes, and Playwright selectors still exist in social_agent.py.

If any are missing (e.g., due to accidental deletion by AI edits or merges),
the bot will refuse to start with a clear error message.
"""

from pathlib import Path
from typing import Dict, List, Tuple


# Assume this file lives next to social_agent.py in the repo root
REPO_ROOT = Path(__file__).resolve().parent
SOCIAL_AGENT_PATH = REPO_ROOT / "social_agent.py"


# Core features that MUST exist in social_agent.py
# Format: {"Human-readable name": "exact string snippet to search for"}
REQUIRED_SNIPPETS: Dict[str, str] = {
    # ========== CORE CLASSES ==========
    "BotConfig dataclass": "class BotConfig:",
    "FollowTracker class": "class FollowTracker:",
    "AnalyticsTracker class": "class AnalyticsTracker:",
    "DMTracker class": "class DMTracker:",
    "MessageRegistry class": "class MessageRegistry:",
    "VideoService class": "class VideoService:",

    # ========== AUTH & SESSION FUNCTIONS ==========
    "is_logged_in function": "def is_logged_in(",
    "automated_login function": "def automated_login(",
    "wait_for_manual_login function": "def wait_for_manual_login(",
    "ensure_logged_in function": "def ensure_logged_in(",
    "prepare_authenticated_session function": "def prepare_authenticated_session(",

    # ========== CORE ENGAGEMENT FUNCTIONS ==========
    "load_tweets function": "def load_tweets(",
    "extract_tweet_data function": "def extract_tweet_data(",
    "send_reply function": "def send_reply(",
    "like_tweet function": "def like_tweet(",
    "follow_user function": "def follow_user(",
    "unfollow_user function": "def unfollow_user(",
    "process_unfollows function": "def process_unfollows(",
    "maybe_send_dm function": "def maybe_send_dm(",
    "generate_ai_reply function": "def generate_ai_reply(",
    "generate_reply_image function": "def generate_reply_image(",

    # ========== MAIN PROCESSING FUNCTIONS ==========
    "process_tweets function": "def process_tweets(",
    "handle_topic function": "def handle_topic(",
    "run_engagement_loop function": "def run_engagement_loop(",
    "run_social_agent function": "def run_social_agent(",
    "validate_critical_features function": "def validate_critical_features(",

    # ========== CRITICAL PLAYWRIGHT SELECTORS ==========
    # Note: Using single quotes to match actual code format
    "tweet article selector": "article[data-testid='tweet']",
    "tweet text selector": "div[data-testid='tweetText']",
    "reply button selector": "button[data-testid='reply']",
    "tweetTextarea selector": "data-testid^='tweetTextarea_'",
    "tweet button selector": "data-testid='tweetButton'",
    "like button selector": "data-testid='like'",
    "follow button selector": "data-testid$='-follow'",
    "unfollow button selector": "data-testid$='-unfollow'",
    "User-Name selector": "div[data-testid='User-Name']",
    "fileInput selector": "data-testid='fileInput'",
    "sendDMFromProfile selector": "data-testid='sendDMFromProfile'",
    "dmComposerTextInput selector": "data-testid='dmComposerTextInput'",
    "dmComposerSendButton selector": "data-testid='dmComposerSendButton'",

    # ========== FILE PATHS & PERSISTENCE ==========
    "auth.json reference": "auth.json",
    "browser_session directory": "browser_session",
    "logs/replied.json registry": "logs/replied.json",
    "logs/follows.json tracking": "logs/follows.json",
    "logs/analytics.json tracking": "logs/analytics.json",
    "logs/dms.json tracking": "logs/dms.json",

    # ========== CONFIG VARIABLES ==========
    "SEARCH_TOPICS config": "SEARCH_TOPICS",
    "RELEVANT_KEYWORDS config": "RELEVANT_KEYWORDS",
    "SPAM_KEYWORDS config": "SPAM_KEYWORDS",
    "MIN_TWEET_LENGTH config": "MIN_TWEET_LENGTH",
    "MIN_KEYWORD_MATCHES config": "MIN_KEYWORD_MATCHES",
    "MAX_REPLIES_PER_TOPIC config": "MAX_REPLIES_PER_TOPIC",
    "ACTION_DELAY_MIN_SECONDS config": "ACTION_DELAY_MIN_SECONDS",
    "ACTION_DELAY_MAX_SECONDS config": "ACTION_DELAY_MAX_SECONDS",
    "LOOP_DELAY_SECONDS config": "LOOP_DELAY_SECONDS",
    "OPENAI_API_KEY config": "OPENAI_API_KEY",
    "REFERRAL_LINK config": "REFERRAL_LINK",
    "REPLY_TEMPLATES config": "REPLY_TEMPLATES",
    "DM_TEMPLATES config": "DM_TEMPLATES",
    "ENABLE_DMS config": "ENABLE_DMS",

    # ========== CRITICAL LOGIC PATTERNS ==========
    "MessageRegistry.contains deduplication": ".contains(",
    "MessageRegistry.add tracking": ".add(",
    "AnalyticsTracker.log_reply": "log_reply(",
    "AnalyticsTracker.log_follow": "log_follow(",
    "AnalyticsTracker.log_like": "log_like(",
    "FollowTracker.add_follow": "add_follow(",
    "FollowTracker.get_stale_follows": "get_stale_follows(",
    "keyword matching logic": "keyword_matches",

    # ========== AI INTEGRATION ==========
    "OpenAI API call": "https://api.openai.com/v1/chat/completions",
    "gpt-4o-mini model": "gpt-4o-mini",
}


def check_core_integrity() -> None:
    """
    Hard guard: verify that social_agent.py still contains all required core markers.

    If any are missing, raise RuntimeError and prevent the bot from starting.
    This protects against accidental deletion of features by AI edits or bad merges.

    Raises:
        RuntimeError: If social_agent.py is missing or lacks critical features
    """
    if not SOCIAL_AGENT_PATH.exists():
        raise RuntimeError(
            f"[INTEGRITY ERROR] {SOCIAL_AGENT_PATH} does not exist.\n"
            "Has the project structure changed or been deleted?"
        )

    # Read the entire social_agent.py file
    try:
        code = SOCIAL_AGENT_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise RuntimeError(
            f"[INTEGRITY ERROR] Failed to read {SOCIAL_AGENT_PATH}: {e}"
        )

    # Check for missing snippets
    missing: List[Tuple[str, str]] = []
    for name, snippet in REQUIRED_SNIPPETS.items():
        if snippet not in code:
            missing.append((name, snippet))

    if missing:
        # Build detailed error message
        details = "\n".join(
            f"  ❌ {name}\n     Missing: {snippet!r}"
            for name, snippet in missing
        )

        raise RuntimeError(
            "\n" + "="*80 + "\n"
            "[INTEGRITY ERROR] Critical features are missing from social_agent.py!\n"
            "="*80 + "\n\n"
            "This likely means an AI assistant deleted or changed critical features\n"
            "during a recent edit, merge, or 'refactor'.\n\n"
            f"Missing features ({len(missing)}):\n\n"
            f"{details}\n\n"
            "="*80 + "\n"
            "SOLUTION:\n"
            "1. Review recent git history to find when features were deleted\n"
            "2. Restore from a known-good commit (e.g., commit 3229340 or 91d38df)\n"
            "3. Use FEATURES_LIST.md to verify all features are present\n"
            "4. Never allow AI to 'simplify' or 'refactor' without explicit review\n"
            "="*80
        )

    # Success - all features present
    print(f"✅ Integrity check passed: All {len(REQUIRED_SNIPPETS)} core features present")


def get_feature_count() -> int:
    """
    Returns the number of required features being validated.
    Useful for logging and verification.
    """
    return len(REQUIRED_SNIPPETS)


if __name__ == "__main__":
    # Allow running this module directly to test integrity
    try:
        check_core_integrity()
        print(f"\n✅ SUCCESS: All {get_feature_count()} critical features are present!")
        print(f"📄 Validated file: {SOCIAL_AGENT_PATH}")
    except RuntimeError as e:
        print(str(e))
        exit(1)
