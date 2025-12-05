"""Smart reply bot that engages with tweets and promotes referral links naturally."""
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
class TweetCandidate:
    """A tweet that's a candidate for reply."""
    url: str
    author: str
    text: str
    topic: str


class ReplyBot:
    """Searches for relevant tweets and replies with smart, natural responses including referral links."""

    def __init__(self, page: Page, config: AgentConfig, logger: logging.Logger):
        self.page = page
        self.config = config
        self.logger = logger
        self.client: Optional[OpenAI] = None

        if config.openai_api_key and OpenAI:
            try:
                self.client = OpenAI(api_key=config.openai_api_key)
                self.logger.info("[ReplyBot] GPT replies enabled with model %s", config.gpt_caption_model)
            except Exception as exc:
                self.logger.warning("[ReplyBot] Could not initialize OpenAI client: %s", exc)

    def _search_tweets(self, topic: str, limit: int = 10) -> List[TweetCandidate]:
        """Search for tweets on a topic."""
        query = topic.replace(" ", "%20")
        url = f"https://x.com/search?q={query}&f=live"
        self.logger.info("[ReplyBot] Searching for tweets about '%s'", topic)

        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)
        except PlaywrightError as exc:
            self.logger.warning("[ReplyBot] Failed to load search page: %s", exc)
            return []

        # Scroll to load more tweets
        for _ in range(3):
            try:
                self.page.mouse.wheel(0, 1500)
                time.sleep(1.5)
            except PlaywrightError:
                break

        candidates: List[TweetCandidate] = []
        try:
            tweets = self.page.locator("article[data-testid='tweet']").all()
        except PlaywrightError as exc:
            self.logger.warning("[ReplyBot] Could not collect tweets: %s", exc)
            return []

        for tweet in tweets:
            if len(candidates) >= limit:
                break
            try:
                text_el = tweet.locator("div[data-testid='tweetText']")
                if text_el.count() == 0:
                    continue
                text = text_el.first.inner_text(timeout=3000)

                # Filter by length
                if len(text) < self.config.min_tweet_length:
                    continue

                # Filter spam keywords
                text_lower = text.lower()
                if any(spam in text_lower for spam in self.config.spam_keywords):
                    continue

                # Check for relevant keywords
                matches = sum(1 for kw in self.config.relevant_keywords if kw.lower() in text_lower)
                if matches < self.config.min_keyword_matches:
                    continue

                # Get tweet URL
                link = tweet.locator("a[href*='/status/']").first
                href = link.get_attribute("href") or ""
                if not href or "/status/" not in href:
                    continue

                # Get author
                author_el = tweet.locator("div[data-testid='User-Name'] a").first
                author = author_el.inner_text(timeout=3000) if author_el.count() > 0 else "someone"

                tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                candidates.append(TweetCandidate(
                    url=tweet_url,
                    author=author,
                    text=text[:500],  # Truncate for API
                    topic=topic
                ))
                self.logger.debug("[ReplyBot] Found candidate: %s", tweet_url)

            except PlaywrightError:
                continue

        self.logger.info("[ReplyBot] Found %d reply candidates for topic '%s'", len(candidates), topic)
        return candidates

    def _generate_reply(self, candidate: TweetCandidate) -> Optional[str]:
        """Generate a smart reply using GPT or templates."""
        # Extract focus from tweet (first meaningful phrase)
        focus = candidate.text.split(".")[0][:50] if "." in candidate.text else candidate.text[:50]

        # If GPT is available, use it for smart replies
        if self.client:
            return self._gpt_reply(candidate, focus)

        # Fallback to templates
        return self._template_reply(candidate, focus)

    def _gpt_reply(self, candidate: TweetCandidate, focus: str) -> Optional[str]:
        """Generate a reply using GPT."""
        prompt = f"""You are a successful tech entrepreneur and growth expert who genuinely helps people on X/Twitter.

Your goal: Write a reply that sounds like a real person sharing genuine value, NOT a bot or marketer.

PERSONALITY:
- Confident but humble
- Shares from real experience
- Gives specific actionable insights
- Builds rapport before promoting anything

REPLY REQUIREMENTS:
1. Start by acknowledging their insight or asking a thoughtful question
2. Share a relevant personal experience or tip (1 sentence)
3. If naturally fitting, mention you documented your approach here: {self.config.referral_link}
4. Keep it under 240 characters
5. Sound like a real person texting a colleague
6. NO hashtags, NO excessive punctuation, minimal emojis

BAD EXAMPLE: "Great post! Check out my resource: [link]"
GOOD EXAMPLE: "This mirrors what we found scaling our team - the async standups were game-changing. Wrote up our playbook if useful: [link]"

Tweet you're replying to:
@{candidate.author}: {candidate.text}

Topic context: {candidate.topic}

Write ONLY the reply, no quotes or explanation:"""

        try:
            response = self.client.chat.completions.create(
                model=self.config.gpt_caption_model,
                messages=[
                    {"role": "system", "content": "You are a helpful tech professional who gives genuine, valuable replies on Twitter. Never sound like a bot or spammer."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=120,
                temperature=0.85,
            )
            content = response.choices[0].message.content if response.choices else None
            if content:
                reply = content.strip().strip('"').strip("'")
                # Clean up any accidental quotes or formatting
                reply = reply.replace('"""', '').replace("'''", '')
                self.logger.info("[ReplyBot] GPT generated reply: %s", reply[:100])
                return reply
        except Exception as exc:
            self.logger.warning("[ReplyBot] GPT reply failed: %s", exc)

        return self._template_reply(candidate, focus)

    def _template_reply(self, candidate: TweetCandidate, focus: str) -> Optional[str]:
        """Generate a reply using templates."""
        if not self.config.reply_templates:
            self.logger.warning("[ReplyBot] No reply templates configured")
            return None

        template = random.choice(self.config.reply_templates)
        try:
            reply = template.format(
                topic=candidate.topic,
                focus=focus,
                ref_link=self.config.referral_link
            )
            return reply
        except KeyError as e:
            self.logger.warning("[ReplyBot] Template missing placeholder: %s", e)
            return None

    def _post_reply(self, candidate: TweetCandidate, reply_text: str) -> bool:
        """Navigate to tweet and post a reply."""
        try:
            self.logger.info("[ReplyBot] Navigating to tweet: %s", candidate.url)
            self.page.goto(candidate.url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(2)

            # Click the reply button
            reply_btn = self.page.locator("div[data-testid='reply']").first
            if not reply_btn.is_visible(timeout=5000):
                self.logger.warning("[ReplyBot] Reply button not visible")
                return False

            reply_btn.click()
            time.sleep(1)

            # Find and fill the composer
            composer = self.page.locator("div[data-testid='tweetTextarea_0']").first
            if not composer.is_visible(timeout=5000):
                self.logger.warning("[ReplyBot] Composer not visible")
                return False

            composer.fill(reply_text)
            time.sleep(0.5)

            # Click send
            send_btn = self.page.locator("button[data-testid='tweetButtonInline']").first
            if not send_btn.is_visible(timeout=3000):
                # Try alternative selector
                send_btn = self.page.locator("div[data-testid='tweetButtonInline']").first

            send_btn.click()
            time.sleep(2)

            self.logger.info("[ReplyBot] Successfully replied to %s", candidate.url)
            return True

        except PlaywrightError as exc:
            self.logger.warning("[ReplyBot] Failed to post reply: %s", exc)
            return False

    def _search_influencer_tweets(self, limit: int = 15) -> List[TweetCandidate]:
        """Search for high-engagement tweets from influencers in the niche."""
        # Search for popular tweets with high engagement
        searches = [
            "AI automation min_faves:100",
            "growth hacking min_faves:50",
            "startup tips min_faves:100",
            "product launch min_faves:50",
            "SaaS growth min_faves:50",
        ]

        all_candidates: List[TweetCandidate] = []

        for search_query in searches:
            if len(all_candidates) >= limit:
                break

            query = search_query.replace(" ", "%20")
            url = f"https://x.com/search?q={query}&f=live"
            self.logger.info("[ReplyBot] Searching influencer tweets: '%s'", search_query)

            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(2)

                # Scroll to load tweets
                for _ in range(2):
                    self.page.mouse.wheel(0, 1000)
                    time.sleep(1)

                tweets = self.page.locator("article[data-testid='tweet']").all()

                for tweet in tweets[:5]:  # Take top 5 from each search
                    try:
                        text_el = tweet.locator("div[data-testid='tweetText']")
                        if text_el.count() == 0:
                            continue
                        text = text_el.first.inner_text(timeout=3000)

                        # Skip spam
                        text_lower = text.lower()
                        if any(spam in text_lower for spam in self.config.spam_keywords):
                            continue

                        link = tweet.locator("a[href*='/status/']").first
                        href = link.get_attribute("href") or ""
                        if not href or "/status/" not in href:
                            continue

                        author_el = tweet.locator("div[data-testid='User-Name'] a").first
                        author = author_el.inner_text(timeout=3000) if author_el.count() > 0 else "someone"

                        tweet_url = f"https://x.com{href}" if href.startswith("/") else href
                        all_candidates.append(TweetCandidate(
                            url=tweet_url,
                            author=author,
                            text=text[:500],
                            topic=search_query.split(" min_faves")[0]
                        ))
                    except PlaywrightError:
                        continue

            except PlaywrightError as exc:
                self.logger.warning("[ReplyBot] Failed searching influencers: %s", exc)
                continue

        self.logger.info("[ReplyBot] Found %d influencer tweets to engage with", len(all_candidates))
        return all_candidates

    def _post_original_tweet(self) -> bool:
        """Post an original tweet to build account credibility."""
        if not self.client:
            return False

        prompt = f"""You are a tech entrepreneur sharing a quick insight on X/Twitter.

Write a short, valuable tweet (under 240 chars) about ONE of these topics:
- AI automation tip
- Growth hacking insight
- Productivity hack
- Startup lesson learned

Make it:
- Specific and actionable
- Sound like genuine experience
- Include a subtle CTA to check your resource: {self.config.referral_link}
- NO hashtags unless 1-2 very relevant ones

Example style:
"Biggest unlock this quarter: automating our onboarding emails saved 12hrs/week. Documented the exact flow here: [link]"

Write ONLY the tweet:"""

        try:
            response = self.client.chat.completions.create(
                model=self.config.gpt_caption_model,
                messages=[
                    {"role": "system", "content": "You write authentic, valuable tweets that build credibility."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=100,
                temperature=0.9,
            )
            content = response.choices[0].message.content if response.choices else None
            if not content:
                return False

            tweet_text = content.strip().strip('"').strip("'")

            # Navigate to compose
            self.page.goto("https://x.com/compose/post", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)

            composer = self.page.locator("div[data-testid='tweetTextarea_0']").first
            if not composer.is_visible(timeout=5000):
                return False

            composer.fill(tweet_text)
            time.sleep(1)

            # Post
            post_btn = self.page.locator("button[data-testid='tweetButton']").first
            if post_btn.is_visible(timeout=3000):
                post_btn.click()
                time.sleep(2)
                self.logger.info("[ReplyBot] Posted original tweet: %s", tweet_text[:80])
                return True

        except Exception as exc:
            self.logger.warning("[ReplyBot] Failed to post original tweet: %s", exc)

        return False

    def run_reply_cycle(self) -> int:
        """Run a cycle of finding tweets and replying."""
        if not self.config.enable_replies:
            self.logger.info("[ReplyBot] Replies disabled in config")
            return 0

        if not self.config.referral_link:
            self.logger.warning("[ReplyBot] No REFERRAL_LINK configured - skipping replies")
            return 0

        total_replies = 0

        # First, try to post an original tweet to build credibility
        if self.client and random.random() < 0.3:  # 30% chance per cycle
            self.logger.info("[ReplyBot] Posting original content...")
            if self._post_original_tweet():
                total_replies += 1
                time.sleep(random.uniform(5, 10))

        # Search for influencer/high-engagement tweets first
        self.logger.info("[ReplyBot] Searching for influencer tweets...")
        influencer_candidates = self._search_influencer_tweets(limit=10)

        # Also search regular topic tweets
        topics = self.config.search_topics
        self.logger.info("[ReplyBot] Starting reply cycle for %d topics", len(topics))

        all_candidates = list(influencer_candidates)

        for topic in topics:
            candidates = self._search_tweets(topic, limit=self.config.max_replies_per_topic * 2)
            all_candidates.extend(candidates)

        # Shuffle and dedupe
        random.shuffle(all_candidates)
        seen_urls = set()
        unique_candidates = []
        for c in all_candidates:
            if c.url not in seen_urls:
                seen_urls.add(c.url)
                unique_candidates.append(c)

        self.logger.info("[ReplyBot] Total unique candidates: %d", len(unique_candidates))

        max_total_replies = self.config.max_replies_per_topic * len(topics)

        for candidate in unique_candidates:
            if total_replies >= max_total_replies:
                break

            reply_text = self._generate_reply(candidate)
            if not reply_text:
                continue

            if self._post_reply(candidate, reply_text):
                total_replies += 1

                # Random delay between replies
                delay = random.uniform(
                    self.config.action_delay_min,
                    self.config.action_delay_max
                )
                self.logger.info("[ReplyBot] Waiting %.1fs before next action", delay)
                time.sleep(delay)

        self.logger.info("[ReplyBot] Cycle complete: %d replies/posts sent", total_replies)
        return total_replies


__all__ = ["ReplyBot", "TweetCandidate"]
