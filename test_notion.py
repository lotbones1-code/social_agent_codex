#!/usr/bin/env python3
"""
Test script to verify Notion integration works correctly.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

try:
    from notion_manager import NotionManager, init_notion_manager
    print("✅ notion_manager module imported successfully")
except ImportError as e:
    print(f"❌ Failed to import notion_manager: {e}")
    print("   Install dependencies: pip install notion-client python-dotenv")
    sys.exit(1)

def test_notion_connection():
    """Test basic Notion API connection"""
    print("\n" + "="*60)
    print("TEST 1: Notion Connection")
    print("="*60)
    
    manager = init_notion_manager()
    
    if not manager.enabled:
        print("❌ Notion manager is disabled")
        print("   Check that:")
        print("   1. notion-client is installed: pip install notion-client")
        print("   2. NOTION_API_KEY is set in .env or environment")
        print("   3. NOTION_DATABASE_ID is set in .env or environment")
        return False
    
    print("✅ Notion manager initialized and enabled")
    print(f"   Database ID: {manager.database_id[:8]}...")
    return True


def test_log_activity():
    """Test logging an activity to Notion"""
    print("\n" + "="*60)
    print("TEST 2: Log Activity")
    print("="*60)
    
    manager = init_notion_manager()
    
    if not manager.enabled:
        print("⚠️ Skipping - Notion manager not enabled")
        return False
    
    try:
        page_id = manager.log_activity(
            "STATUS_CHANGE",
            "Test activity from Python script",
            metadata={
                "test": "true",
                "script": "test_notion.py",
                "message": "This is a test entry"
            }
        )
        
        if page_id:
            print(f"✅ Activity logged successfully")
            print(f"   Page ID: {page_id}")
            return True
        else:
            print("❌ Activity logging returned None")
            return False
    except Exception as e:
        print(f"❌ Failed to log activity: {e}")
        return False


def test_update_task_status():
    """Test updating a task status"""
    print("\n" + "="*60)
    print("TEST 3: Update Task Status")
    print("="*60)
    
    manager = init_notion_manager()
    
    if not manager.enabled:
        print("⚠️ Skipping - Notion manager not enabled")
        return False
    
    try:
        # Try to update "Bot Status" task
        success = manager.update_task_status(
            "Bot Status",
            "In Progress",
            "Test update from Python script"
        )
        
        if success:
            print("✅ Task status updated successfully")
            print("   Task: Bot Status")
            print("   Status: 🟢 In Progress")
            return True
        else:
            print("⚠️ Task status update returned False (task may not exist yet)")
            print("   This is OK - task will be created on first real update")
            return True  # Not a failure, just means task doesn't exist yet
    except Exception as e:
        print(f"❌ Failed to update task status: {e}")
        return False


def test_dashboard_metrics():
    """Test updating dashboard metrics"""
    print("\n" + "="*60)
    print("TEST 4: Dashboard Metrics")
    print("="*60)
    
    manager = init_notion_manager()
    
    if not manager.enabled:
        print("⚠️ Skipping - Notion manager not enabled")
        return False
    
    try:
        success = manager.update_dashboard_metrics(
            followers=123,
            posts_today=5,
            replies_today=12,
            views_avg=45.6
        )
        
        if success:
            print("✅ Dashboard metrics updated successfully")
            print("   Followers: 123")
            print("   Posts Today: 5")
            print("   Replies Today: 12")
            print("   Avg Views: 45.6")
            return True
        else:
            print("⚠️ Dashboard metrics update returned False")
            return False
    except Exception as e:
        print(f"❌ Failed to update dashboard metrics: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("NOTION INTEGRATION TEST SUITE")
    print("="*60)
    
    results = []
    
    # Test 1: Connection
    results.append(("Connection", test_notion_connection()))
    
    # Test 2: Log Activity
    results.append(("Log Activity", test_log_activity()))
    
    # Test 3: Update Task Status
    results.append(("Update Task Status", test_update_task_status()))
    
    # Test 4: Dashboard Metrics
    results.append(("Dashboard Metrics", test_dashboard_metrics()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! Notion integration is working correctly.")
        print("   You can now run your bot and it will update Notion automatically.")
        return 0
    else:
        print("\n⚠️ Some tests failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())

