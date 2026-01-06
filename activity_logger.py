#!/usr/bin/env python3
"""
[ACTIVITY_LOGGER] Comprehensive bot activity tracking system.

Tracks ALL bot actions (replies, posts, videos, errors) to a unified log
for analysis, debugging, and historical data collection.

Use this to answer: "What did the bot do?" at any point in time.
"""

import json
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

# === CONFIG ===
ACTIVITY_LOG_FILE = Path("activity_log.json")
ACTIVITY_LOG_MAX_SIZE = 100000  # Keep last 100k activities

class ActivityLogger:
    """
    Central activity logging system for the bot.
    
    Logs everything:
    - Replies (successful, failed, duplicate)
    - Posts (original, video, magnet)
    - Errors and exceptions
    - Rate limits hit
    - Searches performed
    - Trends checked
    """
    
    def __init__(self, log_file=ACTIVITY_LOG_FILE):
        self.log_file = Path(log_file)
        self.ensure_log_exists()
    
    def ensure_log_exists(self):
        """Create log file if it doesn't exist."""
        if not self.log_file.exists():
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            initial_data = {"activities": [], "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "total_activities": 0
            }}
            with open(self.log_file, 'w') as f:
                json.dump(initial_data, f, indent=2)
    
    def log(self, activity_type: str, status: str, details: Optional[Dict[str, Any]] = None, error: Optional[str] = None):
        """
        Log a bot activity.
        
        Args:
            activity_type: Type of activity (REPLY, POST, VIDEO_POST, ERROR, SEARCH, RATE_LIMIT, etc.)
            status: Status (success, failed, duplicate, blocked, etc.)
            details: Additional data dict
            error: Error message if applicable
        
        Example:
            logger.log(
                activity_type="VIDEO_POST",
                status="success",
                details={
                    "video_path": "viral_001.mp4",
                    "caption": "Watch below 👇",
                    "post_id": "1234567890"
                }
            )
        """
        try:
            # Load current log
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            
            activities = data.get("activities", [])
            
            # Create activity entry
            activity_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": activity_type,
                "status": status,
                "details": details or {}
            }
            
            if error:
                activity_entry["error"] = error
            
            # Append activity
            activities.append(activity_entry)
            
            # Keep only last N activities (prevent huge file)
            if len(activities) > ACTIVITY_LOG_MAX_SIZE:
                activities = activities[-ACTIVITY_LOG_MAX_SIZE:]
            
            # Update metadata
            data["activities"] = activities
            data["metadata"]["total_activities"] = len(activities)
            data["metadata"]["last_activity"] = activity_entry["timestamp"]
            
            # Save back
            with open(self.log_file, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            print(f"[ACTIVITY_LOGGER] Error logging activity: {e}")
    
    def get_activities(self, activity_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve activities from log.
        
        Args:
            activity_type: Filter by type (e.g., "VIDEO_POST") or None for all
            limit: Max number of activities to return
        
        Returns:
            List of activity dicts (most recent first)
        """
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            
            activities = data.get("activities", [])
            
            # Filter by type if specified
            if activity_type:
                activities = [a for a in activities if a.get("type") == activity_type]
            
            # Return most recent first, limited
            return list(reversed(activities))[:limit]
        
        except Exception as e:
            print(f"[ACTIVITY_LOGGER] Error retrieving activities: {e}")
            return []
    
    def get_stats(self, activity_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics about bot activities.
        
        Returns:
            Dict with counts by status, total, etc.
        
        Example:
            stats = logger.get_stats("VIDEO_POST")
            # Returns: {"success": 5, "failed": 2, "total": 7}
        """
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            
            activities = data.get("activities", [])
            
            # Filter if specified
            if activity_type:
                activities = [a for a in activities if a.get("type") == activity_type]
            
            # Count by status
            stats = {
                "total": len(activities),
                "by_status": {},
                "by_type": {} if not activity_type else None
            }
            
            for activity in activities:
                status = activity.get("status", "unknown")
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            return stats
        
        except Exception as e:
            print(f"[ACTIVITY_LOGGER] Error getting stats: {e}")
            return {}
    
    def summary(self) -> str:
        """
        Get human-readable summary of bot activity.
        
        Returns:
            String summary
        """
        try:
            with open(self.log_file, 'r') as f:
                data = json.load(f)
            
            activities = data.get("activities", [])
            
            # Count by type
            type_counts = {}
            status_counts = {}
            
            for activity in activities:
                atype = activity.get("type", "unknown")
                status = activity.get("status", "unknown")
                
                type_counts[atype] = type_counts.get(atype, 0) + 1
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Build summary
            summary_lines = [
                f"[ACTIVITY_LOGGER] Summary:",
                f"  Total activities: {len(activities)}",
                f"  By type:",
            ]
            
            for atype, count in sorted(type_counts.items()):
                summary_lines.append(f"    {atype}: {count}")
            
            summary_lines.append(f"  By status:")
            for status, count in sorted(status_counts.items()):
                summary_lines.append(f"    {status}: {count}")
            
            return "\n".join(summary_lines)
        
        except Exception as e:
            return f"[ACTIVITY_LOGGER] Error generating summary: {e}"

# Global logger instance
ACTIVITY_LOGGER = ActivityLogger()

# === CONVENIENT LOGGING FUNCTIONS ===

def log_reply(post_id: str, reply_text: str, status: str, error: Optional[str] = None):
    """Log a reply action."""
    ACTIVITY_LOGGER.log(
        activity_type="REPLY",
        status=status,
        details={
            "post_id": post_id,
            "reply_text": reply_text[:100],  # First 100 chars
            "text_length": len(reply_text)
        },
        error=error
    )

def log_post(post_text: str, post_type: str, status: str, error: Optional[str] = None, post_id: Optional[str] = None):
    """Log an original post."""
    ACTIVITY_LOGGER.log(
        activity_type="POST",
        status=status,
        details={
            "post_type": post_type,  # "original", "video", "magnet"
            "post_text": post_text[:100],
            "text_length": len(post_text),
            "post_id": post_id
        },
        error=error
    )

def log_video(video_path: str, caption: str, status: str, error: Optional[str] = None, post_id: Optional[str] = None):
    """Log a video post."""
    ACTIVITY_LOGGER.log(
        activity_type="VIDEO_POST",
        status=status,
        details={
            "video_path": video_path,
            "caption": caption[:100],
            "post_id": post_id
        },
        error=error
    )

def log_search(keyword: str, results_count: int):
    """Log a search action."""
    ACTIVITY_LOGGER.log(
        activity_type="SEARCH",
        status="success",
        details={
            "keyword": keyword,
            "results_count": results_count
        }
    )

def log_error(error_type: str, error_msg: str, details: Optional[Dict] = None):
    """Log an error."""
    ACTIVITY_LOGGER.log(
        activity_type="ERROR",
        status="error",
        details=details or {},
        error=error_msg
    )

def log_rate_limit(limit_type: str, sleep_seconds: int):
    """Log a rate limit hit."""
    ACTIVITY_LOGGER.log(
        activity_type="RATE_LIMIT",
        status="blocked",
        details={
            "limit_type": limit_type,  # "video_24h", "replies_per_hour", etc.
            "sleep_seconds": sleep_seconds
        }
    )

# === ANALYSIS FUNCTIONS ===

def analyze_success_rate(activity_type: str) -> float:
    """
    Calculate success rate for an activity type.
    
    Returns:
        Percentage (0-100) of successful activities
    """
    stats = ACTIVITY_LOGGER.get_stats(activity_type)
    total = stats.get("total", 0)
    success = stats.get("by_status", {}).get("success", 0)
    
    if total == 0:
        return 0.0
    return (success / total) * 100

def analyze_last_n_hours(hours: int = 24) -> Dict[str, Any]:
    """
    Analyze bot activity from last N hours.
    
    Returns:
        Dict with activity counts, types, etc.
    """
    try:
        with open(ACTIVITY_LOG_FILE, 'r') as f:
            data = json.load(f)
        
        activities = data.get("activities", [])
        cutoff_time = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        
        recent_activities = []
        for activity in activities:
            try:
                timestamp = datetime.fromisoformat(activity["timestamp"]).timestamp()
                if timestamp > cutoff_time:
                    recent_activities.append(activity)
            except Exception:
                pass
        
        # Analyze
        type_counts = {}
        status_counts = {}
        
        for activity in recent_activities:
            atype = activity.get("type", "unknown")
            status = activity.get("status", "unknown")
            type_counts[atype] = type_counts.get(atype, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "hours_analyzed": hours,
            "total_activities": len(recent_activities),
            "by_type": type_counts,
            "by_status": status_counts
        }
    
    except Exception as e:
        print(f"[ACTIVITY_LOGGER] Error analyzing last {hours} hours: {e}")
        return {}

if __name__ == "__main__":
    # Test the logger
    logger = ActivityLogger()
    
    # Log some test activities
    logger.log("REPLY", "success", {"post_id": "123", "reply_text": "Nice post!"})
    logger.log("VIDEO_POST", "success", {"video_path": "video.mp4", "caption": "Watch!"})
    logger.log("ERROR", "error", {}, "Connection timeout")
    
    # Show summary
    print(logger.summary())
    
    # Get recent activities
    print("\nLast 5 activities:")
    for activity in logger.get_activities(limit=5):
        print(f"  {activity['timestamp']} - {activity['type']}: {activity['status']}")
