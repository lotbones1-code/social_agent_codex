#!/usr/bin/env python3
"""
[STAGE 16A] VIDEO INTEGRATION
Integrate video posting into the main social_agent.py bot loop.

This module is called FROM social_agent.py to inject video posting
into the main reply/posting cycle.
"""

import time
import random
import json
import os
from pathlib import Path
from datetime import datetime, timezone

# Import video functions from social_agent
try:
    from social_agent import (
        should_post_video_now,
        get_video_for_post,
        post_video_with_context,
        log,
        VIDEO_POSTING_CONFIG
    )
except ImportError as e:
    print(f"[VIDEO_INTEGRATION] Error importing from social_agent: {e}")
    print("[VIDEO_INTEGRATION] Make sure social_agent.py is in the same directory")
    raise

def integrate_video_into_loop(page, cycle_count=0):
    """
    [STAGE 16A] Check and post video if conditions met.
    
    Call this INSIDE the main bot loop to add video posting.
    
    Args:
        page: Playwright page object (from social_agent main loop)
        cycle_count: Current cycle number (for spacing)
    
    Returns:
        bool: True if video was posted, False otherwise
    """
    try:
        # Check if this cycle should post video
        if not should_post_video_now():
            return False
        
        # Get video to post
        video_path = get_video_for_post()
        if not video_path:
            log("[VIDEO_INTEGRATION] No video available to post")
            return False
        
        # Get context/caption
        context_text = VIDEO_POSTING_CONFIG.get("context_prompt", "Watch below 👇")
        
        # Post the video
        success = post_video_with_context(page, video_path, context_text, bypass_rate_limit=False)
        
        if success:
            log(f"[VIDEO_INTEGRATION] ✓ Video posted successfully in cycle {cycle_count}")
            return True
        else:
            log(f"[VIDEO_INTEGRATION] ✗ Failed to post video in cycle {cycle_count}")
            return False
            
    except Exception as e:
        log(f"[VIDEO_INTEGRATION] Error in video integration: {e}")
        return False

def where_to_add_video_in_loop():
    """
    Instructions on WHERE to add video integration in social_agent.py
    
    FIND THIS SECTION in social_agent.py (main loop):
    ```python
    while True:
        # Reply to trending posts
        # Post original content
        # Other stuff...
    ```
    
    ADD THIS AFTER original posting, BEFORE next iteration:
    ```python
    # [STAGE 16A] Try to post video
    from integrate_video import integrate_video_into_loop
    integrate_video_into_loop(page, cycle_count)
    ```
    
    That's it! Video will now post automatically with 5% probability every cycle.
    """
    pass

if __name__ == "__main__":
    print("[VIDEO_INTEGRATION] This module is meant to be imported by social_agent.py")
    print("[VIDEO_INTEGRATION] See where_to_add_video_in_loop() for instructions")
