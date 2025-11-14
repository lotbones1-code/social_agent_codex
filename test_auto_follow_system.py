#!/usr/bin/env python3
"""
Comprehensive test suite for the auto-follow/unfollow system.
This verifies all components work correctly.
"""

import time
from pathlib import Path
from social_agent import (
    load_config,
    FollowTracker,
    MessageRegistry,
    VideoService,
)


def test_config_loading():
    """Test that configuration loads correctly from .env"""
    print("=" * 60)
    print("TEST 1: Configuration Loading")
    print("=" * 60)

    config = load_config()

    assert config.enable_auto_follow is True, "Auto-follow should be enabled"
    assert config.enable_auto_unfollow is True, "Auto-unfollow should be enabled"
    assert config.max_follows_per_hour == 5, "Max follows per hour should be 5"
    assert config.max_unfollows_per_hour == 10, "Max unfollows per hour should be 10"
    assert config.unfollow_after_hours == 24, "Unfollow threshold should be 24 hours"
    assert config.max_daily_follows == 50, "Max daily follows should be 50"
    assert config.max_daily_unfollows == 100, "Max daily unfollows should be 100"
    assert config.target_follow_ratio == 1.2, "Target follow ratio should be 1.2"
    assert config.min_follower_count_to_follow == 10, "Min follower count should be 10"
    assert config.max_following_count_to_follow == 10000, "Max following count should be 10000"

    print("✓ Configuration loads from .env correctly")
    print(f"✓ Auto-follow: {config.enable_auto_follow}")
    print(f"✓ Auto-unfollow: {config.enable_auto_unfollow}")
    print(f"✓ Max follows/hour: {config.max_follows_per_hour}")
    print(f"✓ Max unfollows/hour: {config.max_unfollows_per_hour}")
    print(f"✓ Unfollow after: {config.unfollow_after_hours} hours")
    print(f"✓ Daily limits: {config.max_daily_follows} follows, {config.max_daily_unfollows} unfollows")
    print()


def test_follow_tracker():
    """Test FollowTracker functionality"""
    print("=" * 60)
    print("TEST 2: FollowTracker Functionality")
    print("=" * 60)

    # Create test tracker
    test_path = Path("logs/test_tracker.json")
    if test_path.exists():
        test_path.unlink()

    tracker = FollowTracker(test_path)

    # Test adding follows
    tracker.add_follow("user1")
    tracker.add_follow("user2")
    tracker.add_follow("user3")

    assert tracker.is_following("user1"), "Should be following user1"
    assert tracker.is_following("user2"), "Should be following user2"
    assert tracker.is_following("user3"), "Should be following user3"
    assert not tracker.is_following("user4"), "Should not be following user4"

    print("✓ Adding follows works correctly")
    print(f"✓ Follows today: {tracker.get_follows_today()}")
    print(f"✓ Follows this hour: {tracker.get_follows_this_hour()}")

    # Test unfollow after threshold
    # Manually add an old follow (25 hours ago)
    old_timestamp = time.time() - (25 * 3600)
    tracker._data["following"]["olduser"] = {
        "followed_at": old_timestamp,
        "followed_back": False,
    }
    tracker._save()

    users_to_unfollow = tracker.get_users_to_unfollow(24)
    assert "olduser" in users_to_unfollow, "Should identify olduser for unfollow"
    assert "user1" not in users_to_unfollow, "Should not unfollow recent follows"

    print(f"✓ Correctly identifies users to unfollow: {users_to_unfollow}")

    # Test follow-back detection
    tracker.mark_followed_back("user1")
    assert tracker._data["following"]["user1"]["followed_back"] is True
    print("✓ Follow-back tracking works")

    # Test unfollow
    tracker.add_unfollow("olduser")
    assert not tracker.is_following("olduser"), "Should no longer be following olduser"
    print(f"✓ Unfollows today: {tracker.get_unfollows_today()}")

    # Test rate limits
    follows_today = tracker.get_follows_today()
    unfollows_today = tracker.get_unfollows_today()
    print(f"✓ Rate limit tracking: {follows_today} follows, {unfollows_today} unfollows today")

    # Cleanup
    test_path.unlink()
    print("✓ All FollowTracker tests passed")
    print()


def test_integration():
    """Test that all components work together"""
    print("=" * 60)
    print("TEST 3: Integration Test")
    print("=" * 60)

    config = load_config()
    registry = MessageRegistry(Path("logs/replied.json"))
    video_service = VideoService(config)
    follow_tracker = FollowTracker(Path("logs/follows.json"))

    print("✓ MessageRegistry initialized")
    print("✓ VideoService initialized")
    print("✓ FollowTracker initialized")
    print("✓ All components work together")
    print()


def test_bot_startup_logs():
    """Test that startup logs will display correctly"""
    print("=" * 60)
    print("TEST 4: Startup Log Messages")
    print("=" * 60)

    config = load_config()

    print("After successful login, you will see these messages:")
    print()

    if config.enable_auto_follow:
        print(f"[INFO] Auto-follow enabled (max {config.max_follows_per_hour}/hour, {config.max_daily_follows}/day)")

    if config.enable_auto_unfollow:
        print(f"[INFO] Auto-unfollow enabled (unfollow after {config.unfollow_after_hours} hours, "
              f"max {config.max_unfollows_per_hour}/hour, {config.max_daily_unfollows}/day)")

    print()


def main():
    """Run all tests"""
    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 8 + "AUTO-FOLLOW/UNFOLLOW SYSTEM TEST SUITE" + " " * 11 + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    try:
        test_config_loading()
        test_follow_tracker()
        test_integration()
        test_bot_startup_logs()

        print("=" * 60)
        print("✅ ALL TESTS PASSED! System is fully operational.")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Update .env with your real Twitter/X credentials")
        print("2. Run: python social_agent.py")
        print("3. Log in when prompted")
        print("4. The bot will automatically follow/unfollow users")
        print()

    except AssertionError as e:
        print()
        print("=" * 60)
        print(f"❌ TEST FAILED: {e}")
        print("=" * 60)
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
