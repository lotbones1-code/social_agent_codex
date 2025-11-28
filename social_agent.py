#!/usr/bin/env python3
"""
Influencer Bot for X (Twitter)
Finds viral videos, generates AI captions, and posts to grow your account.
"""
from __future__ import annotations

import logging
import random
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

from bot.ai_captioner import AICaptioner
from bot.browser import BrowserManager
from bot.config_loader import load_config
from bot.engagement import EngagementModule
from bot.growth_optimizer import GrowthOptimizer
from bot.post_tracker import PostTracker
from bot.poster import VideoPoster
from bot.hybrid_downloader import HybridDownloader
from bot.trend_analyzer import TrendAnalyzer
from bot.video_validator import VideoValidator
from bot.viral_scorer import ViralScorer
from bot.viral_scraper import ViralScraper, VideoCandidate


def _slug_from_url(url: str) -> str:
    """Generate a filename from tweet URL."""
    slug = url.rstrip("/").split("/")[-1].split("?")[0]
    if not slug:
        slug = f"vid-{random.randint(1000, 9999)}"
    return slug.replace("?", "-").replace("#", "-")


def run_influencer_cycle(logger: logging.Logger) -> None:
    """Run one complete influencer cycle: scrape → download → caption → post."""

    # Load configuration
    logger.info("=" * 60)
    logger.info("Loading configuration...")
    config = load_config()

    if not config.influencer.enabled:
        logger.info("Influencer mode disabled in config. Exiting.")
        return

    # Check daily post limit
    tracker = PostTracker(config.safety.post_tracking_file, logger)
    if not tracker.can_post(config.safety.max_daily_posts):
        logger.info("Daily post limit reached. Skipping posting, will only engage.")
        skip_posting = True
    else:
        skip_posting = False

    # Start browser
    logger.info("=" * 60)
    logger.info("Starting browser session...")

    with sync_playwright() as playwright:
        manager = BrowserManager(playwright, logger)

        # Try CDP first, fall back to regular if needed
        if config.browser.use_cdp:
            session = manager.start_cdp(config.browser.cdp_url)
        else:
            session = manager.start_regular(config.browser.headless)

        if not session:
            logger.error("Failed to start browser session. Exiting cycle.")
            return

        try:
            page = session.page

            # Initialize components
            logger.info("Initializing bot components...")
            scraper = ViralScraper(page, logger)
            poster = VideoPoster(page, logger)
            engagement = EngagementModule(page, logger)
            downloader = HybridDownloader(
                page,
                Path(config.download.dir),
                logger
            )
            validator = VideoValidator(logger)

            # 🚀 GROWTH SYSTEMS
            trend_analyzer = TrendAnalyzer(page, logger)
            growth_optimizer = GrowthOptimizer(page, logger)

            # Only initialize AI systems if we have API key
            captioner = None
            viral_scorer = None
            if config.openai.api_key:
                captioner = AICaptioner(
                    api_key=config.openai.api_key,
                    model=config.openai.model,
                    max_tokens=config.openai.max_tokens,
                    temperature=config.openai.temperature,
                    logger=logger,
                )
                viral_scorer = ViralScorer(
                    openai_api_key=config.openai.api_key,
                    logger=logger,
                )
                logger.info("✅ AI systems enabled (captions + viral scoring)")
            else:
                logger.warning("No OPENAI_API_KEY found - will use fallback captions and skip viral scoring")

            # 🔥 Analyze trending topics FIRST
            logger.info("=" * 60)
            logger.info("🔥 Analyzing trending topics...")
            trending_topics = trend_analyzer.get_trending_topics(max_topics=10)
            trending_hashtags = trend_analyzer.get_trending_hashtags(max_hashtags=3)

            if trending_topics:
                logger.info(f"📈 Top trending topics:")
                for topic in trending_topics[:5]:
                    logger.info(f"  #{topic['rank']}: {topic['topic']} ({topic['category']}) - {topic['tweet_count']}")

            if trending_hashtags:
                logger.info(f"#️⃣ Trending hashtags: {', '.join(trending_hashtags)}")

            # Scrape viral videos (prioritize trending topics)
            logger.info("=" * 60)
            logger.info("Scraping viral video candidates...")

            # Use trending topics if available, fallback to config topics
            search_topics = config.influencer.topics
            if trending_topics:
                # Mix trending topics with configured topics
                trending_keywords = [t["topic"] for t in trending_topics[:3]]
                search_topics = trending_keywords + config.influencer.topics
                logger.info(f"🎯 Prioritizing trending topics: {trending_keywords}")

            candidates = scraper.find_candidates(
                topics=search_topics,
                use_explore=True,
                max_per_source=10,
            )

            if not candidates:
                logger.warning("No video candidates found. Exiting cycle.")
                return

            logger.info(f"Found {len(candidates)} total candidates")

            # Try to post videos (if not at daily limit)
            posted_count = 0
            posted_candidates: list[VideoCandidate] = []

            # Performance tracking
            metrics = {
                "candidates_found": len(candidates),
                "download_attempts": 0,
                "downloads_successful": 0,
                "validation_failures": 0,
                "post_attempts": 0,
                "posts_successful": 0,
            }

            if not skip_posting:
                logger.info("=" * 60)
                logger.info("Attempting to post videos...")

                # Shuffle and limit attempts
                attempts = random.sample(
                    candidates,
                    min(len(candidates), config.influencer.daily_post_max)
                )

                for candidate in attempts:
                    # Check if we've posted enough
                    if posted_count >= random.randint(1, 3):  # 1-3 posts per cycle
                        logger.info("Posted enough for this cycle")
                        break

                    # Check daily limit again
                    if not tracker.can_post(config.safety.max_daily_posts):
                        logger.info("Hit daily post limit during cycle")
                        break

                    logger.info("-" * 60)
                    logger.info(f"Processing: {candidate.url}")

                    # Download video
                    slug = _slug_from_url(candidate.url)
                    logger.info("Downloading video...")
                    metrics["download_attempts"] += 1
                    video_path = downloader.download_from_tweet(candidate.url, slug)

                    if not video_path:
                        logger.warning("Download failed, skipping")
                        continue

                    metrics["downloads_successful"] += 1

                    # Validate video quality
                    logger.info("Validating video quality...")
                    validation = validator.validate(video_path)

                    if not validation["is_valid"]:
                        logger.warning(f"Video validation failed: {validation.get('issues', [])}")
                        metrics["validation_failures"] += 1
                        # Cleanup invalid video
                        try:
                            video_path.unlink()
                        except:
                            pass
                        continue

                    # 🎯 Calculate viral score (skip low-potential videos)
                    if viral_scorer:
                        logger.info("Calculating viral score...")

                        # Check if video topic is trending
                        is_trending = trend_analyzer.should_post_about_topic(
                            candidate.text,
                            trending_topics
                        )

                        viral_score_data = viral_scorer.calculate_viral_score(
                            video_text=candidate.text,
                            author=candidate.author,
                            engagement_metrics=None,  # Could extract from candidate if available
                            is_trending=is_trending,
                        )

                        # Skip low-potential videos to save credit
                        if viral_score_data["recommendation"] == "skip":
                            logger.warning(f"⏭️ Skipping low viral potential (score: {viral_score_data['score']}/100)")
                            try:
                                video_path.unlink()
                            except:
                                pass
                            continue

                    # Generate caption
                    logger.info("Generating caption...")
                    if captioner:
                        caption = captioner.generate_caption(
                            video_text=candidate.text,
                            author=candidate.author,
                            topic="viral",  # Could be smarter here
                            style=config.influencer.caption_style,
                        )
                    else:
                        # Fallback caption
                        caption = f"{candidate.text[:150]}\n\n📹 via {candidate.author}"

                    # 🔥 Inject trending hashtags for maximum reach
                    if trending_hashtags and random.random() < 0.7:  # 70% chance to add hashtags
                        # Add 1-2 trending hashtags
                        num_hashtags = random.randint(1, min(2, len(trending_hashtags)))
                        selected_hashtags = random.sample(trending_hashtags, num_hashtags)

                        # Add hashtags before the credit line
                        if "📹 via" in caption:
                            parts = caption.split("📹 via")
                            hashtag_line = " " + " ".join(selected_hashtags)
                            caption = parts[0].rstrip() + hashtag_line + "\n\n📹 via" + parts[1]
                        else:
                            caption += " " + " ".join(selected_hashtags)

                        logger.info(f"✨ Added trending hashtags: {', '.join(selected_hashtags)}")

                    logger.info(f"Caption: {caption[:100]}...")

                    # Post video with retry logic
                    logger.info("Posting video...")
                    post_success = False
                    max_retries = 2
                    metrics["post_attempts"] += 1

                    for attempt in range(max_retries):
                        if attempt > 0:
                            logger.info(f"Retry attempt {attempt + 1}/{max_retries}...")
                            time.sleep(random.uniform(3, 6))

                        if poster.post_video(caption, video_path):
                            post_success = True
                            break
                        else:
                            logger.warning(f"Post attempt {attempt + 1} failed")

                    if post_success:
                        posted_count += 1
                        posted_candidates.append(candidate)
                        tracker.record_post()
                        metrics["posts_successful"] += 1
                        logger.info(f"✅ Posted successfully! ({posted_count} this cycle)")

                        # Optional: Retweet after posting
                        if config.influencer.retweet_after_post:
                            time.sleep(random.uniform(2, 4))
                            engagement.retweet(candidate.url)

                        # Cleanup video if configured
                        if config.download.cleanup_after_post:
                            try:
                                video_path.unlink()
                                logger.info("Cleaned up video file")
                            except:
                                pass
                    else:
                        logger.warning(f"Failed to post after {max_retries} attempts, skipping")

                    # Delay between posts
                    time.sleep(random.uniform(
                        config.safety.action_delay_min,
                        config.safety.action_delay_max
                    ))

                logger.info(f"Posted {posted_count} videos this cycle")

            # Engagement actions (like/retweet source tweets)
            if config.influencer.like_source_tweets and candidates:
                logger.info("=" * 60)
                logger.info("Engaging with source tweets...")
                engagement.engage_with_sources(
                    candidates=candidates,
                    like=True,
                    retweet=False,  # Be conservative with retweets
                    max_actions=5,
                )

            # 🚀 GROWTH OPTIMIZATION - Strategic engagement to gain followers
            logger.info("=" * 60)
            logger.info("🚀 Running growth optimization...")

            # Engage with trending topics to get visibility
            if trending_topics:
                top_trending = trending_topics[0]["topic"]
                logger.info(f"Engaging with top trending topic: {top_trending}")
                growth_optimizer.engage_with_viral_accounts(
                    topic=top_trending,
                    max_accounts=3,
                    actions_per_account=2,
                )

            # Engage with trending hashtags
            if trending_hashtags:
                for hashtag in trending_hashtags[:2]:  # Top 2 hashtags
                    growth_optimizer.engage_with_trending_hashtag(
                        hashtag=hashtag,
                        max_actions=5,
                    )
                    time.sleep(random.uniform(5, 10))

            logger.info("✅ Growth optimization complete")

            logger.info("=" * 60)
            logger.info(f"Cycle complete! Posted: {posted_count}")

            # Performance summary
            if metrics["download_attempts"] > 0:
                download_success_rate = (metrics["downloads_successful"] / metrics["download_attempts"]) * 100
                logger.info(f"📊 Download success rate: {download_success_rate:.1f}% ({metrics['downloads_successful']}/{metrics['download_attempts']})")

            if metrics["downloads_successful"] > 0:
                validation_success_rate = ((metrics["downloads_successful"] - metrics["validation_failures"]) / metrics["downloads_successful"]) * 100
                logger.info(f"📊 Validation pass rate: {validation_success_rate:.1f}%")

            if metrics["post_attempts"] > 0:
                post_success_rate = (metrics["posts_successful"] / metrics["post_attempts"]) * 100
                logger.info(f"📊 Post success rate: {post_success_rate:.1f}% ({metrics['posts_successful']}/{metrics['post_attempts']})")

            logger.info(f"📊 Overall efficiency: {metrics['posts_successful']}/{metrics['candidates_found']} candidates converted to posts")

        finally:
            session.close()


def run_bot() -> None:
    """Main bot loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("influencer_bot")

    logger.info("🚀 Influencer Bot Starting...")

    # Load config to get delay settings
    config = load_config()

    while True:
        try:
            run_influencer_cycle(logger)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as exc:
            logger.error(f"Cycle failed: {exc}", exc_info=True)

        # Wait before next cycle
        delay = config.safety.cycle_delay_seconds
        logger.info(f"Waiting {delay}s before next cycle...")
        time.sleep(delay)


if __name__ == "__main__":
    run_bot()
