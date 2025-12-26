import json
import os
import re
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

class PolymarketIntelligence:
    """Generate high-conviction contrarian takes on politics Polymarkets."""
    
    def __init__(self, analytics_log="performance_log.json"):
        self.analytics_log = analytics_log
        self.politics_keywords = [
            "trump", "election", "2026", "2024", "congress", "senate",
            "policy", "inflation", "fed", "rate", "president", "democrat",
            "republican", "conviction", "trial", "indictment", "senate race",
            "midterm", "healthcare", "nato", "ukraine", "china", "taiwan",
            "nuclear", "debt ceiling", "government shutdown", "fbi"
        ]
    
    def is_politics_market(self, market_name):
        """True if market_name contains politics keywords."""
        if not market_name:
            return False
        market_lower = market_name.lower()
        return any(kw in market_lower for kw in self.politics_keywords)
    
    def has_betting_substance(self, tweet_text):
        """
        Check if tweet contains actual betting/prediction content worth replying to.
        
        Returns True if tweet mentions:
        - Specific odds, probabilities, or percentages (e.g., "83%", "50/50", "2:1 odds")
        - Predictions or forecasts (e.g., "will win", "predicted to", "forecast")
        - Market data (e.g., "volume", "price", "trading at", "market shows")
        - Betting discussion (e.g., "bet on", "wager", "taking the over", "buying/selling")
        - Specific events with dates or contexts (e.g., "2026 election", "trial outcome")
        
        Returns False if tweet is just:
        - Generic mentions of "Polymarket" without substance
        - Just images with minimal text
        - General discussion without specific predictions/odds
        """
        if not tweet_text:
            return False
        
        tweet_lower = tweet_text.lower()
        
        # Check for specific odds/probabilities (e.g., "83%", "50%", "2:1", "5/1", "0.7")
        odds_patterns = [
            r'\d+%',  # Percentages like "83%", "50%"
            r'\d+/\d+',  # Fractional odds like "5/1", "2/1"
            r'\d+:\d+',  # Decimal odds like "2:1", "3:2"
            r'\d+\.\d+',  # Decimal probabilities like "0.7", "0.5"
            r'\b(odds?|probability|prob|chance|likelihood)\b.*\d+',  # "odds of 83", "50% chance"
            r'\b\d+.*(percent|%)',  # "83 percent", "50%"
        ]
        
        for pattern in odds_patterns:
            if re.search(pattern, tweet_lower):
                return True
        
        # Check for prediction/forecast language
        prediction_keywords = [
            "will win", "will lose", "predicted to", "forecast", "forecasting",
            "prediction", "predicting", "expected to", "likely to", "unlikely to",
            "market predicts", "traders think", "consensus is", "betting on",
            "taking the", "buying", "selling", "long", "short", "wager", "bet on",
            "taking", "fading", "fade"
        ]
        
        for keyword in prediction_keywords:
            if keyword in tweet_lower:
                return True
        
        # Check for market data keywords
        market_data_keywords = [
            "volume", "trading at", "market shows", "price", "implied",
            "market odds", "current odds", "market price", "betting odds",
            "market is pricing", "priced at", "trading", "market consensus"
        ]
        
        for keyword in market_data_keywords:
            if keyword in tweet_lower:
                return True
        
        # Check for specific events with context (has year, date, or specific event)
        # This catches things like "2026 election", "trial outcome", "next week"
        event_patterns = [
            r'\b(20\d{2})\b',  # Years like 2024, 2026
            r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d+',  # Dates
            r'\b(election|trial|vote|primary|caucus|debate|announcement|verdict)\b',
        ]
        
        # Only count events if they're paired with prediction language
        has_event = any(re.search(pattern, tweet_lower) for pattern in event_patterns)
        if has_event and any(kw in tweet_lower for kw in ["will", "odds", "bet", "predict", "market"]):
            return True
        
        # If tweet is very short and just says "Polymarket" or similar, skip it
        if len(tweet_text.split()) <= 5 and "polymarket" in tweet_lower:
            return False
        
        return False
    
    def fetch_market_context(self, market_name, market_odds="50%", volume_24h="$100k", 
                            resolution_date="2026-01-01", sentiment="neutral"):
        """Package market data for ChatGPT analysis."""
        try:
            implied = float(market_odds.strip('%')) if '%' in str(market_odds) else float(market_odds) * 100
        except:
            implied = 50.0
        
        return {
            "market_name": market_name,
            "current_odds": market_odds,
            "implied_probability": round(implied, 1),
            "volume_24h": volume_24h,
            "resolution_date": resolution_date,
            "sentiment": sentiment,
            "timestamp": datetime.now().isoformat()
        }
    
    def is_thesis_high_quality(self, thesis_dict):
        """
        Check if thesis meets quality standards.
        Returns: (is_high_quality: bool, failure_reason: str or None)
        
        Checks:
        - No dismissive/robotic keywords (obviously, clearly, pay attention, wake up, etc.)
        - Contains at least 1 specific detail: number, date, name, or percentage
        - Has reasoning/explanation, not just disagreement
        - Confidence >= 60 (weak confidence = low quality)
        - Message length 180-220 chars (not too short, not forced)
        
        Return tuple: (True, None) if good, or (False, "reason") if bad
        """
        if not thesis_dict:
            return False, "empty_thesis"
        
        thesis_text = thesis_dict.get("thesis", "").lower()
        confidence = thesis_dict.get("confidence", 0)
        
        # Check 1: Reject dismissive/robotic keywords
        rejection_keywords = [
            "obviously", "clearly", "if you don't see", "pay attention",
            "wake up", "not paying attention", "duh", "honestly", "literally",
            "you're wrong", "you're not seeing", "you're missing"
        ]
        
        for keyword in rejection_keywords:
            if keyword in thesis_text:
                return False, f"contains dismissive language: '{keyword}'"
        
        # Check 2: Require specific data (number, date, name, percentage)
        # Check for numbers (including percentages)
        has_number = bool(re.search(r'\d+', thesis_text))
        # Check for percentages
        has_percentage = bool(re.search(r'\d+%', thesis_text) or re.search(r'percent', thesis_text))
        # Check for dates (years like 2024, 2026, etc.)
        has_date = bool(re.search(r'\b(20\d{2}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)', thesis_text, re.IGNORECASE))
        # Check for person names (capitalized words that might be names)
        has_name = bool(re.search(r'\b([A-Z][a-z]+ [A-Z][a-z]+|[A-Z][a-z]+(?:,| and| &))', thesis_text))
        
        has_specific_data = has_number or has_percentage or has_date or has_name
        if not has_specific_data:
            return False, "no specific data (numbers/dates/names/percentages)"
        
        # Check 3: Has reasoning/explanation (not just disagreement)
        # Simple check: thesis should have some explanation words or structure
        reasoning_indicators = [
            "because", "since", "due to", "based on", "shows", "indicates",
            "suggests", "implies", "given", "considering", "fact that",
            "data", "polls", "odds", "market", "trend"
        ]
        has_reasoning = any(indicator in thesis_text for indicator in reasoning_indicators)
        
        # Also check if thesis is too short (might be just disagreement)
        if len(thesis_dict.get("thesis", "")) < 50:
            return False, "too short (likely lacks reasoning)"
        
        if not has_reasoning and len(thesis_text.split()) < 15:
            return False, "lacks reasoning/explanation"
        
        # Check 4: Confidence >= 60
        if confidence < 60:
            return False, f"confidence too low ({confidence}% < 60%)"
        
        # Check 5: Length 180-220 chars (not too short, not forced)
        thesis_length = len(thesis_dict.get("thesis", ""))
        if thesis_length < 180:
            return False, f"too short ({thesis_length} chars < 180)"
        if thesis_length > 220:
            return False, f"too long ({thesis_length} chars > 220)"
        
        return True, None
    
    def regenerate_thesis_if_poor(self, market_context, thesis_dict, max_attempts=2):
        """
        If thesis fails quality check, regenerate it automatically.
        
        Args:
            market_context: dict with market data
            thesis_dict: current thesis (may be poor quality)
            max_attempts: max regeneration attempts (default 2)
        
        Returns: high_quality_thesis dict, or None if all attempts fail
        
        Process:
        1. Check quality of thesis_dict
        2. If poor, regenerate via ChatGPT
        3. Check quality of new thesis
        4. Repeat up to max_attempts times
        5. Return best thesis found, or None if all fail
        """
        # Check initial quality
        is_quality, failure_reason = self.is_thesis_high_quality(thesis_dict)
        
        if is_quality:
            print(f"[STAGE 10B] ✓ Thesis passed quality check")
            return thesis_dict
        
        # Initial thesis failed, log and regenerate
        print(f"[STAGE 10B] ✗ Thesis failed quality check ({failure_reason})")
        market_name = market_context.get("market_name", "unknown")
        
        # Try regeneration up to max_attempts times
        best_thesis = thesis_dict
        best_quality_passed = False
        
        for attempt in range(1, max_attempts + 1):
            print(f"[STAGE 10B] Regenerating thesis (attempt {attempt}/{max_attempts})...")
            
            # Regenerate with attempt number
            new_thesis = self.generate_contrarian_thesis(market_context, attempt_number=attempt + 1)
            
            if not new_thesis:
                print(f"[STAGE 10B] Regeneration attempt {attempt} failed (ChatGPT error)")
                continue
            
            # Check quality of regenerated thesis
            is_quality, failure_reason = self.is_thesis_high_quality(new_thesis)
            
            if is_quality:
                print(f"[STAGE 10B] ✓ Regenerated thesis passed quality check")
                self.log_quality_check(market_name, new_thesis, passed=True, failure_reason=None, regeneration_attempts=attempt)
                return new_thesis
            else:
                print(f"[STAGE 10B] ✗ Regenerated thesis failed quality check ({failure_reason})")
                # Keep best thesis so far (in case all fail)
                best_thesis = new_thesis
                best_quality_passed = False
        
        # All attempts failed
        print(f"[STAGE 10B] ✗ Max regeneration attempts exceeded ({max_attempts}/{max_attempts}), skipping reply")
        self.log_quality_check(market_name, best_thesis, passed=False, failure_reason=failure_reason, regeneration_attempts=max_attempts)
        return None
    
    def log_quality_check(self, market_name, thesis, passed, failure_reason=None, regeneration_attempts=0):
        """
        Log quality check result for transparency.
        
        Logs to performance_log.json with type="stage10b_quality_check"
        Include: timestamp, market, thesis_text, passed (true/false), failure_reason (if failed), regeneration_attempts
        """
        try:
            if os.path.exists(self.analytics_log):
                with open(self.analytics_log, 'r') as f:
                    data = json.load(f)
            else:
                data = {"posts": []}
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "stage10b_quality_check",
                "market": market_name,
                "thesis": thesis.get("thesis", "") if thesis else "",
                "passed": passed,
                "failure_reason": failure_reason,
                "regeneration_attempts": regeneration_attempts,
                "confidence": thesis.get("confidence", 0) if thesis else 0
            }
            
            if "posts" not in data:
                data["posts"] = []
            data["posts"].append(entry)
            
            with open(self.analytics_log, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[STAGE 10B] Log error: {str(e)[:80]}")

    def generate_contrarian_thesis(self, market_context, attempt_number=1):
        """Call GPT-4 to generate contrarian thesis. Returns dict or None."""
        if not client:
            print("[STAGE 10] OpenAI client not available")
            return None
        
        # Check if this is breaking news (from Stage 11B)
        is_breaking = market_context.get('is_breaking', False) or 'BREAKING' in market_context.get('market_name', '')
        breaking_news_context = ""
        if is_breaking:
            breaking_news = market_context.get('breaking_news', '')
            if breaking_news:
                breaking_news_context = f"\n\n🚨 BREAKING NEWS CONTEXT: {breaking_news}\nThis news just broke. How does it change the odds? Be specific about immediate market impact."
        
        prompt = f"""You are a Polymarket trader analyzing a politics prediction market.

MARKET DATA:
Name: {market_context['market_name']}
Odds: {market_context['current_odds']} (implies {market_context['implied_probability']}% probability)
Volume 24h: {market_context['volume_24h']}
Resolves: {market_context['resolution_date']}
Sentiment: {market_context['sentiment']}{breaking_news_context}

CRITICAL RULES:
1. Your thesis MUST mention specific Polymarket odds, probabilities, or market movements
2. Must be data-driven analysis of the PREDICTION MARKET, not generic political commentary
3. Reference actual odds percentages, implied probabilities, or market data
4. NO generic statements like "Hunter Biden has definitely been..." or incomplete endings
5. NO "Track live:" or promotional language
6. Must analyze why Polymarket odds are mispriced, not general political opinions

GENERATE a contrarian thesis (180-220 chars) that:
- Identifies WHERE Polymarket odds are mispriced (why market consensus is wrong)
- Cites ONE specific data point: current odds %, recent odds movement, volume shift, or polling vs market gap
- Recommends BUY (odds too low, actual probability > {market_context['implied_probability']}%) or SELL (odds too high, actual probability < {market_context['implied_probability']}%)
- Mentions specific odds/probability numbers or market metrics
- Sounds like a smart trader analyzing Polymarket data, NOT a bot or generic political commentator

BANNED PHRASES (never use):
- "Track live"
- "has definitely been"
- "polarizing figure"
- Generic political commentary without market data
- Incomplete sentences ending with ":"
- Any promotional or spam-like language

Output ONLY this JSON (no markdown, no extra text):
{{"thesis": "YOUR 180-220 CHAR POLYMARKET ANALYSIS WITH SPECIFIC ODDS/DATA", "action": "BUY", "confidence": 75, "edge": "WHY MISPRICED", "bet_size": "med"}}"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Output ONLY valid JSON. No markdown. No explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=300
            )
            
            response_text = response.choices[0].message.content.strip()
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(0)
            
            data = json.loads(response_text)
            
            for field in ["thesis", "action", "confidence", "edge", "bet_size"]:
                if field not in data:
                    return None
            
            if data.get("action") not in ["BUY", "SELL"]:
                data["action"] = "BUY"
            
            try:
                data["confidence"] = max(0, min(100, int(data["confidence"])))
            except:
                data["confidence"] = 50
            
            # Log attempt number
            if attempt_number > 1:
                print(f"[STAGE 10] Generated thesis (attempt {attempt_number}/2)")
            else:
                print(f"[STAGE 10] Generated thesis (attempt {attempt_number}/2)")
            
            return data
        
        except json.JSONDecodeError:
            print(f"[STAGE 10] JSON parse failed for {market_context['market_name']}")
            return None
        except Exception as e:
            print(f"[STAGE 10] ChatGPT error: {str(e)[:100]}")
            return None
    
    def format_thesis_for_tweet(self, thesis, market_name, market_context=None):
        """
        Format thesis as tweet. Returns dict or None.
        
        Before formatting, automatically checks quality and regenerates if poor.
        """
        
        if not thesis or thesis.get("action") not in ["BUY", "SELL"]:
            return None
        
        # STAGE 10B: Quality filter + auto-regeneration
        if market_context:
            quality_thesis = self.regenerate_thesis_if_poor(market_context, thesis, max_attempts=2)
            
            if quality_thesis is None:
                # All regeneration attempts failed, skip posting
                print(f"[STAGE 10] Skipped thesis for {market_name} (quality threshold not met)")
                return None
            
            # Use quality-checked thesis
            thesis = quality_thesis
        else:
            # No market_context provided, do basic quality check
            is_quality, failure_reason = self.is_thesis_high_quality(thesis)
            if not is_quality:
                print(f"[STAGE 10B] ✗ Thesis failed quality check ({failure_reason}), but no market_context for regeneration")
                # Log the failure
                self.log_quality_check(market_name, thesis, passed=False, failure_reason=failure_reason, regeneration_attempts=0)
                return None
            else:
                print(f"[STAGE 10B] ✓ Thesis passed quality check")
                self.log_quality_check(market_name, thesis, passed=True, failure_reason=None, regeneration_attempts=0)
        
        opener = self._random_opener()
        closer = self._random_closer(thesis["action"])
        msg = f"{opener} {thesis['thesis']} {closer}"
        
        if len(msg) > 280:
            msg = msg[:270] + "…"
        
        return {
            "message": msg,
            "action": thesis["action"],
            "confidence": thesis["confidence"],
            "edge": thesis["edge"]
        }
    
    def _random_opener(self):
        import random
        openers = [
            "Here's what I see:",
            "Market consensus misses this:",
            "Odds don't match fundamentals:",
            "Everyone sleeping on this:",
            "Unpopular take:",
            "Data says:",
            "The real edge:",
            "What the market gets wrong:",
            "Think about it:",
            "Hot take:"
        ]
        return random.choice(openers)
    
    def _random_closer(self, action):
        import random
        if action == "BUY":
            closers = ["👀 Worth a look.", "Clear edge.", "Asymmetric payoff.", "Market sleeping.", "Real opportunity."]
        else:
            closers = ["Too much priced in.", "Crowd overestimating.", "Reality check needed.", "Not worth these odds.", "Fade the hype."]
        return random.choice(closers)
    
    def log_thesis(self, market_name, thesis):
        """Log thesis to analytics."""
        try:
            if os.path.exists(self.analytics_log):
                with open(self.analytics_log, 'r') as f:
                    data = json.load(f)
            else:
                data = {"posts": []}
            
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "stage10_thesis",
                "market": market_name,
                "thesis": thesis.get("thesis", ""),
                "action": thesis.get("action", ""),
                "confidence": thesis.get("confidence", 0),
                "edge": thesis.get("edge", ""),
                "engagement": 0
            }
            
            if "posts" not in data:
                data["posts"] = []
            data["posts"].append(entry)
            
            with open(self.analytics_log, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[STAGE 10] Logged thesis: {market_name}")
        except Exception as e:
            print(f"[STAGE 10] Log error: {str(e)[:80]}")

poly_intel = PolymarketIntelligence()

