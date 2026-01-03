#!/usr/bin/env python3
"""
🚀 VIRAL VIDEO RUNNER
Run this script to specifically hunt for and repost viral videos.
It uses your existing social_agent.py for login but runs the new viral engine.
"""

from social_agent import launch_ctx, sync_playwright, HOME_URL
from trendingVideos import run_viral_cycle, log

def main():
    print("🎬 Starting Viral Video Agent...")
    
    with sync_playwright() as p:
        # 1. Login using your existing profile
        ctx = launch_ctx(p)
        page = ctx.pages[0]
        
        # 2. Run the Viral Cycle (Find -> Score -> Download -> Post)
        success = run_viral_cycle(page, {})
        
        if success:
            print("\n✨ SUCCESS: Video posted! Check your profile.")
        else:
            print("\n💤 No viral videos posted this cycle.")
            
        # Keep browser open for a few seconds to verify
        page.wait_for_timeout(5000)
        ctx.close()

if __name__ == "__main__":
    main()
