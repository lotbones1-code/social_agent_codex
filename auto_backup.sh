#!/bin/bash
# Auto-backup script for social_agent bot
# Runs git add, commit, and push automatically

cd "$(dirname "$0")" || exit 1

# Check if git is initialized
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "[BACKUP] Git not initialized, skipping backup"
    exit 0
fi

# Check for changes
if git diff --quiet && git diff --cached --quiet; then
    # No changes to commit
    exit 0
fi

# Add all changes (respects .gitignore)
git add .

# Commit with timestamp
COMMIT_MSG="Auto-backup: $(date '+%Y-%m-%d %H:%M:%S')"
if git commit -m "$COMMIT_MSG" > /dev/null 2>&1; then
    echo "[BACKUP] Committed changes: $COMMIT_MSG"
    
    # Push to remote (non-blocking, don't fail if push fails)
    if git push origin main > /dev/null 2>&1; then
        echo "[BACKUP] ✓ Code saved to GitHub"
    else
        echo "[BACKUP] ⚠ Commit successful but push failed (will retry next time)"
    fi
else
    echo "[BACKUP] ⚠ No changes to commit or commit failed"
fi

exit 0

