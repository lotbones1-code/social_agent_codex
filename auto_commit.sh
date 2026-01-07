#!/bin/bash
# Auto-commit script - runs every minute to keep GitHub updated for Perplexity

cd /Users/shamil/social_agent_codex-1 || exit 1

# Check if git is initialized
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "[AUTO-COMMIT $(date '+%H:%M:%S')] Git not initialized"
    exit 0
fi

# Check if remote exists
if ! git remote get-url origin > /dev/null 2>&1; then
    echo "[AUTO-COMMIT $(date '+%H:%M:%S')] No GitHub remote configured"
    exit 0
fi

# Get current branch
BRANCH=$(git branch --show-current 2>/dev/null || echo "main")

# Add all changes (respects .gitignore)
git add -A > /dev/null 2>&1

# Check if there are changes to commit
if git diff --cached --quiet; then
    # No changes to commit
    exit 0
fi

# Commit with timestamp
COMMIT_MSG="Auto-commit: $(date '+%Y-%m-%d %H:%M:%S') - Perplexity sync"
if git commit -m "$COMMIT_MSG" > /dev/null 2>&1; then
    echo "[AUTO-COMMIT $(date '+%H:%M:%S')] ✓ Committed changes"
    
    # Push to GitHub (try main first, then master)
    if git push origin "$BRANCH" > /dev/null 2>&1; then
        echo "[AUTO-COMMIT $(date '+%H:%M:%S')] ✓ Pushed to GitHub"
    else
        echo "[AUTO-COMMIT $(date '+%H:%M:%S')] ⚠ Push failed (will retry next time)"
    fi
else
    echo "[AUTO-COMMIT $(date '+%H:%M:%S')] ⚠ Commit failed"
fi

exit 0

