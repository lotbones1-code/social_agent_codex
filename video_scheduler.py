# VIDEO SCHEDULER - DISABLED
# This module is disabled to prevent crashes from missing config keys
# All methods return False or do nothing

class VideoScheduler:
    def __init__(self, config_file="video_schedule.json"):
        # Minimal initialization - no config loading to prevent KeyErrors
        pass
    
    def should_post_video_now(self):
        """Always returns False - video posting is disabled"""
        return False  # ALWAYS FALSE - VIDEO POSTING DISABLED
    
    def log_video_posted(self):
        """No-op - videos are disabled"""
        pass
    
    def mark_video_posted(self):
        """No-op - videos are disabled"""
        pass
    
    def reset_daily_counter_if_needed(self):
        """No-op - videos are disabled"""
        pass
    
    def load_config(self):
        """No-op - videos are disabled"""
        return {}
    
    def save_config(self):
        """No-op - videos are disabled"""
        pass

# Global instance
VIDEO_SCHEDULER = VideoScheduler()
