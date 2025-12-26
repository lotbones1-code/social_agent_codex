"""
Hashtag Manager - Generates strategic hashtags for posts
Part of the Bot Reconstruction "The Awakening"
"""

import random
import json
import logging

logger = logging.getLogger(__name__)

def load_hashtag_config():
    """Load hashtag rules from viral_templates.json"""
    try:
        with open("viral_templates.json") as f:
            config = json.load(f)
            return config.get("hashtag_rules", {})
    except Exception as e:
        logger.error(f"Failed to load hashtag config: {e}")
        return {}

def generate_hashtags(template_tier, market_category="crypto", avoid_hashtags=None):
    """
    Generates 2-3 hashtags per post based on template tier and market category.
    Intelligently chosen to avoid repetition.
    
    Args:
        template_tier: Type of template (contrarian, educational, urgency, etc)
        market_category: Type of market (crypto, politics, traditional, sports)
        avoid_hashtags: List of hashtags to not use (for variety)
    
    Returns:
        String of hashtags separated by spaces (e.g., "#Polymarket #Analysis #Crypto")
    """
    
    if avoid_hashtags is None:
        avoid_hashtags = []
    
    # Define hashtags by tier
    tier_hashtags = {
        "contrarian": ["#HotTake", "#Unpopular", "#Fade", "#Contrarian", "#AlphaMove"],
        "educational": ["#Analysis", "#Research", "#DeepDive", "#DataDriven", "#Breakdown"],
        "urgency": ["#Breaking", "#Alpha", "#Signal", "#AlertMode", "#MoneyMove"],
        "question": ["#Discussion", "#Debate", "#Thoughts", "#OpenQuestion", "#WhatDoYouThink"],
        "gametheory": ["#GameTheory", "#Incentives", "#Meta", "#Strategic", "#SmartMoney"],
        "minimal": ["#Trading", "#Markets", "#Crypto", "#Perspective", "#RealTalk"]
    }
    
    # Define hashtags by category
    category_hashtags = {
        "crypto": ["#Bitcoin", "#Ethereum", "#Crypto", "#DeFi", "#Web3"],
        "politics": ["#Election2024", "#Politics", "#Prediction", "#USPolitics"],
        "traditional": ["#Markets", "#Finance", "#Economy", "#Stocks"],
        "sports": ["#Sports", "#Prediction", "#Betting"],
        "general": ["#Markets", "#Odds", "#Trading"]
    }
    
    # Get available hashtags for this tier
    tier_tags = tier_hashtags.get(template_tier, tier_hashtags["minimal"])
    cat_tags = category_hashtags.get(market_category, category_hashtags["general"])
    
    # Filter out hashtags we're avoiding
    tier_tags = [tag for tag in tier_tags if tag not in avoid_hashtags]
    cat_tags = [tag for tag in cat_tags if tag not in avoid_hashtags]
    
    # Pick one from tier, one from category
    chosen_tier_tag = random.choice(tier_tags) if tier_tags else "#Markets"
    chosen_cat_tag = random.choice(cat_tags) if cat_tags else "#Crypto"
    
    # Always include #Polymarket
    chosen_hashtags = [chosen_tier_tag, chosen_cat_tag, "#Polymarket"]
    
    # Remove duplicates
    chosen_hashtags = list(set(chosen_hashtags))
    
    # Return top 3 (or less if duplicates)
    return " ".join(chosen_hashtags[:3])

def add_hashtags_to_post(text, template_tier, market_category="crypto"):
    """
    Appends hashtags to the end of a post
    
    Args:
        text: The post text
        template_tier: Type of template
        market_category: Type of market
    
    Returns:
        Complete post text with hashtags
    """
    hashtags = generate_hashtags(template_tier, market_category)
    return f"{text}\n\n{hashtags}"

