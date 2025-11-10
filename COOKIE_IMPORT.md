# Cookie Import Guide - Bypass Twitter Bot Detection

If Twitter is blocking the automated browser from logging in, you can import cookies from your regular browser instead.

## Why This Works

Twitter's bot detection is very aggressive and can block Playwright/Selenium browsers. However, your regular browser (Chrome, Firefox, Safari) is trusted and won't be blocked. By logging in with your regular browser and transferring the session cookies, you completely bypass the bot detection.

## Step-by-Step Instructions

### 1. Install a Cookie Export Extension

**Chrome/Edge:**
- Open Chrome Web Store
- Search for "EditThisCookie" or "Cookie-Editor"
- Click "Add to Chrome"

**Firefox:**
- Open Firefox Add-ons
- Search for "Cookie-Editor" or "Cookie Quick Manager"
- Click "Add to Firefox"

**Safari:**
- Unfortunately Safari doesn't have good cookie export extensions
- Use Chrome or Firefox for this step

### 2. Log In to Twitter in Your Regular Browser

1. Open your regular browser (Chrome/Firefox)
2. Go to https://x.com
3. Log in normally with your username and password
4. Complete any 2FA if prompted
5. Make sure you can see your Twitter home feed

### 3. Export Your Cookies

1. Click the cookie extension icon in your browser toolbar
2. Make sure you're on x.com (the extension only shows cookies for the current site)
3. Click "Export" or "Export All Cookies"
4. Choose JSON format (most extensions default to this)
5. Save the file somewhere easy to find (like your Desktop or Downloads folder)

### 4. Import Cookies into the Social Agent

```bash
cd /Users/shamil/social_agent_codex
python import_cookies.py
```

When prompted, enter the path to your exported cookies file:
```
Enter path to your exported cookies JSON file: /Users/shamil/Downloads/cookies.json
```

### 5. Run the Social Agent

```bash
python social_agent.py
```

The browser will open already logged in! No manual login needed.

## Troubleshooting

**"No Twitter/X cookies found in the file"**
- Make sure you're logged in to x.com before exporting
- Make sure you export cookies while on x.com (not another website)
- Some extensions only export cookies for the current site

**"File not found" error**
- Use the full path to your file
- On Mac: Drag the file from Finder into Terminal to auto-fill the path
- Remove any quotes if you pasted the path with quotes

**Cookies expire after a while**
- Twitter cookies usually last 30 days
- If the bot stops working, just re-import cookies
- You can run import_cookies.py again anytime

**Browser extension not working**
- Try a different extension
- Make sure you clicked "Allow" when the extension asked for permissions
- Restart your browser after installing the extension

## Security Note

The exported cookies file contains your Twitter session. Keep it safe:
- Don't share it with anyone
- Delete it after importing
- The cookies are only stored locally on your machine

## Video Tutorial

For a visual guide, search YouTube for "export cookies from chrome" or "export cookies from firefox".
