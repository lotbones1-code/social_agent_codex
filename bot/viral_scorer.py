"""Calculate viral potential of videos before posting."""
from __future__ import annotations

import logging
from typing import Optional

from openai import OpenAI


class ViralScorer:
    """Calculate viral score for videos to only post high-potential content."""

    def __init__(self, openai_api_key: str, logger: logging.Logger):
        self.client = OpenAI(api_key=openai_api_key)
        self.logger = logger

    def calculate_viral_score(
        self,
        video_text: str,
        author: str,
        engagement_metrics: Optional[dict] = None,
        is_trending: bool = False,
    ) -> dict:
        """
        Calculate viral score (0-100) for a video.

        Args:
            video_text: Original tweet text
            author: Tweet author handle
            engagement_metrics: Dict with likes, retweets, views counts
            is_trending: Whether the video topic is currently trending

        Returns:
            {
                "score": 85,  # 0-100
                "confidence": "high",  # low, medium, high
                "reasons": ["High engagement", "Trending topic", ...],
                "recommendation": "post"  # post, skip, review
            }
        """
        score = 0
        reasons = []

        # Base engagement score (if metrics provided)
        if engagement_metrics:
            likes = engagement_metrics.get("likes", 0)
            retweets = engagement_metrics.get("retweets", 0)
            views = engagement_metrics.get("views", 0)

            # High engagement = viral potential
            if likes > 10000:
                score += 25
                reasons.append(f"High likes ({likes:,})")
            elif likes > 5000:
                score += 15
                reasons.append(f"Good likes ({likes:,})")
            elif likes > 1000:
                score += 10

            if retweets > 2000:
                score += 20
                reasons.append(f"High retweets ({retweets:,})")
            elif retweets > 500:
                score += 10

            if views > 100000:
                score += 15
                reasons.append(f"High views ({views:,})")
            elif views > 50000:
                score += 10

        # Trending topic bonus
        if is_trending:
            score += 20
            reasons.append("🔥 Trending topic RIGHT NOW")

        # AI content quality analysis
        try:
            ai_score = self._analyze_content_quality(video_text, author)
            score += ai_score
            if ai_score >= 15:
                reasons.append("AI: High quality content")
            elif ai_score >= 10:
                reasons.append("AI: Good content quality")
        except Exception as exc:
            self.logger.debug(f"AI analysis failed: {exc}")

        # Cap at 100
        score = min(score, 100)

        # Determine confidence and recommendation
        if score >= 70:
            confidence = "high"
            recommendation = "post"
            reasons.append("✅ STRONG viral potential")
        elif score >= 50:
            confidence = "medium"
            recommendation = "post"
            reasons.append("✅ Good viral potential")
        elif score >= 30:
            confidence = "low"
            recommendation = "review"
            reasons.append("⚠️ Moderate potential")
        else:
            confidence = "low"
            recommendation = "skip"
            reasons.append("❌ Low viral potential")

        result = {
            "score": score,
            "confidence": confidence,
            "reasons": reasons,
            "recommendation": recommendation,
        }

        self.logger.info(f"📊 Viral score: {score}/100 ({confidence}) - {recommendation.upper()}")
        for reason in reasons:
            self.logger.debug(f"  - {reason}")

        return result

    def _analyze_content_quality(self, video_text: str, author: str) -> int:
        """
        Use AI to analyze content quality and viral potential.

        Returns:
            Score contribution (0-20 points)
        """
        try:
            prompt = f"""Analyze this viral video content and rate its viral potential on X (Twitter).

Content: "{video_text[:500]}"
Author: @{author}

Rate the viral potential considering:
1. Emotional impact (shocking, funny, inspiring, controversial)
2. Shareability (would people repost this?)
3. Timing relevance (is this timely/newsworthy?)
4. Broad appeal (universal vs niche)
5. Hook quality (does it grab attention?)

Respond with ONLY a number from 0-20 representing the viral potential points.
Higher = more viral potential."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a viral content analyst expert who predicts what will go viral on X/Twitter."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0.3,
            )

            score_text = response.choices[0].message.content.strip()
            # Extract number from response
            import re
            match = re.search(r'\d+', score_text)
            if match:
                ai_score = int(match.group())
                # Ensure in valid range
                ai_score = max(0, min(20, ai_score))
                self.logger.debug(f"AI content quality score: {ai_score}/20")
                return ai_score
            else:
                return 10  # Default middle score

        except Exception as exc:
            self.logger.debug(f"AI scoring failed: {exc}")
            return 10  # Default to moderate score


__all__ = ["ViralScorer"]
