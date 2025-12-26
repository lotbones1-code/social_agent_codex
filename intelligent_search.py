"""
Intelligent Search Query Generator

Generates adaptive, real-time search queries based on:
- Current X trends
- Market sentiment
- Query performance history
- Engagement metrics
"""

import time
import random
import json
import os
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

class IntelligentSearch:
    def __init__(self, config_file="search_performance.json"):
        self.config_file = config_file
        self.query_performance = self.load_performance()
        self.last_query_generation = 0
        self.generated_queries = []
        self.current_query = None
        self.query_attempts = defaultdict(int)  # Track attempts per query
        self.query_successes = defaultdict(int)  # Track successful replies per query
        
        # Base query templates that adapt to trends
        self.base_templates = [
            "{trend} odds",
            "{trend} prediction",
            "{trend} betting",
            "{trend} market",
            "{trend} poll",
            "{trend} latest",
            "{trend} 2026",
            "{trend} campaign",
        ]
        
    def load_performance(self):
        """Load query performance history"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"queries": {}, "last_updated": None}
    
    def save_performance(self):
        """Save query performance history"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.query_performance, f, indent=2)
        except Exception as e:
            print(f"[SEARCH] Error saving performance: {e}")
    
    def should_regenerate_queries(self) -> bool:
        """Check if it's time to regenerate queries (every 60 minutes / once per hour)"""
        elapsed = time.time() - self.last_query_generation
        return elapsed >= (60 * 60)  # 60 minutes (once per hour)
    
    def generate_queries_from_trends(self, trends: List[str], markets: List[str] = None, openai_client=None) -> List[str]:
        """
        Generate 5-10 search queries based on current trends and Polymarket markets.
        Uses ChatGPT API if available, otherwise simple keyword logic.
        Calls ChatGPT once per hour, then reuses queries.
        """
        queries = []
        
        if not trends:
            # Fallback to base queries if no trends
            base_keywords = ["Polymarket", "election odds", "prediction market", "betting markets", "political odds"]
            for keyword in base_keywords[:5]:
                queries.append(keyword)
            return queries
        
        # Use ChatGPT to generate smart queries (once per hour)
        if openai_client:
            try:
                trends_str = ", ".join(trends[:5])
                markets_str = ""
                if markets:
                    markets_str = f"\n\nCurrent Polymarket markets: {', '.join(markets[:3])}"
                
                prompt = f"""You are generating search queries for an X (Twitter) bot that finds posts about prediction markets and betting odds.

Current X trending topics: {trends_str}{markets_str}

Generate 10 search queries (one per line, no numbering) that would find relevant tweets about:
- Prediction markets related to these trends
- Betting odds for these topics
- Political markets (elections, polls, policy)
- Crypto/finance markets if relevant

Format: Just the queries, one per line. Keep them short (2-4 words max). Focus on what traders/bettors would actually search for on X.

Example format:
Trump 2026 odds
FOMC rate decision
bitcoin price action
election betting markets
senate control prediction

Generate queries now:"""

                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You generate concise, effective X search queries. Output only the queries, one per line, no numbering or explanations."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.9,  # Higher temperature for more variety
                    max_tokens=200,  # More tokens for 10 queries
                )
                
                llm_queries = response.choices[0].message.content.strip().split('\n')
                # Clean and filter queries
                for q in llm_queries:
                    q = q.strip()
                    # Remove numbering if present
                    q = re.sub(r'^\d+[\.\)]\s*', '', q)
                    if q and len(q) > 3 and len(q) < 50:
                        queries.append(q)
                
                if len(queries) >= 5:
                    return queries[:10]  # Return up to 10
            except Exception as e:
                print(f"[SEARCH] LLM query generation failed: {e}, using fallback")
        
        # Fallback: Simple keyword-based generation
        for trend in trends[:5]:
            # Clean trend (remove hashtags, @ mentions)
            clean_trend = trend.replace('#', '').replace('@', '').strip()
            if len(clean_trend) < 3:
                continue
            
            # Generate variations
            for template in self.base_templates[:3]:  # Use first 3 templates
                query = template.format(trend=clean_trend)
                if query not in queries:
                    queries.append(query)
        
        # Add base queries if we don't have enough
        if len(queries) < 5:
            base_queries = [
                "Polymarket",
                "election odds",
                "prediction market",
                "betting markets",
                "political odds",
                "senate odds",
                "2026 election",
            ]
            for bq in base_queries:
                if bq not in queries:
                    queries.append(bq)
        
        return queries[:10]
    
    def evaluate_query_performance(self, page, query: str) -> Dict:
        """
        Evaluate a query by searching and checking results.
        Returns dict with: result_count, avg_engagement, has_recent_posts
        """
        try:
            # Build search URL - use query exactly as provided (no filters added)
            clean_query = query.strip()
            search_url = f"https://x.com/search?q={clean_query.replace(' ', '%20')}&src=typed_query&f=live"
            page.goto(search_url, wait_until="domcontentloaded", timeout=10000)
            time.sleep(2)
            
            # Wait for tweets to load
            for _ in range(10):
                if page.locator('article[data-testid="tweet"]').count() > 0:
                    break
                time.sleep(0.5)
            
            cards = page.locator('article[data-testid="tweet"]')
            result_count = min(cards.count(), 100)  # Cap at 100 for performance
            
            if result_count == 0:
                return {"result_count": 0, "avg_engagement": 0, "has_recent_posts": False, "score": 0}
            
            # Sample first 10 cards to estimate engagement
            engagement_scores = []
            recent_count = 0
            
            for i in range(min(10, result_count)):
                try:
                    card = cards.nth(i)
                    # Try to get likes
                    likes = 0
                    try:
                        likes_elem = card.locator('[data-testid="like"]').first
                        if likes_elem.count() > 0:
                            likes_text = likes_elem.inner_text()
                            likes_str = likes_text.replace("K", "000").replace("M", "000000").replace(",", "").strip()
                            likes = int(''.join(filter(str.isdigit, likes_str))) if likes_str else 0
                    except Exception:
                        pass
                    
                    engagement_scores.append(likes)
                    
                    # Check if recent (has "m" or "h" in time indicator - approximate)
                    # This is a heuristic since X doesn't always show exact timestamps
                    if likes > 0:  # Assume posts with engagement are more likely recent
                        recent_count += 1
                except Exception:
                    continue
            
            avg_engagement = sum(engagement_scores) / len(engagement_scores) if engagement_scores else 0
            has_recent_posts = recent_count >= 3  # At least 3 posts with engagement
            
            # Calculate score: prefer 50-500 results, 5+ avg engagement, recent posts
            score = 0
            if 50 <= result_count <= 500:
                score += 30
            elif result_count > 500:
                score += 10  # Too many results, harder to find good targets
            elif result_count > 0:
                score += 5  # Some results but not ideal
            
            if avg_engagement >= 5:
                score += 40
            elif avg_engagement >= 1:
                score += 20
            
            if has_recent_posts:
                score += 30
            
            return {
                "result_count": result_count,
                "avg_engagement": avg_engagement,
                "has_recent_posts": has_recent_posts,
                "score": score
            }
            
        except Exception as e:
            print(f"[SEARCH] Error evaluating query '{query}': {str(e)[:50]}")
            return {"result_count": 0, "avg_engagement": 0, "has_recent_posts": False, "score": 0}
    
    def select_best_queries(self, page, queries: List[str], trends: List[str] = None, count: int = 2) -> List[str]:
        """
        Evaluate queries and select the best 2-3 queries.
        Returns list of best queries (or empty list if all are bad).
        """
        if not queries:
            return []
        
        query_scores = []
        
        # Evaluate each query (evaluate top 8 to find best 2-3)
        for query in queries[:8]:
            perf = self.evaluate_query_performance(page, query)
            score = perf["score"]
            
            # Boost score based on historical performance
            if query in self.query_performance.get("queries", {}):
                hist = self.query_performance["queries"][query]
                success_rate = hist.get("successes", 0) / max(hist.get("attempts", 1), 1)
                if success_rate > 0.3:  # 30%+ success rate
                    score += 20
            
            query_scores.append((query, score, perf))
        
        # Sort by score
        query_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Select best 2-3 queries (score > 30)
        selected_queries = []
        for query, score, perf in query_scores:
            if score >= 30 and len(selected_queries) < count:  # Minimum viable score
                print(f"[SEARCH] Selected query \"{query}\" ({perf['result_count']} results, avg engagement {perf['avg_engagement']:.1f}, score {score})")
                selected_queries.append(query)
        
        # If we don't have enough good queries, use the best ones anyway
        if len(selected_queries) < count and query_scores:
            for query, score, perf in query_scores:
                if query not in selected_queries and len(selected_queries) < count:
                    print(f"[SEARCH] Selected query \"{query}\" ({perf['result_count']} results, avg engagement {perf['avg_engagement']:.1f}, score {score}) - best available")
                    selected_queries.append(query)
        
        return selected_queries
    
    def select_best_query(self, page, queries: List[str], trends: List[str] = None) -> Optional[str]:
        """
        Legacy method: Select single best query (for backward compatibility).
        """
        best_queries = self.select_best_queries(page, queries, trends, count=1)
        return best_queries[0] if best_queries else None
    
    def get_next_query(self, page, trends: List[str] = None, markets: List[str] = None, openai_client=None) -> str:
        """
        Main entry point: Get the next intelligent search query.
        Regenerates every 60 minutes (once per hour), otherwise reuses best-performing query.
        Uses Stage 12's trending data and Polymarket markets.
        """
        # Regenerate queries if needed (once per hour)
        if self.should_regenerate_queries() or not self.generated_queries:
            print("[SEARCH] Regenerating queries using ChatGPT (once per hour)...")
            self.generated_queries = self.generate_queries_from_trends(trends or [], markets=markets, openai_client=openai_client)
            self.last_query_generation = time.time()
            print(f"[SEARCH] Generated {len(self.generated_queries)} queries from trends: {', '.join(self.generated_queries[:3])}...")
        
        # Select best 2-3 queries per cycle (rotate through them)
        if not hasattr(self, 'current_query_index'):
            self.current_query_index = 0
            self.current_query_list = []
        
        # Regenerate query list if needed or if current list is empty
        if not self.current_query_list or self.should_regenerate_queries():
            self.current_query_list = self.select_best_queries(page, self.generated_queries, trends, count=3)
            self.current_query_index = 0
        
        # If no good queries found, use fallback
        if not self.current_query_list:
            self.current_query_list = ["Polymarket"]
            print("[SEARCH] No good queries found, using fallback: 'Polymarket'")
        
        # Rotate through queries (use next query in list)
        self.current_query = self.current_query_list[self.current_query_index % len(self.current_query_list)]
        self.current_query_index += 1
        
        return self.current_query
    
    def record_query_attempt(self, query: str, success: bool):
        """Record that we attempted a query and whether it succeeded"""
        self.query_attempts[query] = self.query_attempts.get(query, 0) + 1
        
        if success:
            self.query_successes[query] = self.query_successes.get(query, 0) + 1
        
        # Update performance history
        if "queries" not in self.query_performance:
            self.query_performance["queries"] = {}
        
        if query not in self.query_performance["queries"]:
            self.query_performance["queries"][query] = {"attempts": 0, "successes": 0}
        
        self.query_performance["queries"][query]["attempts"] = self.query_attempts[query]
        self.query_performance["queries"][query]["successes"] = self.query_successes.get(query, 0)
        self.query_performance["last_updated"] = datetime.now().isoformat()
        
        # Save periodically (every 10 attempts)
        if sum(self.query_attempts.values()) % 10 == 0:
            self.save_performance()

# Global instance
INTELLIGENT_SEARCH = IntelligentSearch()

