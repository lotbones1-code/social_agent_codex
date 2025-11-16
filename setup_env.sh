#!/bin/bash
# Auto-setup script for .env configuration
# Usage: OPENAI_KEY="your-api-key" ./setup_env.sh

cd "$(dirname "$0")"

if [ -z "$OPENAI_KEY" ]; then
  echo "ERROR: OPENAI_KEY environment variable not set"
  echo "Usage: OPENAI_KEY=\"sk-proj-...\" ./setup_env.sh"
  exit 1
fi

# Create .env file with correct configuration
cat > .env << EOF
DM_INTEREST_THRESHOLD=3.2
DM_QUESTION_WEIGHT=0.75
DM_TEMPLATES="Hey {name}! Loved how you framed {focus}. I've got a behind-the-scenes walkthrough with screenshots that might give you a head start—mind if I share the link? {ref_link}||Appreciate how deep you went on {focus}. I documented my own playbook after a bunch of trial and error. If you want it, here you go: {ref_link}||You sound serious about mastering {focus}. This is the exact toolkit I'm using with clients right now—thought you'd enjoy an early look: {ref_link}||Couldn't help but notice your questions around {focus}. I recorded a mini breakdown for the team yesterday; happy to let you peek: {ref_link}||Your energy around {focus} is infectious. Sharing the resource that finally clicked for me, just in case it sparks something for you too: {ref_link}"
DM_TRIGGER_LENGTH=220
ENABLE_DMS=true
LOOP_DELAY_SECONDS=900
MAX_REPLIES_PER_TOPIC=3
MIN_KEYWORD_MATCHES=1
MIN_TWEET_LENGTH=60
HEADLESS=true
DEBUG=false
OPENAI_API_KEY=$OPENAI_KEY
ENABLE_AI_REPLIES=true
X_USERNAME=your_twitter_username_or_email_here
X_PASSWORD=your_twitter_password_here
REFERRAL_LINK=https://shamilbark.gumroad.com/l/qjsat
RELEVANT_KEYWORDS="AI||automation||growth||launch||community||creator economy"
REPLY_TEMPLATES="This is solid! I built something similar for {topic} - check it out: {ref_link}||{focus} is exactly right. Here's what worked for me: {ref_link}||Love this take on {topic}! Made a guide about this if you want it: {ref_link}||Great point about {focus}. Sharing my notes on {topic}: {ref_link}||{focus} - YES! This helped me 10x my results: {ref_link}||Been working on {topic} for months. This might help: {ref_link}||Spot on! Here's my playbook for {topic}: {ref_link}||{focus} is the key. Full breakdown here: {ref_link}||This resonates! Built a resource on {topic}: {ref_link}||100% agree on {focus}. Check this out: {ref_link}||{topic} is huge right now. Made this for you: {ref_link}||Facts! Here's my system for {topic}: {ref_link}||{focus} changed everything for me. Details: {ref_link}||Great thread on {topic}! Related resource: {ref_link}||This! Documented my {topic} process here: {ref_link}"
SEARCH_TOPICS="AI automation||growth hacking||product launches"
SPAM_KEYWORDS="giveaway||airdrop||pump||casino||xxx||nsfw"
EOF

echo "[✓] .env file created with HEADLESS=true for stable operation"
echo "[✓] AI replies enabled with your OpenAI API key"
echo "[✓] Ready to run! Execute: ./run.sh"
