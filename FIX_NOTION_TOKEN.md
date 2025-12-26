# 🔧 FIX NOTION API TOKEN

The bot shows: `[NOTION] ⚠️ Connection test failed: API token is invalid`

## Quick Fix Steps:

### 1. Get a Fresh Token
1. Go to: https://www.notion.so/my-integrations
2. Find your integration: **"Bot Task Automator"**
3. If it doesn't exist, create it:
   - Click **"New integration"**
   - Name: `Bot Task Automator`
   - Select your workspace
   - Click **"Submit"**
4. Copy the **"Internal Integration Token"** (starts with `secret_`)

### 2. Share Database with Integration
1. Open your **Tasks Tracker** database in Notion
2. Click the **"..."** menu (top right)
3. Click **"Connections"** or **"Add connections"**
4. Select **"Bot Task Automator"** integration
5. Click **"Confirm"**

### 3. Update .env File
```bash
# Edit .env file
NOTION_API_KEY=secret_YOUR_NEW_TOKEN_HERE
NOTION_DATABASE_ID=2d36e908b8a180a992abd323fddaf04f
```

### 4. Restart Bot
```bash
./run_agent.sh
```

## Verify It Works:
You should see:
```
[NOTION] ✅ Connected to Notion API
[NOTION] ✅ Notion controller initialized and connected
```

If you still see errors, check:
- Token starts with `secret_` (not `ntn_`)
- Database ID is exactly 32 characters
- Integration is shared with the database
