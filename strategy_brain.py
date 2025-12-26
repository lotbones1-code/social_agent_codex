import json
import os
import re
from datetime import datetime
from openai import OpenAI

class StrategyBrain:
    """
    Reads daily analytics and uses ChatGPT to optimize bot strategy
    
    Process:
    1. Load yesterday's performance_log.json
    2. Analyze which topics/strategies worked best
    3. Ask ChatGPT for recommendations
    4. Update bot config automatically
    5. Log all recommendations for audit
    """
    
    def __init__(self, openai_api_key=None):
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = None
            print("[BRAIN] OpenAI API key not found, Strategy Brain disabled")
        self.recommendations_log = self.load_recommendations_log()
    
    def load_recommendations_log(self):
        """Load history of all recommendations"""
        if os.path.exists("strategy_recommendations.json"):
            try:
                with open("strategy_recommendations.json", 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "recommendations": [],
            "implemented": [],
            "rejected": []
        }
    
    def save_recommendations_log(self):
        """Save recommendation history"""
        try:
            with open("strategy_recommendations.json", 'w') as f:
                json.dump(self.recommendations_log, f, indent=2)
        except Exception as e:
            print(f"[BRAIN] Error saving recommendations log: {e}")
    
    def load_yesterdays_analytics(self):
        """Load performance data from yesterday"""
        if os.path.exists("performance_log.json"):
            try:
                with open("performance_log.json", 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return None
    
    def generate_strategy_prompt(self, analytics_data):
        """
        Create a detailed prompt for ChatGPT to analyze performance
        
        Ask ChatGPT to:
        1. Identify best-performing topics
        2. Analyze CTR by topic and link strategy
        3. Recommend topic focus for next day
        4. Recommend link frequency adjustments
        5. Suggest engagement mix tweaks
        6. Flag any warning signs
        """
        
        if not analytics_data:
            return None
        
        totals = analytics_data.get("totals", {})
        topics = analytics_data.get("topics", {})
        
        # Build topic performance summary
        topic_summary = "TOPIC PERFORMANCE:\n"
        sorted_topics = sorted(topics.items(), key=lambda x: x[1].get('clicks', 0), reverse=True)
        for topic, stats in sorted_topics:
            clicks = stats.get('clicks', 0)
            with_link = stats.get('with_link', 0)
            ctr = (clicks / max(with_link, 1) * 100) if with_link > 0 else 0
            topic_summary += f"""
  - {topic}:
    Actions: {stats.get('count', 0)}
    Views: {stats.get('views', 0)}
    Clicks: {stats.get('clicks', 0)}
    With Link: {stats.get('with_link', 0)} posts
    Without Link: {stats.get('without_link', 0)} posts
    CTR: {ctr:.1f}% (if link used)
"""
        
        prompt = f"""
You are an AI strategist optimizing a social media bot for Polymarket promotion.

YESTERDAY'S PERFORMANCE DATA:
{topic_summary}

TOTALS:
- Posts: {totals.get('posts', 0)}
- Replies: {totals.get('replies', 0)}
- Likes: {totals.get('likes', 0)}
- Retweets: {totals.get('retweets', 0)}
- Videos: {totals.get('videos', 0)}
- Links Used: {totals.get('links_included', 0)}
- Total Views: {totals.get('total_views', 0)}
- Total Clicks: {totals.get('total_clicks', 0)}
- Total Likes: {totals.get('total_likes', 0)}

TASK: Analyze this data and provide SPECIFIC, ACTIONABLE recommendations for TODAY.

You MUST respond in this exact JSON format (no other text):

{{
  "best_topic": "topic name",
  "best_topic_reason": "why this topic performed best",
  "recommended_topic_focus": ["topic1", "topic2", "topic3"],
  "link_frequency_recommendation": "INCREASE to X% / KEEP at X% / DECREASE to X%",
  "link_frequency_reasoning": "brief explanation",
  "engagement_mix_adjustment": "INCREASE likes to X% / INCREASE retweets / KEEP current / DECREASE replies",
  "engagement_mix_reasoning": "brief explanation",
  "warning_signs": ["warning1", "warning2"] or [],
  "top_3_actions": ["action1", "action2", "action3"],
  "confidence_level": "HIGH / MEDIUM / LOW"
}}

Rules for recommendations:
- NEVER recommend increasing total automation volume
- ONLY recommend strategy shifts (topic focus, link placement, engagement mix)
- If CTR on links is below 1%, recommend decreasing link frequency
- If CTR is above 3%, recommend maintaining or slightly increasing
- If a topic got 10+ clicks, strongly recommend focusing on it
- If clicks were very low overall, flag as warning
- Always assume the goal is sustainable growth, not risky spikes
"""
        
        return prompt
    
    def get_strategy_recommendations(self):
        """Ask ChatGPT to analyze yesterday's data"""
        if not self.client:
            print("[BRAIN] OpenAI client not available, skipping optimization")
            return None
        
        print("[BRAIN] Loading yesterday's analytics...")
        
        analytics = self.load_yesterdays_analytics()
        if not analytics:
            print("[BRAIN] No analytics data found, skipping optimization")
            return None
        
        prompt = self.generate_strategy_prompt(analytics)
        if not prompt:
            return None
        
        print("[BRAIN] Asking ChatGPT to analyze performance...")
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert social media strategist. Analyze bot performance data and provide JSON recommendations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            response_text = response.choices[0].message.content
            
            # Parse JSON response
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                recommendations = json.loads(json_match.group())
                print("[BRAIN] ✓ Got recommendations from ChatGPT")
                return recommendations
            else:
                print("[BRAIN] Could not parse ChatGPT response")
                return None
        
        except Exception as e:
            print(f"[BRAIN ERROR] {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def implement_recommendations(self, recommendations):
        """
        Convert ChatGPT recommendations into bot config changes
        
        Updates:
        1. radar_config.json (topic focus)
        2. link_frequency config (if needed)
        3. engagement_mix config (if needed)
        """
        
        if not recommendations:
            return False
        
        print("[BRAIN] Implementing recommendations...")
        
        # Update Radar config with recommended topics
        radar_config = self.load_radar_config()
        
        recommended_topics = recommendations.get("recommended_topic_focus", [])
        if recommended_topics:
            radar_config["hot_keywords"] = recommended_topics
            radar_config["strategy_focus"] = "AI-optimized based on yesterday's performance"
            radar_config["last_optimized"] = datetime.now().isoformat()
            
            try:
                with open("radar_config.json", 'w') as f:
                    json.dump(radar_config, f, indent=2)
                
                print(f"[BRAIN] Updated Radar config: {recommended_topics}")
            except Exception as e:
                print(f"[BRAIN] Error updating Radar config: {e}")
        
        # Log the recommendation
        recommendation_entry = {
            "timestamp": datetime.now().isoformat(),
            "recommendation": recommendations,
            "status": "implemented"
        }
        
        self.recommendations_log["recommendations"].append(recommendation_entry)
        self.recommendations_log["implemented"].append(recommendation_entry)
        self.save_recommendations_log()
        
        print("[BRAIN ✓] Recommendations implemented")
        return True
    
    def load_radar_config(self):
        """Load current Radar config"""
        if os.path.exists("radar_config.json"):
            try:
                with open("radar_config.json", 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "hot_keywords": ["polymarket"],
            "hot_accounts": ["@Polymarket"],
            "hot_topics": ["prediction market"]
        }
    
    def print_strategy_summary(self, recommendations):
        """Print a nice summary of the strategy for today"""
        
        if not recommendations:
            return
        
        print(f"""

╔════════════════════════════════════════════════════════════╗
║              STAGE 8 - DAILY STRATEGY BRAIN UPDATE         ║
║                    {datetime.now().strftime('%Y-%m-%d')}                       ║
╚════════════════════════════════════════════════════════════╝

[ANALYSIS COMPLETE]
Yesterday's best performer: {recommendations.get('best_topic', 'N/A')}
  → {recommendations.get('best_topic_reason', '')}

[TODAY'S OPTIMIZED STRATEGY]
  Topics to focus: {', '.join(recommendations.get('recommended_topic_focus', []))}
  Link frequency: {recommendations.get('link_frequency_recommendation', 'unchanged')}
    Reason: {recommendations.get('link_frequency_reasoning', '')}
  Engagement mix: {recommendations.get('engagement_mix_adjustment', 'unchanged')}
    Reason: {recommendations.get('engagement_mix_reasoning', '')}

[KEY ACTIONS]
""")
        
        for i, action in enumerate(recommendations.get('top_3_actions', []), 1):
            print(f"  {i}. {action}")
        
        if recommendations.get('warning_signs'):
            print(f"\n[⚠️  WARNINGS]")
            for warning in recommendations.get('warning_signs', []):
                print(f"  ⚠️  {warning}")
        
        print(f"""
[CONFIDENCE: {recommendations.get('confidence_level', 'MEDIUM')}]

Bot will auto-implement these changes. Previous data logged in strategy_recommendations.json.
╚════════════════════════════════════════════════════════════╝

""")

def analyze_stage10_performance(analytics_log="performance_log.json"):
    """Optional: Stage 8 reads Stage 10 theses to learn which topics work best."""
    try:
        with open(analytics_log, 'r') as f:
            data = json.load(f)
        
        stage10_posts = [p for p in data.get("posts", []) if p.get("type") == "stage10_thesis"]
        if not stage10_posts:
            return None
        
        topics = {}
        for post in stage10_posts:
            market = post.get("market", "").lower()
            if "election" in market or "senate" in market:
                topic = "election"
            elif "trump" in market or "trial" in market:
                topic = "legal"
            elif "fed" in market or "rate" in market:
                topic = "macro"
            elif "ukraine" in market or "china" in market:
                topic = "geopolitics"
            else:
                topic = "other"
            
            if topic not in topics:
                topics[topic] = {"count": 0, "engagement": 0}
            topics[topic]["count"] += 1
            topics[topic]["engagement"] += post.get("engagement", 0)
        
        ranked = sorted([(t, topics[t]["engagement"] / max(topics[t]["count"], 1)) for t in topics], key=lambda x: x[1], reverse=True)
        print("[STAGE 8] Stage 10 top topics:")
        for topic, avg_eng in ranked[:3]:
            print(f"  {topic}: {avg_eng:.1f} avg engagement")
        
        return {"top_topics": [t[0] for t in ranked]}
    except Exception as e:
        print(f"[STAGE 8] Stage 10 analysis error: {e}")
        return None

def analyze_stage11a_performance(thread_log="thread_log.json"):
    """Optional: Stage 8 reads Stage 11A threads to learn which topics work best."""
    try:
        if not os.path.exists(thread_log):
            return None
        
        with open(thread_log, 'r') as f:
            data = json.load(f)
        
        threads = data.get("threads_posted", [])
        if not threads:
            return None
        
        total_threads = len(threads)
        # Calculate avg engagement per thread (if engagement data available)
        # For now, just count threads
        print(f"[STAGE 8] Stage 11A performance:")
        print(f"  Total threads posted: {total_threads}")
        
        # Last thread date
        if threads:
            last_thread = threads[-1]
            last_date = last_thread.get("timestamp", "")
            print(f"  Last thread: {last_date}")
            print(f"  Avg tweets per thread: {sum(t.get('tweet_count', 0) for t in threads) / max(total_threads, 1):.1f}")
        
        return {
            "total_threads": total_threads,
            "threads": threads[-10:]  # Last 10 threads
        }
    except Exception as e:
        print(f"[STAGE 8] Stage 11A analysis error: {e}")
        return None

BRAIN = StrategyBrain()

