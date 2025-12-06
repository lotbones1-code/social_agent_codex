#!/bin/bash
# Start the bot with virtual display for manual login

echo "Starting bot with virtual display..."
echo "Browser will open for manual login."
echo ""

# Run with xvfb (virtual framebuffer)
xvfb-run --auto-servernum --server-args="-screen 0 1280x900x24" python3 social_agent.py
