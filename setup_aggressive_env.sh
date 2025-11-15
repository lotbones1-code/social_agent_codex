#!/bin/bash
# Setup aggressive growth configuration on Mac

cd ~/social_agent_codex

# Check if .env already exists and back it up
if [ -f .env ]; then
    echo "Backing up existing .env to .env.backup..."
    cp .env .env.backup
fi

echo "Creating optimized .env file for aggressive growth..."

cat > .env << 'EOF'
HEADLESS=false

# Revenue
REFERRAL_LINK=https://shamilbark.gumroad.com/l/qjsat

# AI Features (paste your API keys here)
OPENAI_API_KEY=YOUR_OPENAI_KEY_HERE
REPLICATE_API_TOKEN=YOUR_REPLICATE_KEY_HERE
REPL_IMAGE_MODEL=black-forest-labs/flux-schnell
IMAGE_ATTACH_RATE=0.0

# Smart DMs (aggressive thresholds)
ENABLE_DMS=true
DM_TRIGGER_LENGTH=180
DM_INTEREST_THRESHOLD=2.5
DM_QUESTION_WEIGHT=0.8
DM_TEMPLATES="Yo! Your tweet about {focus} hit different. Built something around this - mind if I share? {ref_link}||Real talk, that {focus} take is spot on. Documented my whole process: {ref_link}||Your question about {focus} is exactly what I was asking 6mo ago. This finally worked: {ref_link}||Been seeing {focus} everywhere. Put together a breakdown with screenshots: {ref_link}||That {focus} insight is fire. Saved the exact playbook that helped me: {ref_link}"

# Reply Templates (conversational)
REPLY_TEMPLATES="Bro the {focus} part is underrated. Everyone sleeping on this for {topic}: {ref_link}||Facts. Been testing {focus} for {topic} and this actually worked: {ref_link}||This {focus} angle on {topic} is what I needed last month. Saved what worked: {ref_link}||Wait this {focus} take on {topic} is solid. Got a breakdown: {ref_link}||Your {focus} point reminded me why I dove into {topic}. Made a guide: {ref_link}||Real quick - that {focus} observation about {topic} is spot on. Here's what I found: {ref_link}||Been obsessed with {topic} and the {focus} approach you mentioned is key: {ref_link}||Low key this {focus} on {topic} is missing from most convos. Full breakdown: {ref_link}||The way you framed {focus} for {topic} >>> Built around that exact idea: {ref_link}||Your {focus} insight on {topic} made it click. Documented everything: {ref_link}"

# Search Topics (10 topics for max reach)
SEARCH_TOPICS="AI automation||growth hacking||product launches||solopreneurs||indie hackers||creator economy||SaaS||startups||marketing automation||productivity tools"

# Keywords (broad reach)
RELEVANT_KEYWORDS="AI||automation||growth||launch||build||ship||product||startup||SaaS||founder||indie||solo||creator||tool||hack||scale||marketing||revenue||sales||traffic||conversion"

SPAM_KEYWORDS="giveaway||airdrop||pump||casino||xxx||nsfw||buy now||click here||limited time"

# Quality filters
MIN_TWEET_LENGTH=30
MIN_KEYWORD_MATCHES=1
MAX_REPLIES_PER_TOPIC=20

# Timing (aggressive - every 5 minutes)
LOOP_DELAY_SECONDS=300
EOF

# Try to restore API keys from backup if they exist
if [ -f .env.backup ]; then
    OPENAI_KEY=$(grep "^OPENAI_API_KEY=" .env.backup | cut -d'=' -f2)
    REPLICATE_KEY=$(grep "^REPLICATE_API_TOKEN=" .env.backup | cut -d'=' -f2)

    if [ ! -z "$OPENAI_KEY" ] && [ "$OPENAI_KEY" != "YOUR_OPENAI_KEY_HERE" ]; then
        sed -i.tmp "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_KEY|" .env
        echo "  ✅ Restored OpenAI API key from backup"
    fi

    if [ ! -z "$REPLICATE_KEY" ] && [ "$REPLICATE_KEY" != "YOUR_REPLICATE_KEY_HERE" ]; then
        sed -i.tmp "s|REPLICATE_API_TOKEN=.*|REPLICATE_API_TOKEN=$REPLICATE_KEY|" .env
        echo "  ✅ Restored Replicate API token from backup"
    fi

    rm -f .env.tmp
fi

echo ""
echo "✅ Aggressive growth .env created!"
echo ""
echo "Configuration:"
echo "  - 10 search topics (3x more reach)"
echo "  - 20 replies per topic (vs 12)"
echo "  - 5-minute cycles (vs 10-min)"
echo "  - Lower DM thresholds (more conversions)"
echo "  - Conversational reply templates"
echo ""
echo "Your referral link: https://shamilbark.gumroad.com/l/qjsat"
echo ""

# Check if API keys are set
if grep -q "YOUR_OPENAI_KEY_HERE" .env || grep -q "YOUR_REPLICATE_KEY_HERE" .env; then
    echo "⚠️  WARNING: You need to add your API keys to .env"
    echo "   Edit .env and replace YOUR_OPENAI_KEY_HERE and YOUR_REPLICATE_KEY_HERE"
    echo ""
fi

echo "Ready to start with: ./run_agent.sh"
