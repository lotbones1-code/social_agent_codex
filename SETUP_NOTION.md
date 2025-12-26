# Notion Integration Setup Guide

This guide will help you set up Notion logging for your X bot.

## Prerequisites

- Python 3.11+
- Virtual environment (venv311)
- Notion account with API access

## Step 1: Activate Virtual Environment

```bash
source venv311/bin/activate
```

You should see `(venv311)` in your terminal prompt.

## Step 2: Install notion-client

```bash
pip install notion-client
```

Verify installation:

```bash
python3 -c "from notion_client import Client; print('✅ notion-client import OK')"
```

If you see `✅ notion-client import OK`, the package is installed correctly.

## Step 3: Configure Credentials

Your Notion credentials are already hardcoded in `notion_manager.py`:
- API Token: `ntn_296794666573mEYAnHr8l5mhH17GHNOMxkTyhydZ39uAata`
- Database ID: `2d36e908b8a180a992abd323fddaf04f`

Alternatively, you can set environment variables in `.env`:
```bash
NOTION_API_KEY=ntn_296794666573mEYAnHr8l5mhH17GHNOMxkTyhydZ39uAata
NOTION_DATABASE_ID=2d36e908b8a180a992abd323fddaf04f
```

## Step 4: Test Connection

Run your bot:

```bash
python3 social_agent.py
```

Look for one of these messages at startup:

### ✅ Success:
```
[NOTION] ✅ Connected to Notion API
[NOTION] ✅ Notion controller initialized and connected
```

### ❌ Missing Package:
```
[NOTION] ⚠️ notion-client not installed. Run: pip install notion-client in your venv
[NOTION] Falling back to local logging only.
```

### ❌ Wrong Credentials:
```
[NOTION] ⚠️ Notion client available but connection test failed: [error message]
[NOTION] Check your API token and database ID
```

### ❌ Missing Credentials:
```
[NOTION] ⚠️ Notion client available but credentials are missing/invalid
[NOTION] Set NOTION_API_KEY and NOTION_DATABASE_ID environment variables
```

## Step 5: Verify Logging

1. Start the bot
2. Wait for it to post or reply
3. Go to your Notion database: https://www.notion.so/[your-workspace]/2d36e908b8a180a992abd323fddaf04f
4. Refresh the page
5. You should see new rows appearing with:
   - **POST** entries when the bot posts
   - **REPLY** entries when the bot replies
   - **ERROR** entries if errors occur

## Troubleshooting

### Issue: "notion-client not installed"
**Solution:** Make sure you're in venv311 and run:
```bash
source venv311/bin/activate
pip install notion-client
```

### Issue: "connection test failed"
**Solution:** Check that:
1. Your API token is correct
2. Your database ID is correct
3. The Notion integration has access to the database
4. You have internet connectivity

### Issue: "credentials are missing"
**Solution:** The credentials are hardcoded in `notion_manager.py`, but you can also set them via environment variables (see Step 3).

## Expected Terminal Output

### Scenario A: notion-client NOT installed
```
[NOTION] ⚠️ notion-client not installed. Run: pip install notion-client in your venv
[NOTION] Falling back to local logging only.
```

### Scenario B: notion-client installed, credentials wrong
```
[NOTION] ⚠️ Notion client available but connection test failed: [error details]
[NOTION] Check your API token and database ID
```

### Scenario C: notion-client installed, credentials valid
```
[NOTION] ✅ Connected to Notion API
[NOTION] ✅ Notion controller initialized and connected
```

## Next Steps

Once Notion logging is working:
- All bot posts will be logged to Notion automatically
- All replies will be logged to Notion automatically
- All errors will be logged to Notion automatically
- Check your Notion database regularly to monitor bot activity

