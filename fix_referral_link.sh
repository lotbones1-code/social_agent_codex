#!/bin/bash
# Quick fix to update referral link on Mac

cd ~/social_agent_codex
sed -i.bak 's|REFERRAL_LINK=.*|REFERRAL_LINK=https://shamilbark.gumroad.com/l/qjsat|' .env
echo "✅ Updated referral link to: https://shamilbark.gumroad.com/l/qjsat"
echo ""
echo "Verification:"
grep REFERRAL_LINK .env
