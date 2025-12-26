import json
import os
from datetime import datetime, timedelta

class PerformanceAnalytics:
    """
    Track performance metrics per topic/action type
    
    Logs:
    - Type of action (reply/like/retweet/video)
    - Topic (from search keyword)
    - Whether link was included
    - Engagement (views, likes)
    
    Daily summary:
    - Which topics got best CTR
    - Which action types convert best
    - Recommendation on link frequency
    """
    
    def __init__(self, log_file="performance_log.json"):
        self.log_file = log_file
        self.daily_stats = self.load_or_init_stats()
    
    def load_or_init_stats(self):
        """Load stats or initialize new day"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    # Check if it's for today
                    if data.get("date") == today:
                        return data
                    # Otherwise, reset for new day
            except Exception:
                pass
        
        return {
            "date": today,
            "actions": [],
            "topics": {},
            "totals": {
                "posts": 0,
                "replies": 0,
                "likes": 0,
                "retweets": 0,
                "quotes": 0,
                "videos": 0,
                "links_included": 0,
                "total_views": 0,
                "total_clicks": 0,
                "total_likes": 0
            }
        }
    
    def log_action(self, action_type, topic, has_link, post_id):
        """
        Log an action when it happens
        
        action_type: "reply", "like", "retweet", "quote", "video", "original"
        topic: what keyword/topic was this about
        has_link: boolean
        post_id: for later matching with engagement data
        """
        # Reset if new day
        today = datetime.now().strftime("%Y-%m-%d")
        if self.daily_stats.get("date") != today:
            self.daily_stats = self.load_or_init_stats()
        
        action = {
            "type": action_type,
            "topic": topic or "unknown",
            "has_link": has_link,
            "post_id": str(post_id) if post_id else "",
            "timestamp": datetime.now().isoformat(),
            "views": 0,
            "likes": 0,
            "clicks": 0
        }
        
        self.daily_stats["actions"].append(action)
        
        # Update totals
        totals = self.daily_stats["totals"]
        if action_type == "quote":
            totals["quotes"] = totals.get("quotes", 0) + 1
        else:
            totals[f"{action_type}s"] = totals.get(f"{action_type}s", 0) + 1
        
        if has_link:
            totals["links_included"] += 1
        
        # Update topic stats
        topic_key = topic or "unknown"
        if topic_key not in self.daily_stats["topics"]:
            self.daily_stats["topics"][topic_key] = {
                "count": 0,
                "views": 0,
                "clicks": 0,
                "likes": 0,
                "with_link": 0,
                "without_link": 0
            }
        
        self.daily_stats["topics"][topic_key]["count"] += 1
        if has_link:
            self.daily_stats["topics"][topic_key]["with_link"] += 1
        else:
            self.daily_stats["topics"][topic_key]["without_link"] += 1
        
        self.save_stats()
    
    def update_engagement(self, post_id, views, likes, clicks):
        """Update engagement after post is live for a while"""
        for action in self.daily_stats["actions"]:
            if action["post_id"] == str(post_id):
                old_views = action["views"]
                old_likes = action["likes"]
                old_clicks = action["clicks"]
                
                action["views"] = views
                action["likes"] = likes
                action["clicks"] = clicks
                
                topic = action["topic"]
                totals = self.daily_stats["totals"]
                
                # Update totals (subtract old, add new)
                totals["total_views"] = totals.get("total_views", 0) - old_views + views
                totals["total_likes"] = totals.get("total_likes", 0) - old_likes + likes
                totals["total_clicks"] = totals.get("total_clicks", 0) - old_clicks + clicks
                
                if topic in self.daily_stats["topics"]:
                    topic_stats = self.daily_stats["topics"][topic]
                    topic_stats["views"] = topic_stats.get("views", 0) - old_views + views
                    topic_stats["clicks"] = topic_stats.get("clicks", 0) - old_clicks + clicks
                    topic_stats["likes"] = topic_stats.get("likes", 0) - old_likes + likes
                
                self.save_stats()
                break
    
    def save_stats(self):
        """Save stats to file"""
        try:
            with open(self.log_file, 'w') as f:
                json.dump(self.daily_stats, f, indent=2)
        except Exception as e:
            print(f"[ANALYTICS] Error saving stats: {e}")
    
    def print_daily_summary(self):
        """
        Print a summary of today's performance
        
        Shows:
        - Total actions by type
        - Best-performing topics
        - CTR by topic (with link vs without)
        - Recommendations
        """
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        if self.daily_stats.get("date") != today:
            print("[ANALYTICS] No data yet for today")
            return
        
        totals = self.daily_stats["totals"]
        topics = self.daily_stats["topics"]
        
        print(f"""

╔════════════════════════════════════════════════════════════╗
║              STAGE 6 - DAILY PERFORMANCE SUMMARY           ║
║                    {today}                       ║
╚════════════════════════════════════════════════════════════╝

[ACTIVITY BREAKDOWN]
  Posts:        {totals.get('posts', 0)}
  Replies:      {totals.get('replies', 0)}
  Likes:        {totals.get('likes', 0)}
  Retweets:     {totals.get('retweets', 0)}
  Videos:       {totals.get('videos', 0)}
  Links Used:   {totals.get('links_included', 0)}

[ENGAGEMENT TOTALS]
  Total Views:   {totals.get('total_views', 0)}
  Total Clicks:  {totals.get('total_clicks', 0)}
  Total Likes:   {totals.get('total_likes', 0)}
  
  Avg Views/Post:   {totals.get('total_views', 0) // max(totals.get('posts', 0) + totals.get('replies', 0), 1)}
  Avg Clicks/Link:  {totals.get('total_clicks', 0) // max(totals.get('links_included', 0), 1)}

[TOP PERFORMING TOPICS]
""")
        
        # Sort topics by clicks
        sorted_topics = sorted(
            topics.items(),
            key=lambda x: x[1].get('clicks', 0),
            reverse=True
        )
        
        for i, (topic, stats) in enumerate(sorted_topics[:5]):
            avg_views = stats.get('views', 0) // max(stats.get('count', 1), 1)
            ctr_with_link = "N/A"
            if stats.get('with_link', 0) > 0:
                clicks = stats.get('clicks', 0)
                with_link = stats.get('with_link', 0)
                ctr_with_link = f"{(clicks / with_link * 100):.1f}%"
            
            print(f"""
  {i+1}. {topic}
     - Actions: {stats.get('count', 0)}
     - Views: {stats.get('views', 0)} (avg {avg_views}/post)
     - Clicks: {stats.get('clicks', 0)}
     - CTR (with link): {ctr_with_link}
""")
        
        print(f"""
[RECOMMENDATIONS]
""")
        
        # Find best-performing link strategy
        with_link_clicks = sum(s.get('clicks', 0) for s in topics.values() if s.get('with_link', 0) > 0)
        with_link_count = sum(s.get('with_link', 0) for s in topics.values())
        
        if with_link_count > 0 and with_link_clicks > 0:
            link_ctr = (with_link_clicks / with_link_count) * 100
            print(f"  ✓ Link CTR: {link_ctr:.1f}% (from {with_link_count} posts with link)")
            
            if link_ctr > 5:
                print(f"    → Consider increasing link frequency (working well)")
            elif link_ctr < 1:
                print(f"    → Consider lowering link frequency (not converting)")
        
        # Find best topic
        best_topic = sorted_topics[0][0] if sorted_topics else "N/A"
        print(f"  ✓ Best topic: {best_topic}")
        print(f"    → Focus more Radar keywords around this topic")
        
        print(f"""
╚════════════════════════════════════════════════════════════╝

""")

ANALYTICS = PerformanceAnalytics()

