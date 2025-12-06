"""DM bot that reaches out to engaged users with personalized messages."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import List, Optional

from playwright.sync_api import Error as PlaywrightError, Page

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from .config import AgentConfig


@dataclass
class DMCandidate:
    """A user who might be interested in a DM."""
    username: str
    display_name: str
    tweet_text: str
    topic: str
    interest_score: float


class DMBot:
    """Sends personalized DMs to users who show interest in relevant topics."""

    def __init__(self, page: Page, config: AgentConfig, logger: logging.Logger):
        self.page = page
        self.config = config
        self.logger = logger
        self.client: Optional[OpenAI] = None

        if config.openai_api_key and OpenAI:
            try:
                self.client = OpenAI(api_key=config.openai_api_key)
                self.logger.info("[DMBot] GPT DMs enabled with model %s", config.gpt_caption_model)
            except Exception as exc:
                self.logger.warning("[DMBot] Could not initialize OpenAI client: %s", exc)

    def _calculate_interest_score(self, tweet_text: str) -> float:
        """Calculate how interested a user might be based on their tweet."""
        score = 0.0
        text_lower = tweet_text.lower()

        # Check for relevant keywords
        for keyword in self.config.relevant_keywords:
            if keyword.lower() in text_lower:
                score += 1.0

        # Check for questions (indicates seeking help)
        if "?" in tweet_text:
            score += self.config.dm_question_weight

        # Longer tweets indicate more engagement
        if len(tweet_text) > self.config.dm_trigger_length:
            score += 0.5

        # Check for problem/help language
        help_indicators = ["how do", "how can", "anyone know", "looking for", "need help", "struggling"]
        for indicator in help_indicators:
            if indicator in text_lower:
                score += 0.75

        return score

    def _find_dm_candidates(self, limit: int = 10) -> List[DMCandidate]:
        """Search for users who might be interested in the referral."""
        candidates: List[DMCandidate] = []

        for topic in self.config.search_topics[:3]:  # Limit to 3 topics
            query = topic.replace(" ", "%20")
            url = f"https://x.com/search?q={query}&f=live"

            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)

                # Scroll to load tweets
                for _ in range(2):
                    self.page.mouse.wheel(0, 1000)
                    time.sleep(1)

                tweets = self.page.locator("article[data-testid='tweet']").all()

                for tweet in tweets[:10]:
                    if len(candidates) >= limit:
                        break

                    try:
                        text_el = tweet.locator("div[data-testid='tweetText']")
                        if text_el.count() == 0:
                            continue
                        text = text_el.first.inner_text(timeout=3000)

                        # Skip spam
                        text_lower = text.lower()
                        if any(spam in text_lower for spam in self.config.spam_keywords):
                            continue

                        # Calculate interest score
                        score = self._calculate_interest_score(text)
                        if score < self.config.dm_interest_threshold:
                            continue

                        # Get username
                        author_el = tweet.locator("div[data-testid='User-Name'] a").first
                        href = author_el.get_attribute("href") or ""
                        username = href.strip("/").split("/")[-1] if href else ""

                        display_el = tweet.locator("div[data-testid='User-Name'] span").first
                        display_name = display_el.inner_text(timeout=2000) if display_el.count() > 0 else username

                        if username and username not in [c.username for c in candidates]:
                            candidates.append(DMCandidate(
                                username=username,
                                display_name=display_name,
                                tweet_text=text[:300],
                                topic=topic,
                                interest_score=score
                            ))

                    except PlaywrightError:
                        continue

            except PlaywrightError as exc:
                self.logger.warning("[DMBot] Failed to search for candidates: %s", exc)
                continue

        self.logger.info("[DMBot] Found %d DM candidates", len(candidates))
        return candidates

    def _generate_dm(self, candidate: DMCandidate) -> Optional[str]:
        """Generate a personalized DM using GPT or templates."""
        focus = candidate.tweet_text.split(".")[0][:50] if "." in candidate.tweet_text else candidate.tweet_text[:50]

        if self.client:
            return self._gpt_dm(candidate, focus)

        return self._template_dm(candidate, focus)

    def _gpt_dm(self, candidate: DMCandidate, focus: str) -> Optional[str]:
        """Generate a DM using GPT."""
        prompt = f"""You are a helpful tech professional reaching out via Twitter DM.

Write a short, friendly DM that:
1. References something specific from their tweet
2. Offers genuine value or insight
3. Naturally mentions a resource that could help: {self.config.referral_link}
4. Keeps it under 200 characters
5. Sounds like a real person, not a marketer

Their tweet: {candidate.tweet_text[:200]}
Topic: {candidate.topic}
Their name: {candidate.display_name}

Write ONLY the DM text:"""

        try:
            response = self.client.chat.completions.create(
                model=self.config.gpt_caption_model,
                messages=[
                    {"role": "system", "content": "You write friendly, helpful DMs that feel personal and genuine."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=80,
                temperature=0.85,
            )
            content = response.choices[0].message.content if response.choices else None
            if content:
                dm = content.strip().strip('"').strip("'")
                self.logger.info("[DMBot] GPT generated DM: %s", dm[:80])
                return dm
        except Exception as exc:
            self.logger.warning("[DMBot] GPT DM failed: %s", exc)

        return self._template_dm(candidate, focus)

    def _template_dm(self, candidate: DMCandidate, focus: str) -> Optional[str]:
        """Generate a DM using templates."""
        if not self.config.dm_templates:
            self.logger.warning("[DMBot] No DM templates configured")
            return None

        template = random.choice(self.config.dm_templates)
        try:
            dm = template.format(
                name=candidate.display_name.split()[0] if candidate.display_name else "there",
                topic=candidate.topic,
                focus=focus,
                ref_link=self.config.referral_link
            )
            return dm
        except KeyError as e:
            self.logger.warning("[DMBot] Template missing placeholder: %s", e)
            return None

    def _send_dm(self, candidate: DMCandidate, message: str) -> bool:
        """Navigate to user's profile and send a DM."""
        try:
            # Go to user's profile
            profile_url = f"https://x.com/{candidate.username}"
            self.page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            # Look for Message button
            msg_btn = self.page.locator("div[data-testid='sendDMFromProfile'], button[aria-label*='Message']").first
            if not msg_btn.is_visible(timeout=5000):
                self.logger.debug("[DMBot] Message button not available for %s", candidate.username)
                return False

            msg_btn.click()
            time.sleep(2)

            # Find and fill the DM composer
            composer = self.page.locator("div[data-testid='dmComposerTextInput'], div[role='textbox']").first
            if not composer.is_visible(timeout=5000):
                self.logger.warning("[DMBot] DM composer not visible")
                return False

            composer.fill(message)
            time.sleep(0.5)

            # Send the DM
            send_btn = self.page.locator("button[data-testid='dmComposerSendButton'], div[aria-label='Send']").first
            if send_btn.is_visible(timeout=3000):
                send_btn.click()
                time.sleep(2)
                self.logger.info("[DMBot] Sent DM to @%s", candidate.username)
                return True

        except PlaywrightError as exc:
            self.logger.warning("[DMBot] Failed to send DM to %s: %s", candidate.username, exc)

        return False

    def run_dm_cycle(self, max_dms: int = 5) -> int:
        """Run a cycle of finding users and sending DMs."""
        if not self.config.enable_dms:
            self.logger.info("[DMBot] DMs disabled in config")
            return 0

        if not self.config.referral_link:
            self.logger.warning("[DMBot] No REFERRAL_LINK configured - skipping DMs")
            return 0

        self.logger.info("[DMBot] Starting DM cycle...")
        candidates = self._find_dm_candidates(limit=max_dms * 2)

        # Sort by interest score
        candidates.sort(key=lambda c: c.interest_score, reverse=True)

        dms_sent = 0
        for candidate in candidates:
            if dms_sent >= max_dms:
                break

            dm_text = self._generate_dm(candidate)
            if not dm_text:
                continue

            if self._send_dm(candidate, dm_text):
                dms_sent += 1
                # Longer delay between DMs to avoid rate limits
                delay = random.uniform(30, 60)
                self.logger.info("[DMBot] Waiting %.1fs before next DM", delay)
                time.sleep(delay)

        self.logger.info("[DMBot] Cycle complete: %d DMs sent", dms_sent)
        return dms_sent


__all__ = ["DMBot", "DMCandidate"]
