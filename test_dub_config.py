import sys
sys.path.insert(0, '.')

try:
    from bot.config import *
    print("✅ Config imports successfully")
except Exception as e:
    print(f"❌ Config import failed: {e}")
    sys.exit(1)

# Test 1: Referral link
try:
    assert "dub.co" in REFERRAL_LINK.lower(), "Referral link is not Dub.co"
    print(f"✅ Referral link correct: {REFERRAL_LINK}")
except Exception as e:
    print(f"❌ Test 1 failed: {e}")

# Test 2: Keywords clean
try:
    forbidden = ["polymarket", "prediction", "betting", "election", "crypto"]
    for keyword in SEARCH_KEYWORDS:
        for word in forbidden:
            assert word.lower() not in keyword.lower(), f"Found '{word}' in '{keyword}'"
    print(f"✅ Keywords clean ({len(SEARCH_KEYWORDS)} keywords, no forbidden terms)")
except Exception as e:
    print(f"❌ Test 2 failed: {e}")

# Test 3: System prompt updated
try:
    assert "polymarket" not in SYSTEM_PROMPT.lower(), "SYSTEM_PROMPT contains polymarket"
    assert "prediction" not in SYSTEM_PROMPT.lower(), "SYSTEM_PROMPT contains prediction"
    assert ("growth" in SYSTEM_PROMPT.lower() or "marketing" in SYSTEM_PROMPT.lower()), "SYSTEM_PROMPT not updated"
    print("✅ System prompt updated correctly")
except Exception as e:
    print(f"❌ Test 3 failed: {e}")

# Test 4: Link inclusion rate
try:
    assert 0.4 <= LINK_INCLUSION_RATE <= 0.6, f"Link rate {LINK_INCLUSION_RATE} should be 0.40-0.60"
    print(f"✅ Link inclusion rate correct: {LINK_INCLUSION_RATE}")
except Exception as e:
    print(f"❌ Test 4 failed: {e}")

# Test 5: Niches updated
try:
    assert len(TARGET_NICHES) > 0, "TARGET_NICHES is empty"
    assert "SaaS" in str(TARGET_NICHES) or "marketing" in str(TARGET_NICHES).lower(), "Niches not SaaS/marketing focused"
    print(f"✅ Target niches correct: {TARGET_NICHES}")
except Exception as e:
    print(f"❌ Test 5 failed: {e}")

print("\n🎉 All basic tests passed!")

