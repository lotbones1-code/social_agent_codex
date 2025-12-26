#!/usr/bin/env python3
"""
Test script to verify Notion Mission Control integration.
Run this to check if Notion connection works before starting the bot.
"""

import os
import sys
from datetime import datetime, timezone

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required

print("=" * 60)
print("NOTION MISSION CONTROL - CONNECTION TEST")
print("=" * 60)

# Check credentials
api_key = os.getenv("NOTION_API_KEY")
database_id = os.getenv("NOTION_DATABASE_ID")

print(f"\n[1] NOTION_API_KEY: {'✅ Set' if api_key else '❌ Missing'}")
if api_key:
    print(f"    Format: {api_key[:10]}... (length: {len(api_key)})")

print(f"\n[2] NOTION_DATABASE_ID: {'✅ Set' if database_id else '❌ Missing'}")
if database_id:
    print(f"    Format: {database_id[:8]}... (length: {len(database_id)})")

# Test import
print("\n[3] Testing notion_manager import...")
try:
    from notion_manager import NotionManager, init_notion_manager
    print("    ✅ notion_manager imported successfully")
except ImportError as e:
    print(f"    ❌ Import failed: {e}")
    print("    Install: pip install notion-client")
    sys.exit(1)

# Test initialization
print("\n[4] Testing Notion connection...")
try:
    manager = init_notion_manager()
    
    if not manager:
        print("    ❌ Manager is None")
        sys.exit(1)
    
    if not manager.enabled:
        print("    ⚠️ Manager initialized but not enabled")
        print("    Check credentials and database connection")
        sys.exit(1)
    
    print("    ✅ Notion manager initialized and enabled")
    
except Exception as e:
    print(f"    ❌ Initialization failed: {e}")
    sys.exit(1)

# Test update_task_status
print("\n[5] Testing update_task_status()...")
try:
    test_time = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    result = manager.update_task_status(
        "Bot Status",
        "In Progress",
        f"Test connection at {test_time}"
    )
    if result:
        print("    ✅ update_task_status() works")
    else:
        print("    ⚠️ update_task_status() returned False (check Notion)")
except Exception as e:
    print(f"    ⚠️ update_task_status() error: {e}")

# Test log_activity
print("\n[6] Testing log_activity()...")
try:
    result = manager.log_activity(
        "STATUS_CHANGE",
        "Test activity log",
        {"test": "true", "timestamp": test_time}
    )
    if result:
        print("    ✅ log_activity() works")
    else:
        print("    ⚠️ log_activity() returned None (check Notion)")
except Exception as e:
    print(f"    ⚠️ log_activity() error: {e}")

# Test update_dashboard_metrics
print("\n[7] Testing update_dashboard_metrics()...")
try:
    result = manager.update_dashboard_metrics(
        followers=100,
        posts_today=5,
        replies_today=10,
        views_avg=50.5
    )
    if result:
        print("    ✅ update_dashboard_metrics() works")
    else:
        print("    ⚠️ update_dashboard_metrics() returned False (check Notion)")
except Exception as e:
    print(f"    ⚠️ update_dashboard_metrics() error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
print("\n✅ If all tests passed, Notion integration is ready!")
print("⚠️ If any test failed, check:")
print("   1. NOTION_API_KEY is correct")
print("   2. NOTION_DATABASE_ID is correct")
print("   3. Integration is shared with database in Notion")
print("   4. notion-client is installed: pip install notion-client")
print("\nRun: ./run_agent.sh to start the bot with Notion logging")

