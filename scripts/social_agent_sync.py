"""Lightweight synchronous automation script for X (Twitter).

This script mirrors the quick-start example shared in the original prompt but
adjusts a few behaviours so it plays nicely with the rest of the repository:

* It relies on the existing ``env.sample`` file when bootstrapping ``.env``.
* Browser contexts are created from the launched browser (fixing a subtle bug in
  the original snippet).
* Logging is used throughout, keeping parity with the production agent.

The script intentionally keeps the control-flow simple so that developers can
quickly prototype interactions or debug credentials without going through the
full asynchronous pipeline that powers ``social_agent.py``.
"""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

# Configure logging (mirrors the style from the shared snippet)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
SAMPLE_ENV_PATH = ROOT_DIR / "env.sample"
AUTH_STATE_PATH = ROOT_DIR / "auth.json"


def _ensure_env_file() -> None:
    """Create a ``.env`` file if one does not already exist.

    The original snippet wrote out placeholder credentials inline. Re-using the
    repository's ``env.sample`` keeps everything consistent while still
    providing helpful defaults for first-time users.
    """

    if ENV_PATH.exists():
        return

    if SAMPLE_ENV_PATH.exists():
        ENV_PATH.write_text(SAMPLE_ENV_PATH.read_text())
        logging.info(".env file created from env.sample. Update it with real credentials.")
    else:
        ENV_PATH.write_text(
            "\n".join(
                [
                    "X_USERNAME=your_username",
                    "X_PASSWORD=your_password",
                    "SEARCH_TOPICS=topic1,topic2",
                    "SPAM_KEYWORDS=spam1,spam2",
                    "DM_TEMPLATES=Hello! How can I help?|Thank you for reaching out!",
                ]
            )
            + "\n"
        )
        logging.info(".env file created with placeholder values. Update it with real credentials.")


def _load_list_env(var_name: str, *, delimiter: str = ",", secondary_delimiter: str = "|") -> list[str]:
    """Load a list from the environment, handling multiple delimiter styles."""

    raw = os.getenv(var_name, "")
    if not raw:
        return []

    parts: list[str] = []
    for chunk in raw.split(secondary_delimiter):
        for piece in chunk.split(delimiter):
            stripped = piece.strip()
            if stripped:
                parts.append(stripped)
    return parts


def contains_spam(text: str, spam_keywords: Iterable[str]) -> bool:
    """Return ``True`` if any spam keyword is present in ``text``."""

    lowered = text.lower()
    return any(keyword in lowered for keyword in spam_keywords)


def _resolve_credentials() -> tuple[str, str]:
    username = os.getenv("X_USERNAME", "").strip()
    password = os.getenv("X_PASSWORD", "").strip()
    if not username or not password:
        logging.error("X_USERNAME or X_PASSWORD not set in .env or environment. Exiting.")
        sys.exit(1)
    return username, password


def _handle_login(context, page) -> None:  # pragma: no cover - UI interaction
    """Handle the initial login flow and persist the storage state."""

    logging.info("No existing login session. Please complete login manually in the opened browser.")
    page.goto("https://twitter.com/login", wait_until="domcontentloaded")
    try:
        page.wait_for_url("https://twitter.com/home", timeout=300_000)
    except (PlaywrightTimeout, PlaywrightError):
        logging.warning("Login wait timed out or failed. Continuing without saving session.")
    try:
        context.storage_state(path=str(AUTH_STATE_PATH))
        logging.info("Authentication state saved for future runs.")
    except PlaywrightError as exc:
        logging.warning("Could not save auth state: %s", exc)


def _search_topics(page, topics: Iterable[str], spam_keywords: list[str], *, delay_seconds: int = 3) -> None:
    """Perform a basic search for each topic and like a handful of tweets."""

    for topic in topics:
        topic = topic.strip()
        if not topic:
            continue
        encoded_topic = topic.replace(" ", "%20")
        search_url = f"https://twitter.com/search?q={encoded_topic}&f=live"
        try:
            logging.info("Searching for topic: %s", topic)
            page.goto(search_url, wait_until="networkidle")
            time.sleep(delay_seconds)
            tweets = page.query_selector_all("article")
            for index, tweet in enumerate(tweets[:3]):
                try:
                    tweet_text = tweet.inner_text()
                except PlaywrightError:
                    continue
                if contains_spam(tweet_text, spam_keywords):
                    logging.info("Skipped tweet containing spam.")
                    continue
                try:
                    like_button = tweet.query_selector("[data-testid='like']")
                    if like_button:
                        like_button.click()
                        logging.info("Liked tweet #%s for topic '%s'.", index + 1, topic)
                        time.sleep(2)
                except PlaywrightError:
                    continue
        except PlaywrightError as exc:
            logging.warning("Search for topic '%s' failed: %s", topic, exc)


def _handle_dms(page, spam_keywords: list[str], templates: list[str]) -> None:
    """Iterate over direct messages and send lightweight replies."""

    if not templates:
        logging.info("No DM templates configured; skipping DM handling.")
        return

    try:
        logging.info("Checking direct messages (DMs)...")
        page.goto("https://twitter.com/messages", wait_until="networkidle")
        time.sleep(3)
        threads = page.query_selector_all("[data-testid='conversation']")
        for thread in threads:
            try:
                thread.click()
                time.sleep(2)
                messages = page.query_selector_all("[data-testid='messageText']")
                if not messages:
                    page.go_back()
                    continue
                last_message = messages[-1].inner_text()
                logging.info("Last DM text: %s", last_message)
                if contains_spam(last_message, spam_keywords):
                    logging.info("Last DM contains spam keywords. Skipping reply.")
                else:
                    reply_text = random.choice(templates)
                    input_box = page.query_selector("[data-testid='conversationTextInput']")
                    if input_box:
                        input_box.focus()
                        input_box.type(reply_text)
                        input_box.press("Enter")
                        logging.info("Replied to DM with: %s", reply_text)
                page.go_back()
                time.sleep(1)
            except PlaywrightError as exc:
                logging.warning("Failed to handle a DM thread: %s", exc)
                page.go_back()
    except PlaywrightError as exc:
        logging.warning("Error while handling DMs: %s", exc)


def run_social_agent() -> None:  # pragma: no cover - relies on external browser
    _ensure_env_file()
    load_dotenv(dotenv_path=ENV_PATH)
    _resolve_credentials()

    search_topics = _load_list_env("SEARCH_TOPICS")
    spam_keywords = [kw.lower() for kw in _load_list_env("SPAM_KEYWORDS")]
    dm_templates = _load_list_env("DM_TEMPLATES", delimiter="|", secondary_delimiter=",")

    logging.info("Starting social_agent_sync with topics: %s", search_topics)

    try:
        with sync_playwright() as playwright:
            first_run = not AUTH_STATE_PATH.exists()

            browser = playwright.chromium.connect_over_cdp("http://localhost:9222")
            try:
                context = browser.contexts[0]
            except IndexError:
                logging.error("No browser contexts available from the connected Chrome instance.")
                return
            page = context.new_page()

            if first_run:
                _handle_login(context, page)
            else:
                logging.info("Using saved login session from auth.json.")
                page.goto("https://twitter.com/home", wait_until="networkidle")

            _search_topics(page, search_topics, spam_keywords)
            _handle_dms(page, spam_keywords, dm_templates)

            context.close()
            browser.close()
    except PlaywrightError as exc:
        logging.error("Playwright encountered an error: %s", exc)
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.error("An unexpected error occurred: %s", exc)


if __name__ == "__main__":  # pragma: no cover - script entry point
    run_social_agent()
