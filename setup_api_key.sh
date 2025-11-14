#!/bin/bash
# Setup script to configure OpenAI API key

echo "Setting up OpenAI API key..."

# Replace the placeholder with the actual API key
sed -i.bak 's/OPENAI_API_KEY=your-openai-api-key-here/OPENAI_API_KEY=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/g' .env

echo "✓ API key configured!"
echo "✓ Ready to run: python social_agent.py"
