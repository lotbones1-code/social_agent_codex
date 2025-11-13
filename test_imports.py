#!/usr/bin/env python3
"""
Smoke tests for political mode modules.
Tests basic imports and function availability.
"""

import sys


def test_imports():
    """Test that all political mode modules can be imported."""
    print("🧪 Testing Political Mode Imports\n")
    print("=" * 60)

    errors = []

    # Test 1: Config loader
    try:
        from app.config_loader import get_config, BotConfigLoader
        print("✓ app.config_loader imports successfully")
        config = get_config()
        assert hasattr(config, 'should_include_promo'), "Missing method: should_include_promo"
        assert hasattr(config, 'should_include_media'), "Missing method: should_include_media"
        assert hasattr(config, 'get_topics_for_mode'), "Missing method: get_topics_for_mode"
        print("  ✓ BotConfigLoader has required methods")
    except Exception as e:
        errors.append(f"config_loader: {e}")
        print(f"✗ app.config_loader failed: {e}")

    # Test 2: Image adapter
    try:
        from app.media.image_adapter import ImageAdapter
        print("✓ app.media.image_adapter imports successfully")
        adapter = ImageAdapter()
        assert hasattr(adapter, 'generate_political_image'), "Missing method: generate_political_image"
        assert hasattr(adapter, 'enabled'), "Missing attribute: enabled"
        print(f"  ✓ ImageAdapter initialized (enabled: {adapter.enabled})")
    except Exception as e:
        errors.append(f"image_adapter: {e}")
        print(f"✗ app.media.image_adapter failed: {e}")

    # Test 3: Video adapter
    try:
        from app.media.video_adapter import VideoAdapter
        print("✓ app.media.video_adapter imports successfully")
        adapter = VideoAdapter()
        assert hasattr(adapter, 'generate_political_video'), "Missing method: generate_political_video"
        assert hasattr(adapter, 'enabled'), "Missing attribute: enabled"
        print(f"  ✓ VideoAdapter initialized (enabled: {adapter.enabled})")
    except Exception as e:
        errors.append(f"video_adapter: {e}")
        print(f"✗ app.media.video_adapter failed: {e}")

    # Test 4: Politics reply generator
    try:
        from app.engagement.politics_reply import PoliticalReplyGenerator
        print("✓ app.engagement.politics_reply imports successfully")
        from app.config_loader import get_config
        config = get_config()
        gen = PoliticalReplyGenerator(config)
        assert hasattr(gen, 'generate_reply'), "Missing method: generate_reply"
        assert hasattr(gen, 'is_safe_to_reply'), "Missing method: is_safe_to_reply"
        print("  ✓ PoliticalReplyGenerator has required methods")
    except Exception as e:
        errors.append(f"politics_reply: {e}")
        print(f"✗ app.engagement.politics_reply failed: {e}")

    # Test 5: Reply composer
    try:
        from app.reply.compose import ReplyComposer
        print("✓ app.reply.compose imports successfully")
        from app.config_loader import get_config
        from app.media.image_adapter import ImageAdapter
        from app.media.video_adapter import VideoAdapter
        from app.engagement.politics_reply import PoliticalReplyGenerator

        config = get_config()
        image_adapter = ImageAdapter()
        video_adapter = VideoAdapter()
        politics_gen = PoliticalReplyGenerator(config)
        composer = ReplyComposer(config, image_adapter, video_adapter, politics_gen)

        assert hasattr(composer, 'compose_reply'), "Missing method: compose_reply"
        print("  ✓ ReplyComposer initialized successfully")
    except Exception as e:
        errors.append(f"reply.compose: {e}")
        print(f"✗ app.reply.compose failed: {e}")

    # Test 6: Config file exists
    try:
        import json
        from pathlib import Path

        config_path = Path(__file__).parent / "config" / "bot_config.json"
        assert config_path.exists(), f"Config file not found: {config_path}"
        print(f"✓ config/bot_config.json exists")

        with open(config_path) as f:
            config_data = json.load(f)

        required_keys = [
            'modes', 'rotation_enabled', 'promo_links', 'promo_frequency',
            'media_probability', 'max_reply_length', 'debate_style',
            'new_reply_composer_enabled'
        ]
        for key in required_keys:
            assert key in config_data, f"Missing required key: {key}"

        print(f"  ✓ Config has all required keys")
    except Exception as e:
        errors.append(f"config file: {e}")
        print(f"✗ config/bot_config.json validation failed: {e}")

    print("\n" + "=" * 60)

    if errors:
        print(f"❌ {len(errors)} test(s) failed:")
        for error in errors:
            print(f"   - {error}")
        sys.exit(1)
    else:
        print("✅ ALL TESTS PASSED")
        print("   Political mode modules are ready to use")
        sys.exit(0)


if __name__ == "__main__":
    test_imports()
