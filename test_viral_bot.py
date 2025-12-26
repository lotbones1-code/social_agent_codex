#!/usr/bin/env python3
"""
Test script for ELITE VIRAL BOT OVERHAUL
Generates 10 sample posts to verify diversity engine and human randomization
"""

import sys
import os
sys.path.insert(0, '.')

# Import the functions we need
from social_agent import (
    load_viral_templates, 
    diversity_engine, 
    human_randomization,
    select_next_template,
    load_template_history,
    load_posted_history,
    save_posted_history,
    insert_odds_into_template,
    random
)
from datetime import datetime, timezone

def test_viral_bot_overhaul():
    """Test the viral bot overhaul with 10 sample posts."""
    print("=" * 70)
    print("ELITE VIRAL BOT OVERHAUL - DIVERSITY TEST")
    print("=" * 70)
    print()
    
    # Load templates
    templates = load_viral_templates('viral_templates.json')
    template_list = templates.get("original", [])
    
    print(f"✅ Loaded {len(template_list)} templates")
    print()
    
    # Clear posted history for clean test
    import json
    from pathlib import Path
    posted_history_file = Path("storage/posted_history.json")
    if posted_history_file.exists():
        posted_history_file.unlink()
    
    print("Generating 10 sample posts...")
    print("=" * 70)
    print()
    
    posts_generated = []
    
    for i in range(10):
        print(f"--- POST #{i+1} ---")
        
        # Get last post data for diversity engine
        last_post_history = load_posted_history()
        last_post_data = last_post_history[0] if last_post_history else None
        
        # Run diversity engine
        banned_tiers, banned_emojis = diversity_engine(last_post_data)
        print(f"Banned tiers: {banned_tiers}")
        print(f"Banned emojis: {banned_emojis}")
        
        # Select template with diversity
        recent_template_ids = load_template_history()
        selected_template = select_next_template(template_list, recent_template_ids, banned_tiers=banned_tiers)
        
        if not selected_template:
            print("❌ No template selected!")
            continue
        
        template_text = selected_template.get("text", "")
        template_id = selected_template.get("id", "unknown")
        template_tier = selected_template.get("tier", "unknown")
        template_emoji = selected_template.get("emoji")
        
        print(f"Template ID: {template_id}")
        print(f"Template Tier: {template_tier}")
        print(f"Template Emoji: {template_emoji}")
        
        # Insert odds (simplified - just replace placeholders)
        market_context = {"market_name": "Bitcoin", "topic": "Bitcoin"}
        text_with_odds = insert_odds_into_template(template_text, market_context)
        
        # Apply human randomization
        final_text = human_randomization(text_with_odds)
        
        print(f"Final Text: {final_text}")
        print()
        
        # Save post data for next iteration
        save_posted_history({
            "template_id": template_id,
            "template_tier": template_tier,
            "emoji_used": template_emoji or "none",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        posts_generated.append({
            "id": i+1,
            "template_id": template_id,
            "tier": template_tier,
            "emoji": template_emoji or "none",
            "text": final_text
        })
    
    print()
    print("=" * 70)
    print("DIVERSITY ANALYSIS")
    print("=" * 70)
    print()
    
    # Check for tier diversity
    tiers_used = [p["tier"] for p in posts_generated]
    print(f"Tiers used: {tiers_used}")
    unique_tiers = set(tiers_used)
    print(f"Unique tiers: {len(unique_tiers)} / {len(posts_generated)} posts")
    
    # Check for consecutive same tiers
    consecutive_same = 0
    for i in range(len(tiers_used) - 1):
        if tiers_used[i] == tiers_used[i+1]:
            consecutive_same += 1
            print(f"⚠️  Posts #{i+1} and #{i+2} both used tier: {tiers_used[i]}")
    
    if consecutive_same == 0:
        print("✅ No consecutive same-tier posts!")
    else:
        print(f"⚠️  {consecutive_same} consecutive same-tier posts detected")
    
    print()
    
    # Check for emoji diversity
    emojis_used = [p["emoji"] for p in posts_generated]
    print(f"Emojis used: {emojis_used}")
    unique_emojis = set(emojis_used)
    print(f"Unique emojis: {len(unique_emojis)} / {len(posts_generated)} posts")
    
    # Check for consecutive same emojis
    consecutive_same_emoji = 0
    for i in range(len(emojis_used) - 1):
        if emojis_used[i] == emojis_used[i+1] and emojis_used[i] != "none":
            consecutive_same_emoji += 1
            print(f"⚠️  Posts #{i+1} and #{i+2} both used emoji: {emojis_used[i]}")
    
    if consecutive_same_emoji == 0:
        print("✅ No consecutive same-emoji posts!")
    else:
        print(f"⚠️  {consecutive_same_emoji} consecutive same-emoji posts detected")
    
    print()
    print("=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    test_viral_bot_overhaul()

