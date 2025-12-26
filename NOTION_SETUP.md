# Notion Integration Setup Guide

This guide will help you set up the Notion integration for your X bot's Mission Control dashboard.

## Prerequisites

1. **Notion Account** - You need a Notion account
2. **Notion API Token** - You already have this: `ntn_296794666573mEYAnHr8l5mhH17GHNOMxkTyhydZ39uAata`
3. **Notion Database ID** - You already have this: `2d36e908b8a180a992abd323fddaf04f`
4. **Python Package** - Install the `notion-client` library

## Step 1: Install Dependencies

```bash
pip install notion-client python-dotenv
```

Or if using a virtual environment:

```bash
pip3 install notion-client python-dotenv
```

## Step 2: Add Environment Variables

Add these to your `.env` file (create it if it doesn't exist):

```bash
NOTION_API_KEY=ntn_296794666573mEYAnHr8l5mhH17GHNOMxkTyhydZ39uAata
NOTION_DATABASE_ID=2d36e908b8a180a992abd323fddaf04f
```

**Note:** The `notion_manager.py` module will use these credentials if available, or fall back to the hardcoded defaults in the code.

## Step 3: Test the Connection

Run the test script to verify everything works:

```bash
python3 test_notion.py
```

Expected output:
```
✅ Notion manager module imported successfully
✅ Notion manager initialized and enabled
✅ Activity logged successfully
✅ Task status updated successfully
✅ Dashboard metrics updated successfully
🎉 All tests passed!
```

## Step 4: Verify Integration Points

The Notion integration is automatically hooked into these bot activities:

### ✅ Startup
- Logs bot startup to Notion
- Updates "Bot Status" task to "In Progress"

### ✅ Original Posts
- Every successful post is logged to Notion
- Includes post text preview, URL, and timestamp

### ✅ Replies (Stage 10)
- Every successful reply is logged
- Includes target username, topic, and whether link was included

### ✅ Videos (Stage 11B/16A)
- Video posts are logged with video filename and caption
- Breaking news videos get special tracking

### ✅ Errors
- All errors are logged to Notion
- Failed stages are marked as "Blocked" with error details

### ✅ Sleep Mode
- Bot status updates to "Not started" when sleeping
- Includes wake-up time

### ✅ Dashboard Metrics
- Can be updated manually or scheduled
- Tracks followers, posts, replies, and average views

## Step 5: Check Your Notion Database

1. Open your Notion workspace
2. Navigate to the "Tasks Tracker" database
3. You should see new rows appearing as the bot runs:
   - **Status column**: Shows "POST", "REPLY", "VIDEO", "ERROR", "STATUS_CHANGE"
   - **Title column**: Shows activity description
   - **Description column**: Shows metadata (URLs, text previews, etc.)
   - **Date column**: Timestamp of the activity

## Database Schema Recommendations

Your Notion database should have these properties for best results:

1. **Title** (or **Name** or **Task**) - Text property for activity/task name
2. **Status** - Select property with options:
   - "In Progress" 🟢
   - "Done" ✅
   - "Blocked" 🔴
   - "Not started" ⚪
   - "POST", "REPLY", "VIDEO", "ERROR", "STATUS_CHANGE" (for activity types)
3. **Description** (optional) - Rich text property for details/metadata
4. **Date** (optional) - Date property for timestamps

## Troubleshooting

### Issue: "notion-client not installed"
**Solution:** Run `pip install notion-client`

### Issue: "Notion manager not enabled"
**Solution:** 
1. Check that `.env` file exists and has the correct keys
2. Verify the API token is correct
3. Check that the database ID is correct

### Issue: "API call failed"
**Solution:**
1. Check your Notion integration has access to the database
2. Verify the database ID is correct (should be 32 characters)
3. Check Notion API status: https://status.notion.so

### Issue: Tasks not appearing in Notion
**Solution:**
1. Check `notion_backup.log` file for backup logs (if Notion API fails)
2. Verify the database has the correct property names (Title, Status, Description)
3. Run `python3 test_notion.py` to verify connection

## Local Backup

If Notion API fails, all activities are automatically logged to `notion_backup.log` as a backup. Check this file if you notice missing entries in Notion.

## Next Steps

Once the integration is working:

1. **Monitor Activity**: Check your Notion database regularly to see bot activity
2. **Set Up Filters**: Create views in Notion to filter by activity type
3. **Create Dashboards**: Build Notion dashboards showing:
   - Posts per day
   - Reply success rate
   - Video generation frequency
   - Error tracking
4. **Daily Summaries**: The bot can create daily summary entries (bonus feature)

## Integration Code Locations

The Notion hooks are integrated in these files:

- `social_agent.py`:
  - Line ~87: Notion manager import and initialization
  - Line ~3579: Reply logging (after successful reply)
  - Line ~5607: Original post logging (after successful post)
  - Line ~610: Video post logging (after successful video post)
  - Line ~6870: Bot startup logging
  - Line ~6818: Sleep mode logging
  - Line ~3572: Error logging (in exception handlers)

- `notion_manager.py`: Complete module with all Notion API functions

## Support

If you encounter issues:
1. Check `notion_backup.log` for backup logs
2. Run `python3 test_notion.py` to diagnose connection issues
3. Check Notion API status page
4. Verify database permissions in Notion

Happy monitoring! 🚀

